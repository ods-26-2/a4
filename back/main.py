"""API do A4: Score Manager, correção manual, anulação e integração opcional com P7/Kafka.

Desenvolvimento local (sem Kafka):
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Integração real: configure A4_KAFKA_ENABLED=true e A4_KAFKA_BOOTSTRAP_SERVERS.
O frontend conversa somente com esta API; nunca acessa Kafka diretamente.
"""
import asyncio
import bisect
import json
import logging
import os
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from arbitragem import Detector, calibracao
from kafka_bridge import KafkaBridge
from zonas import TOLERANCIA_CM, Registro, ZonaInvalida, erro_quadra_cm, pontos_para_metros, validar_quadra

logging.basicConfig(level=os.getenv("A4_LOG_LEVEL", "INFO"))
log = logging.getLogger("a4")

INTERVALO_S = float(os.getenv("A4_INTERVALO_S", "6"))
MODO_DEMO = os.getenv("A4_MODO_DEMO", "true").lower() in {"1", "true", "yes", "sim"}
KAFKA_HABILITADO = os.getenv("A4_KAFKA_ENABLED", "false").lower() in {"1", "true", "yes", "sim"}
VEREDITOS = ("dentro", "fora", "duvida")
CALIBRACAO_ARQUIVO = os.getenv("A4_CALIBRACAO_ARQUIVO")
# fonte de vídeo do player (decisão do A4): a gravação que a câmera do jogo toca, servida aqui.
# na 6c o vídeo fica fora do barramento; o player toca qualquer URL, então outra fonte é outra URL
P6_VIDEO = Path(os.getenv("A4_P6_VIDEO") or Path(__file__).parent.parent / "old" / "yolo" / "clipe.mp4")

partidas: dict[str, dict[str, Any]] = {}
kafka: KafkaBridge | None = None
registro = Registro()
calibracoes: dict[str, Any] = {}                     # source_id -> Calibracao mais recente
detectores: dict[str, tuple[str, Detector]] = {}     # source_id -> (session_id, Detector)
# último ods.session.started: started_at amarra o captured_at dos lances à posição no vídeo
sessao_p6: dict[str, Any] | None = None
clipes_pedidos: dict[str, str] = {}                  # message_id do ods.s4.capture.command -> decisao_id
# bolas que o S1 mandou na sessao em curso, no tempo do video, para o player desenhar (6c: a
# sobreposicao na tela sai de S1): [(video_s, [[u, v, em_jogo], ...])], em ordem de tempo
deteccoes_p6: list[tuple[float, list]] = []
MAX_DETECCOES = 20000                                # ~11 min de jogo a 30 quadros/s
# media_uri do S4 (s4://<caminho>) vira URL do navegador por esta base: acesso controlado do S4
S4_MIDIA_URL = os.getenv("A4_S4_MEDIA_URL", "").rstrip("/")
REPLAY_ANTES_S, REPLAY_DEPOIS_S = 3.0, 2.0


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nova_partida(time_a="Time A", time_b="Time B", source_id="cam0", pid=None):
    p = {"id": pid or str(uuid.uuid4()), "time_a": time_a, "time_b": time_b,
         "source_id": source_id, "encerrada": False, "decisoes": [], "versao": 0}
    partidas[p["id"]] = p
    return p


def ganhador(d):
    """Dentro no lado A dá ponto ao B; fora dá ponto ao lado onde quicou."""
    if d["anulada"] or d["veredito"] == "duvida":
        return None
    outro = "B" if d["lado"] == "A" else "A"
    return outro if d["veredito"] == "dentro" else d["lado"]


def placar(p):
    """Calcula o placar do zero a partir das decisões válidas, inclusive após correções.

    Vôlei: sets a 25 com dois de vantagem; 5º set a 15. O estado é derivado,
    nunca incrementado por efeitos colaterais, então corrigir/anular lance antigo
    recalcula corretamente o placar inteiro.
    """
    sets, pts = {"A": 0, "B": 0}, {"A": 0, "B": 0}
    for d in p["decisoes"]:
        g = ganhador(d)
        if not g:
            continue
        pts[g] += 1
        alvo = 15 if sets["A"] + sets["B"] == 4 else 25
        outro = "B" if g == "A" else "A"
        if pts[g] >= alvo and pts[g] - pts[outro] >= 2:
            sets[g] += 1
            pts = {"A": 0, "B": 0}
    return {"sets": sets, "pontos": pts}


