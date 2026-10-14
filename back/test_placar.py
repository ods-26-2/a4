"""python test_placar.py -- confere a regra do placar do mock"""
from main import nova_partida, placar


def lance(veredito, lado, anulada=False):
    return {"veredito": veredito, "lado": lado, "anulada": anulada}


p = nova_partida(pid="teste")
p["decisoes"] = [lance("dentro", "A"), lance("fora", "A"), lance("duvida", "B"),
                 lance("dentro", "B", anulada=True)]
# dentro no lado A e ponto do B; fora no lado A e ponto do A; duvida e anulado nao contam
assert placar(p) == {"sets": {"A": 0, "B": 0}, "pontos": {"A": 1, "B": 1}}, placar(p)

# 25 x 24 nao fecha o set; 26 x 24 fecha
p["decisoes"] = [lance("fora", "A")] * 24 + [lance("fora", "B")] * 24 + [lance("fora", "A")]
assert placar(p)["sets"] == {"A": 0, "B": 0}, placar(p)
p["decisoes"].append(lance("fora", "A"))
assert placar(p) == {"sets": {"A": 1, "B": 0}, "pontos": {"A": 0, "B": 0}}, placar(p)

# 5o set vai a 15
p["decisoes"] = ([lance("fora", "A")] * 25 + [lance("fora", "B")] * 25) * 2 + [lance("fora", "A")] * 15
assert placar(p) == {"sets": {"A": 3, "B": 2}, "pontos": {"A": 0, "B": 0}}, placar(p)

print("placar ok")
