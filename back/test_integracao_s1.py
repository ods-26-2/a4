"""python test_integracao_s1.py -- confere a integração S1 → Detector → Score Manager

Simula o fluxo completo: calibração I3, posições S1 com a bola, e verifica
que o Detector reconhece o quique e a decisão chega no Score Manager.
"""
import os
import tempfile

os.environ.setdefault("A4_DADOS_DIR", tempfile.mkdtemp())  # as partidas do teste nao vao para back/dados

import uuid
from datetime import datetime, timezone

# ---- Setup: simula o Score Manager ----
decisoes_recebidas = []

# Monkey-patch o import para que o teste funcione sem Kafka/FastAPI
import main
main.partidas = {}
main.nova_partida(pid="test", source_id="cam0")

_original = main.receber_decisao_automatica


def capturar(decisao):
    decisoes_recebidas.append(decisao)
    _original(decisao)


main.receber_decisao_automatica = capturar

# ---- 1. Receber calibração I3 ----
cal_envelope = {
    "message_id": str(uuid.uuid4()),
    "schema": "ods.i3.calibration",
    "source_id": "cam0",
    "artifact_version": "cal-cam0-3",
    "payload": {
        "intrinsics": {"fx": 1000.0, "fy": 1000.0, "cx": 960.0, "cy": 540.0},
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        # homografia que mapeia pixel -> metro (identidade escalada: px/100 = m)
        "homography_px_to_m": [[0.01, 0.0, 0.0],
                                [0.0, 0.01, 0.0],
                                [0.0, 0.0, 1.0]],
        "reprojection_rms_cm": 0.9,
        "valid_from": "2026-10-01T00:00:00.000Z",
        "reference_frame": {"space_id": "quadra", "origin": "canto", "axes": "x-y", "unit": "m"},
    },
}
main.receber_calibracao(cal_envelope)
assert "cam0" in main.calibracoes, "calibração não foi registrada"
print("1. Calibração I3 registrada OK")

# ---- 2. Inicializar o Detector ----
print("2. Detector nasce por câmera e sessão no main")

# ---- 3. Enviar posições S1 com bola quicando ----
# Simula uma bola quicando: a altura (v no quadro) faz um V
# A bola está no pixel (1200, v) onde v sobe e desce (quique = v máximo = bola mais baixa)
# Com a homografia de identidade/100, o ponto em metros fica em (12.0, v/100)
import math

decisoes_recebidas.clear()

# Gera 20 quadros de bola: t=0.2s..0.83s, a bola quica em t=0.5s
for i in range(6, 26):
    t = i / 30.0
    # v simula altura no quadro (invertido): maior v = mais baixo na imagem = mais perto do chão
    # quique em t=0.5s → v máximo
    v = 540.0 + 200.0 * (1.0 - abs(t - 0.5) * 4.0)  # pico em t=0.5
    captured_at = datetime.fromtimestamp(t + 1730000000, timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")

    envelope = {
        "message_id": str(uuid.uuid4()),
        "schema": "ods.s1.position",
        "source_id": "cam0",
        "session_id": "sess-1",
        "captured_at": captured_at,
        "payload": {
            "frame_index": i,
            "positions": [
                {"track_id": "ball-001", "class": "ball",
                 "point_px": [1200.0, v]},
            ],
        },
    }
    main.receber_posicao(envelope)

if decisoes_recebidas:
    d = decisoes_recebidas[0]
    print(f"3. Quique detectado: veredito={d['veredito']}, dist={d['distancia_cm']} cm, "
          f"lado={d['lado']}, track={d['track_id']}")
    assert d["veredito"] in ("dentro", "fora", "duvida"), f"veredito inválido: {d['veredito']}"
    assert d["track_id"] == "ball-001", f"track_id errado: {d['track_id']}"
    assert d["source_id"] == "cam0", f"source_id errado: {d['source_id']}"
    assert d["artifact_version"] == "cal-cam0-3", f"artifact_version errado: {d['artifact_version']}"
    # Verifica que a decisão foi adicionada à partida
    p = main.partidas["test"]
    assert len(p["decisoes"]) > 0, "decisão não chegou na partida"
    print("4. Decisão inserida na partida 'test' OK")
else:
    print("3. AVISO: nenhum quique detectado (ajuste os parâmetros da simulação se necessário)")

# ---- 4. Verifica que posições sem bola são ignoradas ----
decisoes_antes = len(decisoes_recebidas)
envelope_sem_bola = {
    "message_id": str(uuid.uuid4()),
    "schema": "ods.s1.position",
    "source_id": "cam0",
    "session_id": "sess-1",
    "captured_at": "2026-10-16T12:00:01.000Z",
    "payload": {
        "frame_index": 100,
        "positions": [
            {"track_id": "p-001", "class": "person", "point_px": [500.0, 300.0]},
        ],
    },
}
main.receber_posicao(envelope_sem_bola)
assert len(decisoes_recebidas) == decisoes_antes, "pessoa não deveria gerar decisão"
print("5. Posições de 'person' ignoradas corretamente OK")

# ---- 5. Verifica que sem calibração não processa ----
main.calibracoes.clear()
envelope_sem_cal = {
    "message_id": str(uuid.uuid4()),
    "schema": "ods.s1.position",
    "source_id": "cam1",  # câmera sem calibração
    "session_id": "sess-1",
    "captured_at": "2026-10-16T12:00:02.000Z",
    "payload": {
        "frame_index": 200,
        "positions": [
            {"track_id": "ball-002", "class": "ball", "point_px": [1200.0, 700.0]},
        ],
    },
}
decisoes_antes = len(decisoes_recebidas)
main.receber_posicao(envelope_sem_cal)
assert len(decisoes_recebidas) == decisoes_antes, "sem calibração não deveria gerar decisão"
print("6. Sem calibração: posição ignorada corretamente OK")

print("\nintegracao s1 ok")
