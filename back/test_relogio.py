"""python test_relogio.py -- A4_RELOGIO_QUADRO: tempo pelo frame_index na camera listada, captured_at nas outras"""
import os
import tempfile

os.environ.setdefault("A4_DADOS_DIR", tempfile.mkdtemp())
os.environ["A4_RELOGIO_QUADRO"] = "INV1:30"

import main


def env(source_id, sessao, n, captured_at):
    return {"source_id": source_id, "session_id": sessao, "captured_at": captured_at,
            "payload": {"frame_index": n, "positions": []}}


assert main.RELOGIO_QUADRO == {"INV1": 30.0}
# o I1 carimba devagar (1 s real para 15 quadros): o relogio segue o video, 30 quadros = 1 s
t0 = main.tempo_do_quadro(env("INV1", "s1", 0, "2026-11-25T23:00:00.000Z"))
t30 = main.tempo_do_quadro(env("INV1", "s1", 30, "2026-11-25T23:00:02.000Z"))
assert abs(t30 - t0 - 1.0) < 1e-9, t30 - t0
# sessao nova recomeca a origem no primeiro quadro dela
t_novo = main.tempo_do_quadro(env("INV1", "s2", 0, "2026-11-25T23:05:00.000Z"))
assert abs(t_novo - t0 - 300.0) < 1e-9, t_novo - t0
# camera fora da lista: captured_at como na 6c
c0 = main.tempo_do_quadro(env("cam0", "s1", 0, "2026-11-25T23:00:00.000Z"))
c30 = main.tempo_do_quadro(env("cam0", "s1", 30, "2026-11-25T23:00:02.000Z"))
assert abs(c30 - c0 - 2.0) < 1e-9, c30 - c0
print("relogio ok")
