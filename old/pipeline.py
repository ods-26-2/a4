"""mockup do a4: video + calibracao do i3 + trilhas do i2, com a quadra desenhada de volta

o i2 e o i3 rodam nos proprios containers; aqui so chegam as mensagens deles,
no envelope do guia kafka b2. pixel -> metro e feito aqui com a H recebida,
como o contrato do i3 manda. duas fontes, mesmo envelope:

    ... | python pipeline.py yolo/clipe.mp4 --calib dados/calibracao.json   # stdin + arquivo
    python pipeline.py yolo/clipe.mp4 --kafka 34.66.235.91:9093 --sessao sessao-1

mockup: sem yolo ao vivo (yolo/detectar.py gera o csv que vai pro i2), sem o
filtro em_quadra (precisava da H antes do i2) e sem a caixa crua da deteccao.
"""
import argparse
import collections
import json
import pathlib
import sys
import time

import cv2
import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "yolo"))
from detectar import fps_de

QUADRA = (18.0, 9.0)                                  # volei FIVB, em metros
LINHAS = [((0, 0), (18, 0)), ((18, 0), (18, 9)), ((18, 9), (0, 9)), ((0, 9), (0, 0)),
          ((9, 0), (9, 9)), ((6, 0), (6, 9)), ((12, 0), (12, 9))]
MAGENTA, VERDE, VERMELHO, BRANCO = (255, 0, 255), (0, 255, 0), (0, 0, 255), (255, 255, 255)
AMARELO, PRETO = (0, 255, 255), (0, 0, 0)
AZUL = (255, 160, 0)                                  # trilha de pessoa


TOPICO_CALIB = "ods.visao.calibracao_publicada"
TOPICO_TRILHAS = "ods.visao.identidade_atribuida"
CAMPOS = ("message_id", "message_type", "schema", "schema_version",
          "producer", "occurred_at", "payload")


def validar(ev, schema):
    """guia b2, 4.3: fora do formato e descartado e registrado, nunca processado na tentativa"""
    falta = [c for c in CAMPOS if c not in ev]
    if falta:
        return f"campo obrigatorio ausente: {falta[0]}"
    if ev["schema"] != schema:
        return f"schema inesperado: {ev['schema']}"
    if not str(ev["schema_version"]).startswith("1."):
        return f"versao nao suportada: {ev['schema_version']}"
    p = ev["payload"]
    if schema == TOPICO_CALIB:
        H = p.get("homography") if isinstance(p, dict) else None
        if not (isinstance(H, list) and len(H) == 3 and all(len(l) == 3 for l in H)):
            return "payload sem homography 3x3"
    elif not (isinstance(p, dict) and isinstance(p.get("frame"), int)
              and isinstance(p.get("tracks"), list)):
        return "payload sem frame ou tracks"
    return None


def ler_evento(texto, schema):
    """json -> envelope valido ou None, com o motivo no stderr"""
    try:
        ev = json.loads(texto)
    except (json.JSONDecodeError, UnicodeDecodeError):
        motivo = "json invalido"
    else:
        motivo = validar(ev, schema) if isinstance(ev, dict) else "json nao e objeto"
    if motivo:
        print(f"a4: mensagem descartada: {motivo}", file=sys.stderr)
        return None
    return ev


def homografia(ev):
    p = ev["payload"]
    print(f"i3: {p['calibration_version']} · rms {p['reprojection_rms_cm']} cm no holdout",
          file=sys.stderr)
    return np.array(p["homography"], float)


def de_arquivos(calib, linhas):
    """calibracao do arquivo do i3, trilhas do stdin em streaming"""
    ev = ler_evento(open(calib).read(), TOPICO_CALIB)
    if ev is None:
        raise SystemExit(f"a4: {calib} nao e uma calibracao valida")

    def trilhas():
        for l in linhas:
            if l.strip() and (e := ler_evento(l, TOPICO_TRILHAS)):
                yield e["payload"]["frame"], e["payload"]["tracks"]
    return homografia(ev), trilhas()


