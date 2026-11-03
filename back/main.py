"""API do A4: Score Manager, correção manual, anulação e integração opcional com P7/Kafka.

Desenvolvimento local (sem Kafka):
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Integração real: configure A4_KAFKA_ENABLED=true e A4_KAFKA_BOOTSTRAP_SERVERS.
O frontend conversa somente com esta API; nunca acessa Kafka diretamente.
"""
import asyncio
import json
import logging
import os
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from arbitragem import Detector, calibracao
from kafka_bridge import KafkaBridge
from zonas import (TOLERANCIA_CM, TOPICO_PUBLICADO, Registro, ZonaInvalida, erro_quadra_cm,
                   mensagem_publicada, pontos_para_metros, validar_quadra)

logging.basicConfig(level=os.getenv("A4_LOG_LEVEL", "INFO"))
log = logging.getLogger("a4")

INTERVALO_S = float(os.getenv("A4_INTERVALO_S", "6"))
MODO_DEMO = os.getenv("A4_MODO_DEMO", "true").lower() in {"1", "true", "yes", "sim"}
KAFKA_HABILITADO = os.getenv("A4_KAFKA_ENABLED", "false").lower() in {"1", "true", "yes", "sim"}
VEREDITOS = ("dentro", "fora", "duvida")
CALIBRACAO_ARQUIVO = os.getenv("A4_CALIBRACAO_ARQUIVO")

partidas: dict[str, dict[str, Any]] = {}
kafka: KafkaBridge | None = None
registro = Registro()
calibracoes: dict[str, Any] = {}                     # source_id -> Calibracao mais recente
detectores: dict[str, tuple[str, Detector]] = {}     # source_id -> (session_id, Detector)


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nova_partida(time_a="Time A", time_b="Time B", source_id="cam0", pid=None):
    p = {"id": pid or str(uuid.uuid4()), "time_a": time_a, "time_b": time_b,
         "source_id": source_id, "encerrada": False, "decisoes": [], "versao": 0}
    partidas[p["id"]] = p
    return p


def ganhador(d):
    """Dentro no lado A dá ponto ao B; fora dá ponto ao lado onde quicou."""
    if d["anulada"] or d["veredito"] == "duvida":
        return None
    outro = "B" if d["lado"] == "A" else "A"
    return outro if d["veredito"] == "dentro" else d["lado"]


def placar(p):
    """Calcula o placar do zero a partir das decisões válidas, inclusive após correções.

    Vôlei: sets a 25 com dois de vantagem; 5º set a 15. O estado é derivado,
    nunca incrementado por efeitos colaterais, então corrigir/anular lance antigo
    recalcula corretamente o placar inteiro.
    """
    sets, pts = {"A": 0, "B": 0}, {"A": 0, "B": 0}
    for d in p["decisoes"]:
        g = ganhador(d)
        if not g:
            continue
        pts[g] += 1
        alvo = 15 if sets["A"] + sets["B"] == 4 else 25
        outro = "B" if g == "A" else "A"
        if pts[g] >= alvo and pts[g] - pts[outro] >= 2:
            sets[g] += 1
            pts = {"A": 0, "B": 0}
    return {"sets": sets, "pontos": pts}


def visao(p):
    return {k: v for k, v in p.items() if k != "versao"} | {"placar": placar(p)}


def buscar(pid):
    if pid not in partidas:
        raise HTTPException(404, f"partida {pid} nao existe")
    return partidas[pid]


def buscar_decisao(did):
    for p in partidas.values():
        for d in p["decisoes"]:
            if d["decisao_id"] == did:
                return p, d
    raise HTTPException(404, f"decisao {did} nao existe")


def mudou(p):
    p["versao"] += 1
    return visao(p)


def adicionar_decisao(p, decisao):
    """Adiciona uma decisão de forma idempotente por decisao_id."""
    if p["encerrada"]:
        return False
    if any(d["decisao_id"] == decisao["decisao_id"] for d in p["decisoes"]):
        return False
    decisao.setdefault("origem", "automatica")
    decisao.setdefault("operador", None)
    decisao.setdefault("veredito_automatico", None)
    decisao.setdefault("anulada", False)
    decisao.setdefault("instante", agora())
    p["decisoes"].append(decisao)
    mudou(p)
    return True


def receber_decisao_automatica(decisao: dict[str, Any]):
    """Recebe uma decisão do tópico ods.regra.evento_consolidado."""
    source_id = str(decisao.get("source_id", "cam0"))
    # A decisão vai para a partida aberta mais recente associada à câmera de origem.
    candidatas = [p for p in partidas.values() if not p["encerrada"] and p["source_id"] == source_id]
    if not candidatas:
        log.warning("Decisão automática ignorada: nenhuma partida aberta para source_id=%s", source_id)
        return
    p = candidatas[-1]
    if adicionar_decisao(p, decisao):
        log.info("Decisão automática %s adicionada à partida %s", decisao.get("decisao_id"), p["id"])


