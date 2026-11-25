"""python test_placar.py -- confere a regra do placar do mock"""
import os
import tempfile

os.environ.setdefault("A4_DADOS_DIR", tempfile.mkdtemp())  # as partidas do teste nao vao para back/dados

from main import nova_partida, placar, preparar_demo


def lance(veredito, lado, anulada=False):
    return {"veredito": veredito, "lado": lado, "anulada": anulada}


p = nova_partida(pid="teste")
p["decisoes"] = [lance("dentro", "A"), lance("fora", "A"), lance("duvida", "B"),
                 lance("dentro", "B", anulada=True)]
# dentro no lado A e ponto do B; fora no lado A e ponto do A; duvida e anulado nao contam
assert placar(p) == {"sets": {"A": 0, "B": 0}, "pontos": {"A": 1, "B": 1}, "saque": "A", "vencedor": None}, placar(p)

# 25 x 24 nao fecha o set; 26 x 24 fecha
p["decisoes"] = [lance("fora", "A")] * 24 + [lance("fora", "B")] * 24 + [lance("fora", "A")]
assert placar(p)["sets"] == {"A": 0, "B": 0}, placar(p)
p["decisoes"].append(lance("fora", "A"))
assert placar(p)["sets"] == {"A": 1, "B": 0} and placar(p)["pontos"] == {"A": 0, "B": 0}, placar(p)

# 5o set vai a 15
p["decisoes"] = ([lance("fora", "A")] * 25 + [lance("fora", "B")] * 25) * 2 + [lance("fora", "A")] * 15
assert placar(p) == {"sets": {"A": 3, "B": 2}, "pontos": {"A": 0, "B": 0}, "saque": None, "vencedor": "A"}, placar(p)
# partida decidida: lances depois disso nao contam
p["decisoes"] += [lance("fora", "B")] * 3
assert placar(p)["sets"] == {"A": 3, "B": 2} and placar(p)["pontos"] == {"A": 0, "B": 0}, placar(p)

# saque: comeca com saque_inicial, passa para quem ganhou o ponto
p = nova_partida(pid="saque", saque_inicial="B")
assert placar(p)["saque"] == "B", placar(p)
p["decisoes"] = [lance("fora", "A")]
assert placar(p)["saque"] == "A", placar(p)
p["decisoes"].append(lance("dentro", "A"))                   # dentro no lado A: ponto do B
assert placar(p)["saque"] == "B", placar(p)
# lance anulado nao muda o saque
p["decisoes"].append(lance("fora", "A", anulada=True))
assert placar(p)["saque"] == "B", placar(p)

# o primeiro saque de cada set alterna, nao importa quem fechou o set anterior
p["decisoes"] = [lance("fora", "B")] * 25                    # B fecha o 1o set
assert placar(p)["sets"] == {"A": 0, "B": 1} and placar(p)["saque"] == "A", placar(p)
p["decisoes"] += [lance("fora", "B")] * 25                   # B fecha o 2o set
assert placar(p)["sets"] == {"A": 0, "B": 2} and placar(p)["saque"] == "B", placar(p)
p["decisoes"] += [lance("fora", "A")] * 25                   # A fecha o 3o set
assert placar(p)["sets"] == {"A": 1, "B": 2} and placar(p)["saque"] == "A", placar(p)

# areia: melhor de 3, sets a 21, 3o set a 15
p = nova_partida(pid="areia", modalidade="areia")
p["decisoes"] = [lance("fora", "A")] * 20 + [lance("fora", "B")] * 20 + [lance("fora", "A")]
assert placar(p)["sets"] == {"A": 0, "B": 0}, placar(p)      # 21 x 20 nao fecha
p["decisoes"].append(lance("fora", "A"))
assert placar(p)["sets"] == {"A": 1, "B": 0} and placar(p)["saque"] == "B", placar(p)
p["decisoes"] += [lance("fora", "B")] * 21                   # 1 x 1
p["decisoes"] += [lance("fora", "A")] * 14 + [lance("fora", "B")] * 14
p["decisoes"].append(lance("fora", "A"))                     # 15 x 14 nao fecha o 3o set
assert placar(p)["sets"] == {"A": 1, "B": 1} and placar(p)["pontos"] == {"A": 15, "B": 14}, placar(p)
p["decisoes"].append(lance("fora", "A"))                     # 16 x 14 fecha
assert placar(p) == {"sets": {"A": 2, "B": 1}, "pontos": {"A": 0, "B": 0}, "saque": None, "vencedor": "A"}, placar(p)

# demo configuravel: mesma configuracao mantem os lances, outra recria vazia
d = preparar_demo("quadra", "A")
d["decisoes"] = [lance("fora", "A")]
assert preparar_demo("quadra", "A") is d and len(d["decisoes"]) == 1
d = preparar_demo("areia", "B")
assert d["modalidade"] == "areia" and d["decisoes"] == [] and placar(d)["saque"] == "B", d
for ruim in (("praia", "A"), ("areia", "C")):
    try:
        preparar_demo(*ruim)
        raise AssertionError(f"{ruim} deveria falhar")
    except ValueError:
        pass

print("placar ok")