def visao(p):
    return {k: v for k, v in p.items() if k != "versao"} | {"placar": placar(p)}


def buscar(pid):
    if pid not in partidas:
        raise HTTPException(404, f"partida {pid} nao existe")
    return partidas[pid]


def buscar_decisao(did):
    for p in partidas.values():
        for d in p["decisoes"]:
            if d["decisao_id"] == did:
                return p, d
    raise HTTPException(404, f"decisao {did} nao existe")


def mudou(p):
    p["versao"] += 1
    return visao(p)


def adicionar_decisao(p, decisao):
    """Adiciona uma decisão de forma idempotente por decisao_id."""
    if p["encerrada"]:
        return False
    if any(d["decisao_id"] == decisao["decisao_id"] for d in p["decisoes"]):
        return False
    decisao.setdefault("origem", "automatica")
    decisao.setdefault("operador", None)
    decisao.setdefault("veredito_automatico", None)
    decisao.setdefault("anulada", False)
    decisao.setdefault("instante", agora())
    p["decisoes"].append(decisao)
    mudou(p)
    return True


def receber_decisao_automatica(decisao: dict[str, Any]):
    """Lance decidido pelo Detector (ods.s1.position): vai para a partida aberta da câmera."""
    source_id = str(decisao.get("source_id", "cam0"))
    # A decisão vai para a partida aberta mais recente associada à câmera de origem.
    candidatas = [p for p in partidas.values() if not p["encerrada"] and p["source_id"] == source_id]
    if not candidatas:
        log.warning("Decisão automática ignorada: nenhuma partida aberta para source_id=%s", source_id)
        return
    p = candidatas[-1]
    if adicionar_decisao(p, decisao):
        log.info("Decisão automática %s adicionada à partida %s", decisao.get("decisao_id"), p["id"])


def receber_calibracao(envelope: dict[str, Any]):
    """Recebe ods.i3.calibration; a mais nova substitui a anterior da mesma câmera."""
    cal = calibracao(envelope)
    calibracoes[cal.source_id] = cal
    log.info("Calibração %s recebida para %s", cal.versao, cal.source_id)


def receber_posicao(envelope: dict[str, Any]):
    """Recebe ods.s1.position e passa a bola pela regra, usando a zona salva da câmera."""
    source_id = envelope["source_id"]
    # o barramento é compartilhado: só interessa a câmera de uma partida aberta aqui
    if not any(not p["encerrada"] and p["source_id"] == source_id for p in partidas.values()):
        return
    t_s = datetime.fromisoformat(envelope["captured_at"].replace("Z", "+00:00")).timestamp()
    # todas as bolas do quadro juntas: a bola em jogo e a que voa, nao um track_id
    # o ods.s1.position nao traz predicted (6c): ponto extrapolado pelo I2 chega como medido. o
    # ajuste do arco descarta o que nao voa, e o I2 so extrapola dentro do horizonte da predicao
    pontos = [(p["track_id"], p["point_px"]) for p in envelope["payload"]["positions"] if p["class"] == "ball"]
    em_jogo = None
    cal = calibracoes.get(source_id)
    if cal is not None:
        sessao = envelope["session_id"]
        if detectores.get(source_id, (None,))[0] != sessao:
            detectores[source_id] = (sessao, Detector())  # sessão nova: os track_id antigos não valem
        detector = detectores[source_id][1]
        decisao = detector.quadro(cal, t_s, pontos, registro.atual(source_id))
        if detector.arco is not None and detector.arco.fim == t_s:
            em_jogo = detector.arco.obs[-1][3]           # o ponto que entrou no voo da bola
        if decisao:
            receber_decisao_automatica(decisao)
    guardar_deteccoes(envelope, t_s, pontos, em_jogo)


def guardar_deteccoes(envelope, t_s, pontos, em_jogo):
    """bolas do quadro no tempo do video da sessao em curso, marcando a que o A4 pos no voo"""
    if not pontos or sessao_p6 is None or envelope["session_id"] != sessao_p6["session_id"]:
        return
    inicio = datetime.fromisoformat(sessao_p6["started_at"].replace("Z", "+00:00")).timestamp()
    deteccoes_p6.append((round(t_s - inicio, 3),
                         [[round(px[0], 1), round(px[1], 1), tid == em_jogo] for tid, px in pontos]))
    del deteccoes_p6[:-MAX_DETECCOES]