def receber_calibracao(envelope: dict[str, Any]):
    """Recebe ods.i3.calibration; a mais nova substitui a anterior da mesma câmera."""
    cal = calibracao(envelope)
    calibracoes[cal.source_id] = cal
    log.info("Calibração %s recebida para %s", cal.versao, cal.source_id)


def receber_posicao(envelope: dict[str, Any]):
    """Recebe ods.s1.position e passa a bola pela regra, usando a zona salva da câmera."""
    source_id = envelope["source_id"]
    # o barramento é compartilhado: só interessa a câmera de uma partida aberta aqui
    if not any(not p["encerrada"] and p["source_id"] == source_id for p in partidas.values()):
        return
    cal = calibracoes.get(source_id)
    if cal is None:
        log.warning("Posição ignorada: sem calibração para source_id=%s", source_id)
        return
    sessao = envelope["session_id"]
    if detectores.get(source_id, (None,))[0] != sessao:
        detectores[source_id] = (sessao, Detector())  # sessão nova: os track_id antigos não valem
    detector = detectores[source_id][1]
    t_s = datetime.fromisoformat(envelope["captured_at"].replace("Z", "+00:00")).timestamp()
    for posicao in envelope["payload"]["positions"]:
        if posicao["class"] != "ball":
            continue
        decisao = detector.amostra(cal, posicao["track_id"], t_s, posicao["point_px"], registro.atual(source_id))
        if decisao:
            receber_decisao_automatica(decisao)


def lance_falso(p):
    """Gera lances fictícios apenas no modo demo local, nunca com Kafka habilitado."""
    v = random.choices(VEREDITOS, weights=(5, 4, 1))[0]
    banda = round(random.uniform(8, 25), 1)
    dist = {"dentro": -random.uniform(banda, 150), "fora": random.uniform(banda, 150),
            "duvida": random.uniform(-banda, banda)}[v]
    adicionar_decisao(p, {
        "decisao_id": str(uuid.uuid4()), "veredito": v, "distancia_cm": round(dist, 1),
        "banda_cm": banda, "lado": random.choice("AB"), "track_id": f"t-{random.randint(1, 999):04d}",
        "source_id": p["source_id"], "artifact_version": f"cal-{p['source_id']}-3", "zones_version": None,
        "origem": "automatica", "operador": None, "veredito_automatico": None,
        "anulada": False, "instante": agora()})


@asynccontextmanager
async def ciclo(_app):
    global kafka
    demo = nova_partida(pid="demo")
    tarefa = None
    registro.carregar()
    if CALIBRACAO_ARQUIVO:
        with open(CALIBRACAO_ARQUIVO, encoding="utf-8") as arquivo:
            conteudo = json.load(arquivo)
        for envelope in conteudo if isinstance(conteudo, list) else [conteudo]:
            receber_calibracao(envelope)
    if KAFKA_HABILITADO:
        kafka = KafkaBridge(receber_decisao_automatica, receber_calibracao, receber_posicao)
        try:
            kafka.start()
        except Exception:
            kafka = None
            log.exception("Não foi possível iniciar a integração Kafka; API seguirá sem barramento")
    elif MODO_DEMO:
        async def gerar():
            while True:
                await asyncio.sleep(INTERVALO_S)
                if not demo["encerrada"]:
                    lance_falso(demo)
        tarefa = asyncio.create_task(gerar())
        log.warning("Modo demo ativo: decisões fictícias serão geradas. Defina A4_MODO_DEMO=false para desligar.")
    try:
        yield
    finally:
        if tarefa:
            tarefa.cancel()
            try:
                await tarefa
            except asyncio.CancelledError:
                pass
        if kafka:
            kafka.close()
            kafka = None


app = FastAPI(title="A4 · Score Manager e Camera Framing", lifespan=ciclo)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class NovaPartida(BaseModel):
    time_a: str = Field(default="Time A", min_length=1, max_length=80)
    time_b: str = Field(default="Time B", min_length=1, max_length=80)
    source_id: str = Field(default="cam0", min_length=1, max_length=100)


class Correcao(BaseModel):
    veredito: str
    operador: str = Field(min_length=1, max_length=100)


