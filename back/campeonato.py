"""Campeonato todos contra todos: tabela de jogos, resultado de cada jogo e ranking (regra FIVB).

Funções puras sobre dicionários; quem guarda em disco e serve pela API é o main.py.
"""


def gerar_jogos(times):
    """Método do círculo: cada time enfrenta cada outro uma vez, em rodadas sem time repetido.
    Com número ímpar de times, um time folga por rodada. Devolve [(rodada, time_a, time_b)]."""
    lista = list(times) + ([None] if len(times) % 2 else [])
    n = len(lista)
    jogos = []
    for r in range(n - 1):
        for i in range(n // 2):
            a, b = lista[i], lista[n - 1 - i]
            if a is not None and b is not None:
                # alterna o mando para o primeiro da lista não ser sempre o time A
                jogos.append((r + 1, a, b) if (r + i) % 2 == 0 else (r + 1, b, a))
        lista = [lista[0], lista[-1], *lista[1:-1]]
    return jogos


def resultado(placar):
    """retrato do jogo a partir do placar da partida; None enquanto ninguém venceu"""
    if not placar["vencedor"]:
        return None
    return {"vencedor": placar["vencedor"], "sets": dict(placar["sets"]),
            "parciais": [dict(s) for s in placar["parciais"]]}


def pontos_fivb(modalidade, sets_perdedor):
    """quadra: 3x0 ou 3x1 dá 3 a 0, 3x2 dá 2 a 1; areia: vitória 2, derrota 1"""
    if modalidade == "areia":
        return 2, 1
    return (2, 1) if sets_perdedor == 2 else (3, 0)


def ranking(c):
    """tabela do campeonato: pontos FIVB, depois vitórias, saldo de sets e saldo de pontos"""
    linhas = {t: {"time": t, "jogos": 0, "vitorias": 0, "derrotas": 0, "pontos": 0,
                  "sets_pro": 0, "sets_contra": 0, "pontos_pro": 0, "pontos_contra": 0}
              for t in c["times"]}
    for j in c["jogos"]:
        res = j.get("resultado")
        if not res:
            continue
        nomes = {"A": j["time_a"], "B": j["time_b"]}
        v = res["vencedor"]
        p = "B" if v == "A" else "A"
        pv, pp = pontos_fivb(c["modalidade"], res["sets"][p])
        for lado, outro, pts, venceu in ((v, p, pv, True), (p, v, pp, False)):
            linha = linhas[nomes[lado]]
            linha["jogos"] += 1
            linha["vitorias" if venceu else "derrotas"] += 1
            linha["pontos"] += pts
            linha["sets_pro"] += res["sets"][lado]
            linha["sets_contra"] += res["sets"][outro]
            linha["pontos_pro"] += sum(s[lado] for s in res["parciais"])
            linha["pontos_contra"] += sum(s[outro] for s in res["parciais"])
    tabela = sorted(linhas.values(), key=lambda t: (
        -t["pontos"], -t["vitorias"], -(t["sets_pro"] - t["sets_contra"]),
        -(t["pontos_pro"] - t["pontos_contra"]), t["time"].casefold()))
    for i, t in enumerate(tabela, 1):
        t["posicao"] = i
    return tabela
