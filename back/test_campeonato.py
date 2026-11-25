"""python test_campeonato.py -- tabela todos contra todos, resultado dos jogos e ranking FIVB"""
import importlib
import os
import tempfile
from itertools import combinations

os.environ["A4_DADOS_DIR"] = tempfile.mkdtemp()  # os campeonatos do teste nao vao para back/dados

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import campeonato as camp  # noqa: E402
import main  # noqa: E402

# todos contra todos: cada par uma vez, e ninguem joga duas vezes na mesma rodada
for n in range(2, 9):
    times = [f"T{i}" for i in range(n)]
    jogos = camp.gerar_jogos(times)
    pares = sorted(tuple(sorted((a, b))) for _, a, b in jogos)
    assert pares == sorted(combinations(times, 2)), (n, pares)
    for r in {r for r, _, _ in jogos}:
        da_rodada = [t for rr, a, b in jogos if rr == r for t in (a, b)]
        assert len(da_rodada) == len(set(da_rodada)), (n, r, da_rodada)
    assert max(r for r, _, _ in jogos) == (n if n % 2 else n - 1), n

# pontos FIVB
assert camp.pontos_fivb("quadra", 0) == (3, 0) and camp.pontos_fivb("quadra", 1) == (3, 0)
assert camp.pontos_fivb("quadra", 2) == (2, 1)
assert camp.pontos_fivb("areia", 0) == (2, 1) and camp.pontos_fivb("areia", 1) == (2, 1)


def lance(lado_ponto):
    """fora no lado X da ponto ao X"""
    return {"veredito": "fora", "lado": lado_ponto, "source_id": "cam0"}


def jogar(pid, sequencia):
    """sequencia: [("A", 21), ("B", 19), ...] pontos seguidos para cada lado"""
    p = main.partidas[pid]
    for lado, n in sequencia:
        for _ in range(n):
            main.adicionar_decisao(p, lance(lado) | {"decisao_id": f"{pid}-{len(p['decisoes'])}"})
    return p


c = main.criar_campeonato(main.NovoCampeonato(nome="Copa", modalidade="areia", times=[" Ana ", "Bia", "Cris"]))
assert c["times"] == ["Ana", "Bia", "Cris"] and len(c["jogos"]) == 3
assert all(j["situacao"] == "a_jogar" for j in c["jogos"])
assert [t["pontos"] for t in c["ranking"]] == [0, 0, 0]
cid = c["id"]
j1, j2, j3 = c["jogos"]

# jogo 1: o time A vence 2x0 -> 2 pontos ao vencedor e 1 ao perdedor (areia)
p1 = main.iniciar_jogo(cid, j1["id"], main.InicioJogo(saque_inicial="B"))
assert p1["modalidade"] == "areia" and p1["placar"]["saque"] == "B"
assert (p1["time_a"], p1["time_b"]) == (j1["time_a"], j1["time_b"])
assert p1["campeonato"]["jogo"] == j1["id"]
assert main.ler_campeonato(cid)["jogos"][0]["situacao"] == "ao_vivo"
try:
    main.iniciar_jogo(cid, j1["id"], main.InicioJogo())
    raise AssertionError("jogo ao vivo nao pode ser iniciado de novo")
except HTTPException as e:
    assert e.status_code == 409
jogar(p1["id"], [("A", 21), ("A", 21)])
c = main.ler_campeonato(cid)
assert c["jogos"][0]["situacao"] == "concluido", c["jogos"][0]
assert c["jogos"][0]["resultado"] == {"vencedor": "A", "sets": {"A": 2, "B": 0},
                                      "parciais": [{"A": 21, "B": 0}, {"A": 21, "B": 0}]}
linha = {t["time"]: t for t in c["ranking"]}
assert linha[j1["time_a"]]["pontos"] == 2 and linha[j1["time_b"]]["pontos"] == 1
assert linha[j1["time_a"]]["pontos_pro"] == 42 and linha[j1["time_b"]]["pontos_contra"] == 42
assert c["ranking"][0]["time"] == j1["time_a"] and c["ranking"][0]["posicao"] == 1

# corrigir um lance depois do fim refaz o resultado: o ultimo ponto passa ao B, 21x20 nao fecha
ultimo = main.partidas[p1["id"]]["decisoes"][-1]["decisao_id"]
main.desfazer(ultimo)
c = main.ler_campeonato(cid)
assert c["jogos"][0]["resultado"] is None and c["jogos"][0]["situacao"] == "ao_vivo", c["jogos"][0]

# jogo interrompido (partida encerrada sem vencedor) pode recomecar do zero
p2 = main.iniciar_jogo(cid, j2["id"], main.InicioJogo())
main.encerrar(p2["id"])
assert main.ler_campeonato(cid)["jogos"][1]["situacao"] == "interrompido"
p2b = main.iniciar_jogo(cid, j2["id"], main.InicioJogo())
assert p2b["id"] != p2["id"] and p2b["placar"]["pontos"] == {"A": 0, "B": 0}

# o arquivo sobrevive ao back reiniciar
antes = main.ler_campeonato(cid)
main.campeonatos.clear()
main.partidas.clear()
importlib.reload(main)
main.carregar_partidas()
main.carregar_campeonatos()
assert main.ler_campeonato(cid) == antes

# quadra: 3x2 da 2 a 1; desempate por vitorias e saldo
q = main.criar_campeonato(main.NovoCampeonato(nome="Liga", times=["X", "Y"]))
pq = main.iniciar_jogo(q["id"], q["jogos"][0]["id"], main.InicioJogo())
jogar(pq["id"], [("A", 25), ("B", 25), ("A", 25), ("B", 25), ("A", 15)])
linha = {t["time"]: t for t in main.ler_campeonato(q["id"])["ranking"]}
a, b = q["jogos"][0]["time_a"], q["jogos"][0]["time_b"]
assert (linha[a]["pontos"], linha[b]["pontos"]) == (2, 1), linha
assert (linha[a]["sets_pro"], linha[a]["sets_contra"]) == (3, 2), linha

# validacao: times repetidos (sem diferenciar maiusculas) e menos de 2 times
for times in (["Ana", "ana"], ["Ana", "  "]):
    try:
        main.NovoCampeonato(nome="x", times=times)
        raise AssertionError(f"{times} deveria falhar")
    except ValidationError:
        pass

print("campeonato ok")
