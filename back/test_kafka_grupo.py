"""python test_kafka_grupo.py -- cada back do A4 no seu grupo, e o fluxo lido do fim"""
import os

from confluent_kafka import OFFSET_BEGINNING, OFFSET_END

import kafka_bridge
from kafka_bridge import (TOPICO_CALIBRACAO, TOPICO_CLIPE_S4, TOPICO_ESTADO_P7, TOPICO_POSICAO, TOPICO_SESSAO,
                          KafkaBridge, posicionar)


class Particao:
    def __init__(self, topic):
        self.topic, self.offset = topic, None


class Consumidor:
    def assign(self, particoes):
        self.atribuidas = particoes


c = Consumidor()
posicionar(c, [Particao(t) for t in (TOPICO_CALIBRACAO, TOPICO_SESSAO, TOPICO_POSICAO, TOPICO_ESTADO_P7, TOPICO_CLIPE_S4)])
offsets = {p.topic: p.offset for p in c.atribuidas}
assert offsets[TOPICO_CALIBRACAO] == offsets[TOPICO_SESSAO] == OFFSET_BEGINNING, "artefato retido: do comeco"
assert offsets[TOPICO_POSICAO] == offsets[TOPICO_ESTADO_P7] == offsets[TOPICO_CLIPE_S4] == OFFSET_END, \
    "posicao velha nao pode virar lance depois de reiniciar"

# dois backs no mesmo broker nao dividem particoes
os.environ.pop("A4_KAFKA_GROUP_ID", None)
assert KafkaBridge().grupo != KafkaBridge().grupo
os.environ["A4_KAFKA_GROUP_ID"] = "A4-fixo"
assert KafkaBridge().grupo == "A4-fixo", "a build pode fixar o grupo"
os.environ.pop("A4_KAFKA_GROUP_ID")

# sem broker configurado nao ha endereco padrao
os.environ.pop("A4_KAFKA_BOOTSTRAP_SERVERS", None)
try:
    KafkaBridge().start()
    raise AssertionError("subiu sem broker")
except RuntimeError as exc:
    assert "A4_KAFKA_BOOTSTRAP_SERVERS" in str(exc)
assert not hasattr(kafka_bridge, "BROKER_PADRAO")
print("grupo e offsets do kafka ok")