def de_kafka(a):
    """le os dois topicos ate o broker ficar quieto por --ocioso segundos

    sem commit de offset: rodar de novo relê do comeco, e o filtro por camera e
    sessao separa esta execucao das antigas. quadro repetido sobrescreve o mesmo
    indice, entao mensagem duplicada nao muda o resultado.
    """
    # ponytail: junta tudo antes de desenhar; ao vivo de verdade e desenhar no poll
    from confluent_kafka import Consumer
    consumidor = Consumer({"bootstrap.servers": a.kafka, "group.id": "A4-arbitragem",
                           "auto.offset.reset": "earliest", "enable.auto.commit": False})
    relogio = [time.monotonic()]
    # entrar no grupo leva uns segundos; o ocioso so conta depois de receber particao
    consumidor.subscribe([TOPICO_CALIB, TOPICO_TRILHAS],
                         on_assign=lambda c, parts: relogio.__setitem__(0, time.monotonic()))
    calib, quadros = None, {}
    try:
        # parada garantida (guia b2, 4.5): sai depois de --ocioso sem mensagem nova
        while time.monotonic() - relogio[0] < a.ocioso:
            msg = consumidor.poll(1.0)
            if msg is None or msg.error():
                continue
            relogio[0] = time.monotonic()
            ev = ler_evento(msg.value().decode("utf-8", "replace"), msg.topic())
            if ev is None or ev["payload"].get("camera_id") != a.camera_id:
                continue
            if msg.topic() == TOPICO_CALIB:
                calib = ev                      # a ultima publicada vale
            elif ev["payload"].get("session_id") == a.sessao:
                quadros[ev["payload"]["frame"]] = ev["payload"]["tracks"]
    finally:
        consumidor.close()
    if calib is None:
        raise SystemExit(f"a4: nenhuma calibracao de {a.camera_id} em {TOPICO_CALIB}")
    print(f"a4: {len(quadros)} quadros da sessao {a.sessao} lidos de {TOPICO_TRILHAS}",
          file=sys.stderr)
    return homografia(calib), iter(sorted(quadros.items()))


def pixel_para_mundo(H, pixel):
    v = H @ np.array([pixel[0], pixel[1], 1.0])
    return tuple(v[:2] / v[2])


