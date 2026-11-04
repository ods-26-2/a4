"""python test_rastros.py -- posicao da bola do s1 vira lance na partida aberta da camera

complementa o test_integracao_s1.py: instante sub-quadro, quique lento, outra camera e
sessao nova no meio do quique
"""
import uuid
from datetime import datetime, timezone

import main
from arbitragem import Detector

T0 = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc).timestamp()   # epoch, como no barramento
TC = T0 + 0.512                                     # quique entre dois quadros


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds") \
        .replace("+00:00", "Z")


def epoch(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).timestamp()


def quadro(n, fonte="cam0", curva=10000):
    """ods.s1.position com a bola a 10 m/s em x; na imagem desce ate v = 450 no quique e sobe
    de novo, a ~10 m/s com curva 10000 (1 px = 1 cm); curva 2000 e ~4 m/s, o sacador quicando"""
    t = T0 + n / 30
    u, v = 1200 + 1000 * (t - TC), 450 - curva * (t - TC) ** 2
    return {"message_id": str(uuid.uuid4()), "schema": "ods.s1.position", "source_id": fonte,
            "session_id": "s-1", "captured_at": iso(t),
            "payload": {"frame_index": n, "positions": [
                {"track_id": "t-ball-0001", "class": "ball", "point_px": [u, v]}]}}


def lances(p, quadros):
    antes = len(p["decisoes"])
    for ev in quadros:
        main.receber_posicao_s1(ev)
    return p["decisoes"][antes:]


main.detector = Detector()
p = main.nova_partida(source_id="cam0")
quique = [quadro(n) for n in range(31)]             # 1 s de bola, quique no quadro ~15

assert lances(p, quique) == [], "sem calibracao do i3 nao pode sair lance"

# homografia simples: 1 px = 1 cm, entao o quique cai em (12, 4.5) m, lado B
main.receber_calibracao_i3({
    "source_id": "cam0", "artifact_version": "cal-cam0-1", "payload": {
        "intrinsics": {"fx": 1000, "fy": 1000, "cx": 640, "cy": 360},
        "distortion": [0, 0, 0, 0, 0], "reprojection_rms_cm": 4.0,
        "homography_px_to_m": [[0.01, 0, 0], [0, 0.01, 0], [0, 0, 1]]}})
(d,) = lances(p, quique)
assert (d["veredito"], d["lado"], d["artifact_version"]) == ("dentro", "B", "cal-cam0-1"), d
assert abs(d["position_m"][0] - 12) < 0.05 and abs(d["position_m"][1] - 4.5) < 0.05, d
assert abs(epoch(d["instante"]) - TC) < 0.005, "instante do quique tem que ser sub-quadro"

assert lances(p, [quadro(n, curva=2000) for n in range(31)]) == [], \
    "quique lento (bola parada, sacador quicando) nao pode virar lance"

assert lances(main.nova_partida(source_id="cam0"), [quadro(n, fonte="cam9") for n in range(31)]) == [], \
    "posicao de outra camera nao pode cair nesta partida"

# sessao nova no meio do quique: os track_id antigos nao valem, o quique nao fecha
p = main.nova_partida(source_id="cam0")
lances(p, quique[:14])
main.receber_sessao({"session_id": "s-2", "payload": {"sources": ["cam0"]}})
assert lances(p, quique[14:]) == [], "ods.session.started tem que zerar o quique em andamento"

print("rastros ok")
