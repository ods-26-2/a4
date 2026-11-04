"""python test_rastros.py -- posicao da bola do s1 vira lance na partida aberta da camera

o caminho do main: calibracao do i3, ods.s1.position por quadro, sessao nova no meio do voo,
outra camera e toque de jogador; a cena e a camera sintetica de cena_sintetica.py
"""
import uuid
from datetime import datetime, timezone

import cena_sintetica as cena
import main

T0 = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc).timestamp()   # epoch, como no barramento


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds") \
        .replace("+00:00", "Z")


def epoch(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).timestamp()


def envelopes(pontos, fonte="cam0", sessao="s-1"):
    """ods.s1.position de cada quadro, com bola ou sem, ate 1 s depois do ultimo ponto"""
    por_n = {round(t * cena.FPS): px for t, px in pontos}
    for n in range(min(por_n), max(por_n) + int(cena.FPS)):
        posicoes = [{"track_id": "t-ball-0001", "class": "ball", "point_px": list(por_n[n])}] if n in por_n else []
        yield {"message_id": str(uuid.uuid4()), "schema": "ods.s1.position", "source_id": fonte,
               "session_id": sessao, "captured_at": iso(T0 + n / cena.FPS),
               "payload": {"frame_index": n, "positions": posicoes}}


def lances(p, evs):
    antes = len(p["decisoes"])
    for ev in evs:
        main.receber_posicao(ev)
    return p["decisoes"][antes:]


QUIQUE = cena.pixels(cena.quique((12.0, 4.5), (6.0, 1.0, -9.0)))     # chao em t = 1 s
main.partidas.clear()
p = main.nova_partida(source_id="cam0")
assert lances(p, envelopes(QUIQUE)) == [], "sem calibracao do i3 nao pode sair lance"

main.receber_calibracao(cena.envelope())
(d,) = lances(main.nova_partida(source_id="cam0"), envelopes(QUIQUE, sessao="s-2"))
assert (d["veredito"], d["lado"], d["artifact_version"]) == ("dentro", "B", "cal-cam0-1"), d
assert abs(d["position_m"][0] - 12) < 0.15 and abs(d["position_m"][1] - 4.5) < 0.15, d
assert abs(epoch(d["instante"]) - (T0 + 1.0)) < 0.02, "instante do quique tem que ser sub-quadro"

manchete = cena.pixels(cena.toque((5.0, 4.0, 1.0), (4.0, 0.5, -6.0), (2.0, 0.0, 7.0)))
assert lances(main.nova_partida(source_id="cam0"), envelopes(manchete, sessao="s-3")) == [], \
    "toque de jogador no ar nao pode virar lance"

assert lances(main.nova_partida(source_id="cam0"), envelopes(QUIQUE, fonte="cam9", sessao="s-4")) == [], \
    "posicao de outra camera nao pode cair nesta partida"

# sessao nova no meio do voo: o que veio antes nao vale, o quique nao fecha
p = main.nova_partida(source_id="cam0")
evs = list(envelopes(QUIQUE, sessao="s-5"))
lances(p, evs[:20])
main.receber_sessao({"session_id": "s-6", "published_at": iso(T0), "payload": {"sources": ["cam0"], "started_at": iso(T0)}})
assert main.estado_p6()["sessao"]["started_at"] == iso(T0)
assert lances(p, evs[20:]) == [], "ods.session.started tem que zerar o voo em andamento"

print("rastros ok")