def receber_sessao(envelope: dict[str, Any]):
    """ods.session.started (6c, componente com estado): quique em andamento da sessão anterior
    não fecha. A posição também troca o Detector pelo session_id; isto cobre o quique que fica
    parado no meio quando a sessão nova chega antes do primeiro quadro dela."""
    global sessao_p6
    if sessao_p6 is None or sessao_p6["session_id"] != envelope["session_id"]:
        deteccoes_p6.clear()                          # volta nova do replay: o tempo recomeca
    # ponytail: uma câmera só no player; por source_id se o A4 mostrar duas
    sessao_p6 = {"session_id": envelope["session_id"], "started_at": envelope["payload"]["started_at"],
                 "publicada_em": envelope["published_at"]}
    for source_id in envelope["payload"].get("sources", []):
        if detectores.get(source_id, (None,))[0] != envelope["session_id"]:
            detectores.pop(source_id, None)


def receber_clipe(envelope: dict[str, Any]):
    """ods.s4.clip do pedido de replay: o clipe fica no lance e a tela recebe pela partida"""
    did = clipes_pedidos.pop(str(envelope.get("correlation_id")), None)
    if did is None:
        return                                        # clipe de outro pedido ou de outra aplicação
    p, d = buscar_decisao(did)
    c = envelope["payload"]
    uri = c["media_uri"]
    url = f"{S4_MIDIA_URL}/{uri.removeprefix('s4://')}" if S4_MIDIA_URL and uri.startswith("s4://") else None
    d["clip"] = {"clip_id": c["clip_id"], "media_uri": uri, "url": url, "start_at": c["start_at"],
                 "end_at": c["end_at"], "expires_at": c["expires_at"]}
    mudou(p)


def lance_falso(p):
    """Gera lances fictícios apenas no modo demo local, nunca com Kafka habilitado."""
    v = random.choices(VEREDITOS, weights=(5, 4, 1))[0]
    banda = round(random.uniform(8, 25), 1)
    dist = {"dentro": -random.uniform(banda, 150), "fora": random.uniform(banda, 150),
            "duvida": random.uniform(-banda, banda)}[v]
    adicionar_decisao(p, {
        "decisao_id": str(uuid.uuid4()), "veredito": v, "distancia_cm": round(dist, 1),
        "banda_cm": banda, "lado": random.choice("AB"), "position_m": None,
        "track_id": f"t-{random.randint(1, 999):04d}",
        "source_id": p["source_id"], "artifact_version": f"cal-{p['source_id']}-3", "zones_version": None,
        "origem": "automatica", "operador": None, "veredito_automatico": None,
        "anulada": False, "instante": agora()})


@asynccontextmanager
async def ciclo(_app):
    global kafka
    demo = nova_partida(pid="demo")
    tarefa = None
    registro.carregar()
    if CALIBRACAO_ARQUIVO:
        with open(CALIBRACAO_ARQUIVO, encoding="utf-8") as arquivo:
            conteudo = json.load(arquivo)
        for envelope in conteudo if isinstance(conteudo, list) else [conteudo]:
            receber_calibracao(envelope)
    if KAFKA_HABILITADO:
        kafka = KafkaBridge(receber_calibracao, receber_posicao, receber_sessao, receber_clipe)
        try:
            kafka.start()
        except Exception:
            kafka = None
            log.exception("Não foi possível iniciar a integração Kafka; API seguirá sem barramento")
    elif MODO_DEMO:
        async def gerar():
            while True:
                await asyncio.sleep(INTERVALO_S)
                if not demo["encerrada"]:
                    lance_falso(demo)
        tarefa = asyncio.create_task(gerar())
        log.warning("Modo demo ativo: decisões fictícias serão geradas. Defina A4_MODO_DEMO=false para desligar.")
    try:
        yield
    finally:
        if tarefa:
            tarefa.cancel()
            try:
                await tarefa
            except asyncio.CancelledError:
                pass
        if kafka:
            kafka.close()
            kafka = None


