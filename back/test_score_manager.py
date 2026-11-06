"""Testes rápidos do Score Manager e do contrato do P7: python test_score_manager.py"""
import os
import tempfile

os.environ.setdefault("A4_DADOS_DIR", tempfile.mkdtemp())  # as partidas do teste nao vao para back/dados

from kafka_bridge import KafkaBridge, TOPICO_COMANDO_P7, TOPICO_ESTADO_P7
from main import Correcao, adicionar_decisao, agora, corrigir, desfazer, nova_partida, placar


def decisao(did, veredito="fora", lado="A"):
    return {
        "decisao_id": did, "veredito": veredito, "distancia_cm": 12.0,
        "banda_cm": 3.0, "lado": lado, "track_id": "track-1", "source_id": "cam0",
        "artifact_version": "cal-cam0-3", "origem": "automatica", "operador": None,
        "veredito_automatico": None, "anulada": False, "instante": agora(),
    }


p = nova_partida("A", "B", "cam0", pid="score-manager-test")
assert adicionar_decisao(p, decisao("d1"))
assert not adicionar_decisao(p, decisao("d1")), "mensagem duplicada não deve duplicar ponto"
assert placar(p)["pontos"] == {"A": 1, "B": 0}

corrigir("d1", Correcao(veredito="dentro", operador="arbitro-teste"))
assert placar(p)["pontos"] == {"A": 0, "B": 1}, "correção manual deve recalcular o placar"
assert p["decisoes"][0]["veredito_automatico"] == "fora"

desfazer("d1")
assert placar(p)["pontos"] == {"A": 0, "B": 0}, "desfazer deve anular o ponto"

assert TOPICO_COMANDO_P7 == "ods.p7.move.command"
assert TOPICO_ESTADO_P7 == "ods.p7.state"
print("score manager e contratos P7 ok")

# 6c, perfil CMD: os seis campos fixos e o target; P7 com o mecanismo e os angulos absolutos
cmd = KafkaBridge.comando("ods.p7.move.command", "P7", {"source_id": "pt0", "pan_deg": 12.5, "tilt_deg": -8.0})
assert {"message_type", "message_id", "schema", "schema_version", "producer", "published_at", "target"} <= set(cmd), cmd
assert cmd["target"] == "P7" and cmd["payload"]["source_id"] == "pt0", cmd

# replay: o ods.s4.clip do pedido (correlation_id) entra no lance, com a URL da midia
import main
main.S4_MIDIA_URL = "http://s4.local:18084"
p = nova_partida(source_id="cam0")
adicionar_decisao(p, decisao("d-replay", "fora", "A"))
main.clipes_pedidos["pedido-1"] = "d-replay"
main.receber_clipe({"correlation_id": "pedido-1", "payload": {
    "clip_id": "c-1", "media_type": "CLIP", "media_uri": "s4://clips/2026/11/04/c-1.mp4",
    "start_at": "2026-11-04T01:00:00.000Z", "end_at": "2026-11-04T01:00:05.000Z",
    "hash_sha256": "0" * 64, "expires_at": "2026-12-04T01:00:05.000Z"}})
clip = next(d for d in p["decisoes"] if d["decisao_id"] == "d-replay")["clip"]
assert clip["url"] == "http://s4.local:18084/api/v1/clips/c-1/media" and "pedido-1" not in main.clipes_pedidos, clip
print("comandos 6c e replay do S4 ok")