def desenhar(quadro, Hinv, trilhas, H, n, t_s):
    """quadra reprojetada + a trilha de cada objeto, com id e metros"""
    def para_pixel(p):
        v = Hinv @ np.array([p[0], p[1], 1.0])
        return tuple(int(round(c)) for c in v[:2] / v[2])

    for a, b in LINHAS:
        cv2.line(quadro, para_pixel(a), para_pixel(b), MAGENTA, 1, cv2.LINE_AA)

    for tr in trilhas:                       # o que o i2 afirma ser o mesmo objeto
        centro = (tr["u_px"], tr["v_px"])
        u, v = (int(round(c)) for c in centro)
        visto = not tr["predicted"]
        # amarelo e trilha predita: nao houve deteccao neste quadro, e o centro
        # que aparece e o que a velocidade diz que devia estar
        if tr["class"] == "person":
            # a posicao em metros de uma pessoa sai do pe, nao do centro da caixa
            # que o i2 rastreia -- entao aqui vai so a identidade, sem numero errado
            cor = AZUL if visto else AMARELO
            cv2.circle(quadro, (u, v), 5, cor, -1 if visto else 1, cv2.LINE_AA)
            rotulo, canto = f"#{tr['track_id']}", (u - 8, v - 10)
        else:
            mx, my = pixel_para_mundo(H, centro)
            # fora da quadra quer dizer bola no ar: a homografia so vale no plano
            dentro = -1 <= mx <= QUADRA[0] + 1 and -1 <= my <= QUADRA[1] + 1
            cor = (VERDE if dentro else VERMELHO) if visto else AMARELO
            # a bola e o objeto que o a4 arbitra e vive cercada de 15 pessoas:
            # circulo grande com mira, senao ela some no meio dos marcadores
            cv2.circle(quadro, (u, v), 13, cor, 2, cv2.LINE_AA)
            cv2.drawMarker(quadro, (u, v), cor, cv2.MARKER_CROSS, 10, 1, cv2.LINE_AA)
            rotulo, canto = f"#{tr['track_id']} {mx:.1f},{my:.1f}m", (u - 34, v - 19)
        cv2.putText(quadro, rotulo, canto, cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    cor, 1, cv2.LINE_AA)

    porclasse = collections.Counter(tr["class"] for tr in trilhas)
    estado = (f"quadro {n}  t={t_s:6.3f}s  "
              + "  ".join(f"{c}:{q}" for c, q in sorted(porclasse.items())))
    # tarja atras do texto: o rodape cai sobre banner claro. contorno nao serve --
    # no opencv a largura do glifo depende da espessura, e os dois textos desalinham
    (larg_txt, alt_txt), base = cv2.getTextSize(estado, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(quadro, (6, 700 - alt_txt - 5), (14 + larg_txt, 704 + base), PRETO, -1)
    cv2.putText(quadro, estado, (10, 700), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                BRANCO, 1, cv2.LINE_AA)
    return quadro


def main(a):
    H, eventos = de_kafka(a) if a.kafka else de_arquivos(a.calib, sys.stdin)
    Hinv = np.linalg.inv(H)
    fps = fps_de(str(a.video))
    proximo = next(eventos, None)

    saida = a.saida or RAIZ / "dados/pipeline.mp4"
    escritor = cv2.VideoWriter(str(saida), cv2.VideoWriter_fourcc(*"mp4v"), fps, (1280, 720))
    passo = 1.0 / (fps * a.velocidade)       # o laco le mais rapido que o video corre
    alvo = time.perf_counter()

    cap = cv2.VideoCapture(str(a.video))
    n = -1
    while True:
        ok, quadro = cap.read()
        if not ok:
            break
        n += 1
        # o i2 so emite quadro que teve linha no csv; pula eventos de quadros ja passados
        while proximo is not None and proximo[0] < n:
            proximo = next(eventos, None)
        trilhas = proximo[1] if proximo is not None and proximo[0] == n else []
        arte = desenhar(quadro, Hinv, trilhas, H, n, n / fps)
        escritor.write(arte)
        if a.janela:
            cv2.imshow("INV-1 · a4 mockup  [espaco pausa · q sai]", arte)
            alvo += passo
            tecla = cv2.waitKey(max(int((alvo - time.perf_counter()) * 1000), 1)) & 0xFF
            if tecla == ord(" "):
                while cv2.waitKey(30) & 0xFF != ord(" "):
                    pass
                alvo = time.perf_counter()
            if tecla == ord("q"):
                break
    cap.release()
    escritor.release()
    if a.janela:
        cv2.destroyAllWindows()
    print(f"{n + 1} quadros a {fps:.4f} fps · video em {saida}", file=sys.stderr)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video", type=pathlib.Path)
    fonte = p.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--calib", type=pathlib.Path,
                       help="arquivo com o evento do i3; as trilhas vem do stdin")
    fonte.add_argument("--kafka", metavar="HOST:PORTA",
                       help="le calibracao e trilhas dos topicos do broker")
    p.add_argument("--camera-id", default="cam-ref", help="com --kafka")
    p.add_argument("--sessao", default="sessao-1", help="com --kafka")
    p.add_argument("--ocioso", type=float, default=10.0,
                   help="com --kafka: segundos sem mensagem nova para parar de ler")
    p.add_argument("--saida", type=pathlib.Path, help="padrao dados/pipeline.mp4")
    p.add_argument("--janela", action="store_true",
                   help="abre janela (so fora do container, precisa de display)")
    p.add_argument("--velocidade", type=float, default=1.0,
                   help="com --janela: 1.0 e tempo real; 0.25 camera lenta")
    main(p.parse_args())