app = FastAPI(title="A4 · Score Manager e Camera Framing", lifespan=ciclo)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class NovaPartida(BaseModel):
    time_a: str = Field(default="Time A", min_length=1, max_length=80)
    time_b: str = Field(default="Time B", min_length=1, max_length=80)
    source_id: str = Field(default="cam0", min_length=1, max_length=100)


class Correcao(BaseModel):
    veredito: str
    operador: str = Field(min_length=1, max_length=100)


class PontoDesenho(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class NovaZona(BaseModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    largura: int = Field(gt=0)                       # tamanho do quadro em que a zona foi desenhada
    altura: int = Field(gt=0)
    pontos: list[PontoDesenho]


@app.get("/health")
def health():
    return {"status": "ok", "kafka_habilitado": bool(kafka and kafka.enabled),
            "modo_demo": MODO_DEMO and not KAFKA_HABILITADO,
            "detectores": list(detectores),
            "calibracoes_carregadas": list(calibracoes.keys())}


@app.post("/partidas")
def criar(corpo: NovaPartida):
    return visao(nova_partida(corpo.time_a.strip(), corpo.time_b.strip(), corpo.source_id.strip()))


@app.get("/partidas/{pid}")
def ler(pid: str):
    return visao(buscar(pid))


@app.post("/partidas/{pid}/encerrar")
def encerrar(pid: str):
    p = buscar(pid)
    p["encerrada"] = True
    return mudou(p)


@app.post("/decisoes/{did}/correcao")
def corrigir(did: str, corpo: Correcao):
    if corpo.veredito not in VEREDITOS:
        raise HTTPException(422, f"veredito deve ser um de {VEREDITOS}")
    p, d = buscar_decisao(did)
    if p["encerrada"]:
        raise HTTPException(409, "partida encerrada; não é possível corrigir decisões")
    if d["anulada"]:
        raise HTTPException(409, "lance anulado; não é possível corrigi-lo")
    if d["origem"] == "automatica" and d["veredito_automatico"] is None:
        d["veredito_automatico"] = d["veredito"]
    d.update(veredito=corpo.veredito, origem="corrigida", operador=corpo.operador.strip())
    mudou(p)
    return d


@app.post("/pontos/{did}/desfazer")
def desfazer(did: str):
    p, d = buscar_decisao(did)
    if p["encerrada"]:
        raise HTTPException(409, "partida encerrada; não é possível desfazer pontos")
    if d["anulada"]:
        raise HTTPException(409, "este lance já foi desfeito")
    d["anulada"] = True
    mudou(p)
    return visao(p)


@app.get("/p6/video")
def video_p6():
    """Pseudo-P6: a gravação para o player do A4. Na 6c o vídeo fica fora do barramento."""
    if not P6_VIDEO.is_file():
        raise HTTPException(404, f"Pseudo-P6 sem vídeo: {P6_VIDEO} não existe. Aponte A4_P6_VIDEO para um .mp4.")
    return FileResponse(P6_VIDEO, media_type="video/mp4")


@app.get("/p6/deteccoes")
def deteccoes_do_p6(de: float, ate: float):
    """bolas do S1 entre de e ate (segundos do video), para a sobreposicao do player"""
    i = bisect.bisect_left(deteccoes_p6, de, key=lambda d: d[0])
    j = bisect.bisect_right(deteccoes_p6, ate, key=lambda d: d[0])
    return [{"t": t, "bolas": bolas} for t, bolas in deteccoes_p6[i:j]]


@app.post("/decisoes/{did}/replay")
def replay(did: str):
    """6c (A4): o replay da jogada é um clipe do S4, pedido por ods.s4.capture.command. O clipe
    chega por ods.s4.clip e aparece no lance; até lá, a tela salta na gravação que já toca."""
    _, d = buscar_decisao(did)
    if not kafka or not kafka.enabled:
        raise HTTPException(503, "Sem barramento: o replay fica na gravação local.")
    t = datetime.fromisoformat(d["instante"].replace("Z", "+00:00"))
    janela = [(t + timedelta(seconds=s)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
              for s in (-REPLAY_ANTES_S, REPLAY_DEPOIS_S)]
    try:
        pedido = kafka.pedir_clipe(d["source_id"], *janela, f"lance {did}")
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    clipes_pedidos[pedido] = did
    return {"pedido": pedido, "start_at": janela[0], "end_at": janela[1]}


@app.get("/p6")
def estado_p6():
    """O que o player precisa: qual vídeo (muda o nome, o player recarrega) e a sessão de replay
    em curso, a que alinha o player à câmera e faz o lance cair em instante - started_at."""
    video = f"{P6_VIDEO.name}-{P6_VIDEO.stat().st_size}" if P6_VIDEO.is_file() else None
    return {"video": video, "sessao": sessao_p6}


@app.get("/camera/estado")
def estado_camera():
    if not kafka or not kafka.enabled:
        return {"conectado": False, "disponivel": False, "estado_recebido": False,
                "pan_deg": 0.0, "tilt_deg": 0.0, "atualizado_em": None, "topico": "ods.p7.state",
                "mensagem": "Kafka/P7 não configurado. Ative A4_KAFKA_ENABLED=true no backend."}
    return kafka.estado_camera()


@app.post("/camera/enquadrar")
def enquadrar(pan_deg: float = 0.0, tilt_deg: float = 0.0):
    if not (-90 <= pan_deg <= 90):                    # faixas do ods.p7.move.command (6c)
        raise HTTPException(422, "pan_deg deve estar entre -90 e 90 graus")
    if not (-45 <= tilt_deg <= 45):
        raise HTTPException(422, "tilt_deg deve estar entre -45 e 45 graus")
    if not kafka or not kafka.enabled:
        raise HTTPException(503, "Integração P7 indisponível. Configure A4_KAFKA_ENABLED=true e reinicie o backend.")
    try:
        return kafka.mover_camera(pan_deg, tilt_deg)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/zonas/{source_id}")
def ler_zona(source_id: str):
    cal = calibracoes.get(source_id)
    return {"calibracao": cal.versao if cal else None, "zona": registro.resumo(source_id),
            "versoes": registro.versoes(source_id)}


@app.post("/zonas")
def salvar_zona(corpo: NovaZona):
    """Converte o desenho para metros, grava a nova versão de ZONES e anuncia no barramento."""
    cal = calibracoes.get(corpo.source_id)
    if cal is None:
        raise HTTPException(409, f"Sem calibração do I3 para {corpo.source_id}; não dá para converter a zona em metros.")
    pontos = [(p.x, p.y) for p in corpo.pontos]
    try:
        poligono = pontos_para_metros(cal, pontos, corpo.largura, corpo.altura)
        validar_quadra(poligono)
    except ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from exc
    return gravar_zona(cal, poligono)


@app.post("/zonas/{source_id}/{versao}/usar")
def usar_zona(source_id: str, versao: str):
    """Volta uma zona antiga como versão nova: a mais nova continua sendo a que vale para a
    regra, para o S1 e depois de reiniciar o back."""
    cal = calibracoes.get(source_id)
    if cal is None:
        raise HTTPException(409, f"Sem calibração do I3 para {source_id}; não dá para publicar a zona.")
    antiga = next((v for v in registro.versoes(source_id) if v["artifact_version"] == versao), None)
    if antiga is None:
        raise HTTPException(404, f"zona {versao} nao existe para {source_id}")
    return gravar_zona(cal, [tuple(p) for p in antiga["poligono_m"]])


def gravar_zona(cal, poligono):
    """a quadra e configuracao do proprio A4 (regra de dentro e fora): na 6c o A4 nao produz
    ZONES, entao a versao fica no registro local e nao e anunciada no barramento"""
    registro.salvar(cal, poligono)
    avisos = ["Vale para os próximos lances."]
    erro_cm = erro_quadra_cm(poligono)
    if erro_cm > TOLERANCIA_CM:
        avisos.insert(0, f"O desenho foge {erro_cm:.0f} cm de 18 × 9 m: confira os cantos, senão muitos lances viram dúvida.")
    return registro.resumo(cal.source_id) | {"aviso": " ".join(avisos)}


@app.get("/eventos")
async def eventos(partida: str, request: Request):
    """SSE: envia a partida inteira sempre que houver uma mudança."""
    p = buscar(partida)

    async def stream():
        visto = -1
        while not await request.is_disconnected():
            if p["versao"] != visto:
                visto = p["versao"]
                yield f"event: partida\ndata: {json.dumps(visao(p))}\n\n"
            await asyncio.sleep(0.3)
    return StreamingResponse(stream(), media_type="text/event-stream")
