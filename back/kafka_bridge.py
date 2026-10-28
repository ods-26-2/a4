"""Integração opcional do A4 com o barramento Kafka do ODS.

Ative com A4_KAFKA_ENABLED=true. O frontend nunca acessa Kafka diretamente:
este módulo publica comandos do P7 e consome estado do P7 e eventos consolidados da regra.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger("a4.kafka")

TOPICO_COMANDO_P7 = "ods.p7.move.command"
TOPICO_ESTADO_P7 = "ods.p7.state"
TOPICO_REGRA = os.getenv("A4_KAFKA_TOPIC_REGRA", "ods.regra.evento_consolidado")


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class KafkaBridge:
    """Producer/consumer em thread dedicada; a aplicação continua utilizável sem Kafka."""

    def __init__(self, ao_receber_decisao: Callable[[dict[str, Any]], None]):
        self.bootstrap = os.getenv("A4_KAFKA_BOOTSTRAP_SERVERS", "34.66.235.91:9093")
        self._ao_receber_decisao = ao_receber_decisao
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
            "group.id": os.getenv("A4_KAFKA_GROUP_ID", "A4-score-manager"),
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
        self._consumer.subscribe([TOPICO_ESTADO_P7, TOPICO_REGRA])
        self._enabled = True
        with self._lock:
            self._camera_state.update({
                "conectado": True,
                "disponivel": True,
                "mensagem": "Kafka conectado; aguardando estado de ods.p7.state",
            })
        self._thread = threading.Thread(target=self._consumir, name="a4-kafka-consumer", daemon=True)
        self._thread.start()
        log.info("Kafka habilitado em %s; consumindo %s e %s", self.bootstrap, TOPICO_ESTADO_P7, TOPICO_REGRA)

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

    def mover_camera(self, pan_deg: float, tilt_deg: float) -> dict[str, Any]:
        if not self._enabled or self._producer is None:
            raise RuntimeError("Integração P7 indisponível. Configure A4_KAFKA_ENABLED=true e reinicie o backend.")
        command_id = str(uuid.uuid4())
        envelope = {
            "message_id": command_id,
            "message_type": "command",
            "schema": TOPICO_COMANDO_P7,
            "schema_version": "1.0",
            "producer": "A4",
            "occurred_at": agora(),
            "payload": {
                "command_id": command_id,
                "pan_deg": float(pan_deg),
                "tilt_deg": float(tilt_deg),
            },
        }
        try:
            self._producer.produce(
                TOPICO_COMANDO_P7,
                key=command_id.encode("utf-8"),
                value=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            )
            remaining = self._producer.flush(5)
            if remaining:
                raise RuntimeError(f"Kafka não confirmou o envio do comando (mensagens pendentes: {remaining})")
        except Exception as exc:
            log.exception("Falha publicando comando P7")
            raise RuntimeError(f"Falha ao enviar comando para o P7: {exc}") from exc
        return {
            "status": "ENVIADO",
            "command_id": command_id,
            "pan_deg": float(pan_deg),
            "tilt_deg": float(tilt_deg),
            "topico": TOPICO_COMANDO_P7,
            "aviso": "Comando publicado; aguardando confirmação em ods.p7.state.",
        }

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
                    elif msg.topic() == TOPICO_REGRA:
                        decisao = self._normalizar_decisao(envelope)
                        if decisao:
                            self._ao_receber_decisao(decisao)
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                    log.warning("Mensagem inválida em %s: %s", msg.topic(), exc)
                except Exception:
                    log.exception("Erro processando mensagem de %s", msg.topic())
            except Exception:
                log.exception("Erro no consumidor Kafka")

    def _atualizar_estado_camera(self, envelope: dict[str, Any]) -> None:
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
                "atualizado_em": envelope.get("occurred_at") or envelope.get("published_at") or agora(),
                "mensagem": payload.get("status", payload.get("state", "Estado recebido do P7")),
                "raw": payload,
            })

    @staticmethod
    def _normalizar_decisao(envelope: dict[str, Any]) -> dict[str, Any] | None:
        """Aceita o envelope do tópico de regra e extrai a decisão A4.

        O produtor de S2 pode publicar a decisão diretamente no payload ou dentro de
        `decisao`/`decision`. Campos desconhecidos são ignorados.
        """
        payload = envelope.get("payload", envelope)
        if not isinstance(payload, dict):
            return None
        decisao = payload.get("decisao", payload.get("decision", payload))
        if not isinstance(decisao, dict):
            return None
        veredito = decisao.get("veredito", decisao.get("verdict"))
        if veredito not in {"dentro", "fora", "duvida"}:
            return None
        lado = decisao.get("lado", decisao.get("side"))
        if lado not in {"A", "B"}:
            log.warning("Evento de regra sem lado A/B; ignorado")
            return None
        return {
            "decisao_id": str(decisao.get("decisao_id") or decisao.get("decision_id") or envelope.get("message_id") or uuid.uuid4()),
            "veredito": veredito,
            "distancia_cm": float(decisao.get("distancia_cm", decisao.get("distance_cm", 0.0))),
            "banda_cm": float(decisao.get("banda_cm", decisao.get("uncertainty_cm", 0.0))),
            "lado": lado,
            "track_id": str(decisao.get("track_id", "desconhecido")),
            "source_id": str(decisao.get("source_id", payload.get("source_id", "cam0"))),
            "artifact_version": str(decisao.get("artifact_version", "desconhecida")),
            "origem": "automatica",
            "operador": None,
            "veredito_automatico": None,
            "anulada": False,
            "instante": decisao.get("instante") or decisao.get("occurred_at") or envelope.get("occurred_at") or agora(),
        }
