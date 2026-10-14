"""mock da api do a4 -- o contrato da secao 5 do planejamento do sprint 3

    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

nao le kafka nem roda o rule engine: a cada INTERVALO_S segundos inventa um lance
na partida "demo", para o front ter o que mostrar. o placar sai sempre das decisoes,
entao corrigir ou desfazer um lance recalcula tudo.
"""
import asyncio
import json
import os
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

INTERVALO_S = float(os.getenv("A4_INTERVALO_S", "6"))
VEREDITOS = ("dentro", "fora", "duvida")

@asynccontextmanager
async def ciclo(_app):
    demo = nova_partida(pid="demo")

    async def gerar():
        while True:
            await asyncio.sleep(INTERVALO_S)
            if not demo["encerrada"]:
                lance_falso(demo)
    tarefa = asyncio.create_task(gerar())
    yield
    tarefa.cancel()


app = FastAPI(title="A4 · mock da api de arbitragem", lifespan=ciclo)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

partidas = {}


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nova_partida(time_a="Time A", time_b="Time B", source_id="cam0", pid=None):
    p = {"id": pid or str(uuid.uuid4()), "time_a": time_a, "time_b": time_b,
         "source_id": source_id, "encerrada": False, "decisoes": [], "versao": 0}
    partidas[p["id"]] = p
    return p


def ganhador(d):
    """lado A e onde a bola quicou: dentro do lado A e ponto do B, fora e ponto do A.
    duvida e lance anulado nao pontuam ate o arbitro decidir"""
    if d["anulada"] or d["veredito"] == "duvida":
        return None
    outro = "B" if d["lado"] == "A" else "A"
    return outro if d["veredito"] == "dentro" else d["lado"]


def placar(p):
    """volei: set a 25 com dois de vantagem, 5o set a 15"""
    sets, pts = {"A": 0, "B": 0}, {"A": 0, "B": 0}
    for d in p["decisoes"]:
        g = ganhador(d)
        if not g:
            continue
        pts[g] += 1
        alvo = 15 if sets["A"] + sets["B"] == 4 else 25
        if pts[g] >= alvo and pts[g] - pts["B" if g == "A" else "A"] >= 2:
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


def lance_falso(p):
    v = random.choices(VEREDITOS, weights=(5, 4, 1))[0]
    banda = round(random.uniform(8, 25), 1)
    dist = {"dentro": -random.uniform(banda, 150), "fora": random.uniform(banda, 150),
            "duvida": random.uniform(-banda, banda)}[v]
    p["decisoes"].append({
        "decisao_id": str(uuid.uuid4()), "veredito": v, "distancia_cm": round(dist, 1),
        "banda_cm": banda, "lado": random.choice("AB"), "track_id": f"t-{random.randint(1, 999):04d}",
        "source_id": p["source_id"], "artifact_version": f"cal-{p['source_id']}-3",
        "origem": "automatica", "operador": None, "veredito_automatico": None,
        "anulada": False, "instante": agora()})
    mudou(p)


class NovaPartida(BaseModel):
    time_a: str = "Time A"
    time_b: str = "Time B"
    source_id: str = "cam0"


class Correcao(BaseModel):
    veredito: str
    operador: str


@app.post("/partidas")
def criar(corpo: NovaPartida):
    return visao(nova_partida(corpo.time_a, corpo.time_b, corpo.source_id))


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
    if d["origem"] == "automatica":
        d["veredito_automatico"] = d["veredito"]
    d.update(veredito=corpo.veredito, origem="corrigida", operador=corpo.operador)
    mudou(p)
    return d


@app.post("/pontos/{did}/desfazer")
def desfazer(did: str):
    p, d = buscar_decisao(did)
    d["anulada"] = True
    return mudou(p)


@app.post("/decisoes/{did}/replay")
def replay(did: str):
    buscar_decisao(did)
    return {"clip_id": None, "aviso": "mock: replay depende do S4"}


@app.post("/camera/enquadrar")
def enquadrar(pan_deg: float = 0.0, tilt_deg: float = 0.0):
    return {"status": "OK", "pan_deg": pan_deg, "tilt_deg": tilt_deg, "aviso": "mock: sem P7"}


@app.get("/eventos")
async def eventos(partida: str, request: Request):
    """sse: manda a partida inteira sempre que ela muda"""
    p = buscar(partida)

    async def stream():
        visto = -1
        while not await request.is_disconnected():
            if p["versao"] != visto:
                visto = p["versao"]
                yield f"event: partida\ndata: {json.dumps(visao(p))}\n\n"
            await asyncio.sleep(0.3)
    return StreamingResponse(stream(), media_type="text/event-stream")
