"""python test_i1_comando.py -- partida ao vivo pede e segura a vez do I1; encerrar solta"""
import os
import tempfile

os.environ.setdefault("A4_DADOS_DIR", tempfile.mkdtemp())  # as partidas do teste nao vao para back/dados

import main
from kafka_bridge import I1_SQUAD, TOPICO_COMANDO_I1, KafkaBridge


class Barramento:
    enabled = True

    def __init__(self):
        self.enviados = []

    def comandar_i1(self, acao):
        self.enviados.append(acao)


main.kafka = Barramento()
main.nova_partida(pid="demo")
assert not main.ao_vivo(), "a partida demo da tela nao pede o I1"

a = main.criar(main.NovaPartida())
b = main.criar(main.NovaPartida())
assert main.kafka.enviados == ["START", "START"] and main.ao_vivo()

main.encerrar(a["id"])
assert main.kafka.enviados[-1] == "START", "a outra partida ainda segura a vez"
main.encerrar(b["id"])
assert main.kafka.enviados[-1] == "STOP" and not main.ao_vivo()

# sem barramento a partida abre igual
main.kafka = None
assert not main.criar(main.NovaPartida())["encerrada"]

# o envelope que o orquestrador do I1 le: acao e equipe no payload; a camera fica com o I1
env = KafkaBridge.comando(TOPICO_COMANDO_I1, "I1", {"action": "START", "squad": I1_SQUAD})
assert env["schema"] == "ods.i1.command" and env["payload"] == {"action": "START", "squad": "INV1"}
print("comando do I1 ok")
