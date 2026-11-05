"""Integração opcional do A4 com o barramento Kafka do ODS.

Ative com A4_KAFKA_ENABLED=true. O frontend nunca acessa Kafka diretamente:
este módulo publica comandos do P7 e pedidos de clipe ao S4, e consome estado do P7, clipes do
S4, calibração do I3, posição do S1 e início de sessão. O lance é decidido aqui no A4 (6c), não chega pronto.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger("a4.kafka")

TOPICO_COMANDO_P7 = "ods.p7.move.command"
TOPICO_ESTADO_P7 = "ods.p7.state"
TOPICO_CALIBRACAO = "ods.i3.calibration"
TOPICO_POSICAO = "ods.s1.position"
TOPICO_SESSAO = "ods.session.started"
TOPICO_CAPTURA_S4 = "ods.s4.capture.command"
TOPICO_CLIPE_S4 = "ods.s4.clip"
P7_SOURCE_ID = os.getenv("A4_P7_SOURCE_ID", "pt0")        # mecanismo pan-tilt do A4 (6c)
CAMPOS_ENVELOPE = ("message_id", "message_type", "schema", "schema_version", "producer", "payload")
VERSAO_SUPORTADA = "1."
MAX_VISTOS = 5000
# artefatos retidos: lidos do começo a cada partida, senão o A4 que sobe depois do I3 (ou da câmera)
# fica sem calibração ou sem sessão. o resto (posição, estado do P7, clipes) é fluxo: do fim em diante
DO_COMECO = (TOPICO_CALIBRACAO, TOPICO_SESSAO)


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def posicionar(consumer, particoes) -> None:
    """on_assign: calibração e sessão do começo, o resto do fim. Do fim, e não do offset salvo:
    o back que reinicia não reprocessa posições velhas, que virariam lances de outro momento"""
    from confluent_kafka import OFFSET_BEGINNING, OFFSET_END
    for p in particoes:
        p.offset = OFFSET_BEGINNING if p.topic in DO_COMECO else OFFSET_END
    consumer.assign(particoes)


def motivo_invalido(envelope: Any, schema: str) -> str | None:
    """Validação do guia do Kafka (4.3): devolve o motivo para descartar, ou None se está certo."""
    if not isinstance(envelope, dict):
        return "mensagem não é um objeto"
    for campo in CAMPOS_ENVELOPE:
        if campo not in envelope:
            return f"campo obrigatório ausente: {campo}"
    if envelope["schema"] != schema:
        return f"schema inesperado: {envelope['schema']}"
    if not str(envelope["schema_version"]).startswith(VERSAO_SUPORTADA):
        return f"versão não suportada: {envelope['schema_version']}"
    if not isinstance(envelope["payload"], dict):
        return "payload não é um objeto"
    return None


class KafkaBridge:
    """Producer/consumer em thread dedicada; a aplicação continua utilizável sem Kafka."""

    def __init__(
        self,
        ao_receber_calibracao: Callable[[dict[str, Any]], None] | None = None,
        ao_receber_posicao: Callable[[dict[str, Any]], None] | None = None,
        ao_receber_sessao: Callable[[dict[str, Any]], None] | None = None,
        ao_receber_clipe: Callable[[dict[str, Any]], None] | None = None,
    ):
        # sem endereço embutido: o broker é configuração da build (local, Jetson 172.18.4.56:9092...)
        self.bootstrap = os.getenv("A4_KAFKA_BOOTSTRAP_SERVERS")
        # grupo próprio por instância: no broker compartilhado, dois backs do A4 no mesmo grupo
        # dividiriam as partições e cada um veria só parte das posições
        self.grupo = os.getenv("A4_KAFKA_GROUP_ID") or f"A4-{uuid.uuid4().hex[:8]}"
        self._ao_receber = {topico: f for topico, f in ((TOPICO_CALIBRACAO, ao_receber_calibracao),
                            (TOPICO_POSICAO, ao_receber_posicao), (TOPICO_SESSAO, ao_receber_sessao),
                            (TOPICO_CLIPE_S4, ao_receber_clipe)) if f}
        self._vistos: OrderedDict[str, None] = OrderedDict()
        self._producer = None
        self._consumer = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._camera_state: dict[str, Any] = {
            "conectado": False,
            "disponivel": False,
            "estado_recebido": False,
            "pan_deg": 0.0,
            "tilt_deg": 0.0,
            "atualizado_em": None,
            "mensagem": "Aguardando estado de ods.p7.state",
        }
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self.bootstrap:
            raise RuntimeError("A4_KAFKA_BOOTSTRAP_SERVERS não definido; o A4 não tem broker padrão")
        try:
            from confluent_kafka import Consumer, Producer
        except ImportError as exc:
            raise RuntimeError(
                "Kafka habilitado, mas confluent-kafka não está instalado. "
                "Execute: pip install -r requirements.txt"
            ) from exc

        self._producer = Producer({
            "bootstrap.servers": self.bootstrap,
            "client.id": "A4-score-camera",
            "enable.idempotence": True,
        })
        self._consumer = Consumer({
            "bootstrap.servers": self.bootstrap,
            "group.id": self.grupo,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        })
        topicos = [TOPICO_ESTADO_P7, *self._ao_receber]
        self._consumer.subscribe(topicos, on_assign=posicionar)
        self._enabled = True
        with self._lock:
            self._camera_state.update({
                "conectado": True,
                "disponivel": True,
                "mensagem": "Kafka conectado; aguardando estado de ods.p7.state",
            })
        self._thread = threading.Thread(target=self._consumir, name="a4-kafka-consumer", daemon=True)
        self._thread.start()
        log.info("Kafka habilitado em %s, grupo %s; consumindo %s", self.bootstrap, self.grupo, topicos)

    def close(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        if self._producer is not None:
            self._producer.flush(3)
        if self._consumer is not None:
            self._consumer.close()
        self._enabled = False

    def estado_camera(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._camera_state) | {"topico": TOPICO_ESTADO_P7}

    @staticmethod
    def comando(schema: str, alvo: str, payload: dict[str, Any]) -> dict[str, Any]:
        """envelope de comando da 6c: os seis campos fixos e o target (perfil CMD)"""
        return {"message_type": "command", "message_id": str(uuid.uuid4()), "schema": schema,
                "schema_version": "1.0", "producer": "A4", "published_at": agora(), "target": alvo,
                "payload": payload}

    def _enviar(self, envelope: dict[str, Any], chave: str) -> None:
        if not self._enabled or self._producer is None:
            raise RuntimeError("Kafka não habilitado. Configure A4_KAFKA_ENABLED=true e reinicie o backend.")
        try:
            self._producer.produce(envelope["schema"], key=chave.encode("utf-8"),
                                   value=json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
            remaining = self._producer.flush(5)
            if remaining:
                raise RuntimeError(f"Kafka não confirmou o envio (mensagens pendentes: {remaining})")
        except Exception as exc:
            log.exception("Falha publicando %s", envelope["schema"])
            raise RuntimeError(f"Falha ao enviar {envelope['schema']}: {exc}") from exc

    def mover_camera(self, pan_deg: float, tilt_deg: float) -> dict[str, Any]:
        """ods.p7.move.command: ângulos absolutos; a conclusão vem por ods.p7.state"""
        envelope = self.comando(TOPICO_COMANDO_P7, "P7", {"source_id": P7_SOURCE_ID, "pan_deg": float(pan_deg),
                                                          "tilt_deg": float(tilt_deg)})
        self._enviar(envelope, P7_SOURCE_ID)
        return {"status": "ENVIADO", "command_id": envelope["message_id"], "pan_deg": float(pan_deg),
                "tilt_deg": float(tilt_deg), "topico": TOPICO_COMANDO_P7,
                "aviso": "Comando publicado; aguardando confirmação em ods.p7.state."}

    def pedir_clipe(self, source_id: str, inicio: str, fim: str, rotulo: str) -> str:
        """ods.s4.capture.command de um CLIP; o descritor volta por ods.s4.clip com
        correlation_id = message_id deste pedido, que é o que se devolve"""
        envelope = self.comando(TOPICO_CAPTURA_S4, "S4", {"source_id": source_id, "media_type": "CLIP",
                                                          "start_at": inicio, "end_at": fim, "label": rotulo})
        self._enviar(envelope, source_id)
        return envelope["message_id"]

    def _repetida(self, message_id: str) -> bool:
        """A mesma mensagem pode chegar duas vezes (guia do Kafka, 4.4)."""
        if message_id in self._vistos:
            return True
        self._vistos[message_id] = None
        if len(self._vistos) > MAX_VISTOS:
            self._vistos.popitem(last=False)
        return False

    def _tratar_contrato(self, topico: str, envelope: Any) -> None:
        """Calibração e posição: descarta e registra o que estiver fora do contrato."""
        motivo = motivo_invalido(envelope, topico)
        if motivo:
            log.warning("Mensagem descartada de %s: %s", topico, motivo)
            return
        destino = self._ao_receber[topico]
        if destino and not self._repetida(envelope["message_id"]):
            destino(envelope)

    def _consumir(self) -> None:
        assert self._consumer is not None
        while not self._stop.is_set():
            try:
                msg = self._consumer.poll(0.5)
                if msg is None:
                    continue
                if msg.error():
                    log.warning("Kafka consumer: %s", msg.error())
                    continue
                try:
                    envelope = json.loads(msg.value().decode("utf-8"))
                    if msg.topic() == TOPICO_ESTADO_P7:
                        self._atualizar_estado_camera(envelope)
                    elif msg.topic() in self._ao_receber:
                        self._tratar_contrato(msg.topic(), envelope)
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                    log.warning("Mensagem inválida em %s: %s", msg.topic(), exc)
                except Exception:
                    log.exception("Erro processando mensagem de %s", msg.topic())
            except Exception:
                log.exception("Erro no consumidor Kafka")

    def _atualizar_estado_camera(self, envelope: dict[str, Any]) -> None:
        if envelope.get("source_id", P7_SOURCE_ID) != P7_SOURCE_ID:
            return                                    # outro mecanismo no mesmo tópico
        payload = envelope.get("payload", envelope)
        pan = payload.get("pan_deg", payload.get("pan"))
        tilt = payload.get("tilt_deg", payload.get("tilt"))
        with self._lock:
            self._camera_state.update({
                "conectado": True,
                "disponivel": True,
                "estado_recebido": True,
                "pan_deg": float(pan) if pan is not None else self._camera_state["pan_deg"],
                "tilt_deg": float(tilt) if tilt is not None else self._camera_state["tilt_deg"],
                "atualizado_em": envelope.get("captured_at") or envelope.get("published_at") or agora(),
                "mensagem": payload.get("status", payload.get("state", "Estado recebido do P7")),
                "raw": payload,
            })