class PontoDesenho(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class NovaZona(BaseModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    largura: int = Field(gt=0)                       # tamanho do quadro em que a zona foi desenhada
    altura: int = Field(gt=0)
    pontos: list[PontoDesenho]


@app.get("/health")
def health():
    return {"status": "ok", "kafka_habilitado": bool(kafka and kafka.enabled),
            "modo_demo": MODO_DEMO and not KAFKA_HABILITADO}


@app.post("/partidas")
def criar(corpo: NovaPartida):
    return visao(nova_partida(corpo.time_a.strip(), corpo.time_b.strip(), corpo.source_id.strip()))


@app.get("/partidas/{pid}")
def ler(pid: str):
    return visao(buscar(pid))


@app.post("/partidas/{pid}/encerrar")
def encerrar(pid: str):
    p = buscar(pid)
    p["encerrada"] = True
    return mudou(p)


@app.post("/decisoes/{did}/correcao")
def corrigir(did: str, corpo: Correcao):
    if corpo.veredito not in VEREDITOS:
        raise HTTPException(422, f"veredito deve ser um de {VEREDITOS}")
    p, d = buscar_decisao(did)
    if p["encerrada"]:
        raise HTTPException(409, "partida encerrada; não é possível corrigir decisões")
    if d["anulada"]:
        raise HTTPException(409, "lance anulado; não é possível corrigi-lo")
    if d["origem"] == "automatica" and d["veredito_automatico"] is None:
        d["veredito_automatico"] = d["veredito"]
    d.update(veredito=corpo.veredito, origem="corrigida", operador=corpo.operador.strip())
    mudou(p)
    return d


@app.post("/pontos/{did}/desfazer")
def desfazer(did: str):
    p, d = buscar_decisao(did)
    if p["encerrada"]:
        raise HTTPException(409, "partida encerrada; não é possível desfazer pontos")
    if d["anulada"]:
        raise HTTPException(409, "este lance já foi desfeito")
    d["anulada"] = True
    mudou(p)
    return visao(p)


@app.post("/decisoes/{did}/replay")
def replay(did: str):
    buscar_decisao(did)
    return {"clip_id": None, "aviso": "Replay indisponível: integração com P6/S4 ainda não configurada."}


@app.get("/camera/estado")
def estado_camera():
    if not kafka or not kafka.enabled:
        return {"conectado": False, "disponivel": False, "estado_recebido": False,
                "pan_deg": 0.0, "tilt_deg": 0.0, "atualizado_em": None, "topico": "ods.p7.state",
                "mensagem": "Kafka/P7 não configurado. Ative A4_KAFKA_ENABLED=true no backend."}
    return kafka.estado_camera()


@app.post("/camera/enquadrar")
def enquadrar(pan_deg: float = 0.0, tilt_deg: float = 0.0):
    if not (-180 <= pan_deg <= 180):
        raise HTTPException(422, "pan_deg deve estar entre -180 e 180 graus")
    if not (-90 <= tilt_deg <= 90):
        raise HTTPException(422, "tilt_deg deve estar entre -90 e 90 graus")
    if not kafka or not kafka.enabled:
        raise HTTPException(503, "Integração P7 indisponível. Configure A4_KAFKA_ENABLED=true e reinicie o backend.")
    try:
        return kafka.mover_camera(pan_deg, tilt_deg)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/zonas/{source_id}")
def ler_zona(source_id: str):
    cal = calibracoes.get(source_id)
    return {"calibracao": cal.versao if cal else None, "zona": registro.resumo(source_id)}


@app.post("/zonas")
def salvar_zona(corpo: NovaZona):
    """Converte o desenho para metros, grava a nova versão de ZONES e anuncia no barramento."""
    cal = calibracoes.get(corpo.source_id)
    if cal is None:
        raise HTTPException(409, f"Sem calibração do I3 para {corpo.source_id}; não dá para converter a zona em metros.")
    pontos = [(p.x, p.y) for p in corpo.pontos]
    try:
        poligono = pontos_para_metros(cal, pontos, corpo.largura, corpo.altura)
        validar_quadra(poligono)
    except ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from exc
    descritor = registro.salvar(cal, poligono)
    avisos = ["Vale para os próximos lances. O S1 só aplica uma versão nova na próxima sessão."]
    erro_cm = erro_quadra_cm(poligono)
    if erro_cm > TOLERANCIA_CM:
        avisos.insert(0, f"O desenho foge {erro_cm:.0f} cm de 18 × 9 m: confira os cantos, senão muitos lances viram dúvida.")
    publicado = False
    if kafka and kafka.enabled:
        try:
            kafka.publicar_evento(TOPICO_PUBLICADO, descritor["artifact_id"], mensagem_publicada(descritor))
            publicado = True
        except Exception as exc:
            log.exception("Falha publicando %s", descritor["artifact_version"])
            avisos.insert(0, f"Zona salva, mas não anunciada no barramento: {exc}")
    else:
        avisos.append("Kafka desligado: a zona foi salva, mas não foi anunciada ao S1.")
    return registro.resumo(corpo.source_id) | {"aviso": " ".join(avisos), "publicado": publicado}


@app.get("/eventos")
async def eventos(partida: str, request: Request):
    """SSE: envia a partida inteira sempre que houver uma mudança."""
    p = buscar(partida)

    async def stream():
        visto = -1
        while not await request.is_disconnected():
            if p["versao"] != visto:
                visto = p["versao"]
                yield f"event: partida\ndata: {json.dumps(visao(p))}\n\n"
            await asyncio.sleep(0.3)
    return StreamingResponse(stream(), media_type="text/event-stream")
