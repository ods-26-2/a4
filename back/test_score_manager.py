"""Testes rápidos do Score Manager e do contrato do P7: python test_score_manager.py"""
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
normalizada = KafkaBridge._normalizar_decisao({
    "message_id": "msg-1", "schema": "ods.regra.evento_consolidado", "occurred_at": agora(),
    "payload": {"veredito": "dentro", "lado": "B", "source_id": "cam0", "track_id": "track-2"},
})
assert normalizada and normalizada["veredito"] == "dentro" and normalizada["lado"] == "B"
print("score manager e contratos P7 ok")
