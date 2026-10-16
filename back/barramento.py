"""consumo do barramento kafka do a4, no envelope comum da arquitetura 6c

roda numa thread, porque o confluent_kafka e bloqueante; cada mensagem valida vai para
o loop do fastapi. sem commit de offset: o a4 nao precisa retomar de onde parou.
"""
import collections
import json
import sys
import threading
import uuid

from confluent_kafka import OFFSET_BEGINNING, OFFSET_END, Consumer

CALIBRACAO = "ods.i3.calibration"
# artefato: quem chega depois le o que ja esta retido. o resto e fluxo, so dagora em diante
DO_COMECO = {CALIBRACAO}
FIXOS = ("message_type", "message_id", "schema", "schema_version", "producer",
         "published_at", "payload")


def ler(texto, topico):
    """json -> envelope valido ou None, com o motivo no stderr (guia b2, 4.3)"""
    try:
        ev = json.loads(texto)
    except (json.JSONDecodeError, UnicodeDecodeError):
        motivo = "json invalido"
    else:
        if not isinstance(ev, dict):
            motivo = "json nao e objeto"
        elif falta := [c for c in FIXOS if c not in ev]:
            motivo = f"campo obrigatorio ausente: {falta[0]}"
        elif ev["schema"] != topico:
            motivo = f"schema {ev['schema']} no topico {topico}"
        elif not str(ev["schema_version"]).startswith("1."):
            motivo = f"versao nao suportada: {ev['schema_version']}"
        else:
            return ev
    print(f"a4: mensagem descartada de {topico}: {motivo}", file=sys.stderr)
    return None


def consumir(kafka, topicos, loop, entregar):
    """assina os topicos e chama entregar(topico, envelope) no loop; devolve a parada"""
    # grupo proprio por processo: sem commit, o grupo nao guarda nada, e um grupo
    # compartilhado faria o a4 reiniciado esperar o antigo expirar (~45 s)
    consumidor = Consumer({"bootstrap.servers": kafka,
                           "group.id": f"A4-arbitragem-{uuid.uuid4().hex[:8]}",
                           "enable.auto.commit": False,
                           # topico criado depois do a4 subir aparece em 5 s, nao em 5 min
                           "topic.metadata.refresh.interval.ms": 5000})
    parar = threading.Event()

    def posicionar(c, particoes):
        for p in particoes:
            p.offset = OFFSET_BEGINNING if p.topic in DO_COMECO else OFFSET_END
        c.assign(particoes)

    def laco():
        # 6c: o consumidor descarta message_id que ja processou
        vistos, ordem = set(), collections.deque(maxlen=10_000)
        consumidor.subscribe(topicos, on_assign=posicionar)
        try:
            while not parar.is_set():
                msg = consumidor.poll(0.5)
                if msg is None or msg.error():
                    continue
                ev = ler(msg.value(), msg.topic())
                if ev is None or ev["message_id"] in vistos:
                    continue
                if len(ordem) == ordem.maxlen:
                    vistos.discard(ordem[0])
                ordem.append(ev["message_id"])
                vistos.add(ev["message_id"])
                loop.call_soon_threadsafe(entregar, msg.topic(), ev)
        finally:
            consumidor.close()

    threading.Thread(target=laco, name="a4-kafka", daemon=True).start()
    return parar.set
