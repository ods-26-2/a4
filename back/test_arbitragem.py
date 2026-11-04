"""python test_arbitragem.py -- confere a regra do rule engine, com pontos ja em metros"""
from arbitragem import Amostra, arbitrar, ponto_de_contato


def decide(x, y, sigma_cm=5.0):
    return arbitrar((x, y), sigma_cm, "cam0", "cal-cam0-3", "t-0001", "2026-10-16T12:00:00.000Z")


d = decide(17.0, 4.5)
assert (d["veredito"], d["lado"]) == ("dentro", "B"), d
assert (d["artifact_version"], d["track_id"]) == ("cal-cam0-3", "t-0001"), d

d = decide(18.5, 4.5)
assert (d["veredito"], d["distancia_cm"]) == ("fora", 50.0), d

# 2 cm fora, mas a banda de 2 sigma e 10 cm: cruza a linha
assert decide(18.02, 4.5)["veredito"] == "duvida"

# fora pela lateral, no lado A
d = decide(3.0, -0.4)
assert (d["veredito"], d["lado"]) == ("fora", "A"), d

# quique em V em t = 0,5 s; no plano a bola anda reto a 10 m/s em x
amostras = [Amostra(t, (12.0 + 10 * (t - 0.5), 4.0), abs(t - 0.5))
            for t in (i / 30 for i in range(6, 25))]
tc, (x, y) = ponto_de_contato(amostras)
assert abs(tc - 0.5) < 1e-3 and abs(x - 12.0) < 0.01 and abs(y - 4.0) < 0.01, (tc, x, y)

# bola no alto da parabola (altura com maximo, nao minimo): nao e quique, e nao pode quebrar
topo = [Amostra(t, (12.0, 4.0), -abs(t - 0.5)) for t in (i / 30 for i in range(6, 25))]
assert ponto_de_contato(topo) is None

# descida reta sem fundo: o vertice so existiria fora das amostras, a quilometros
descida = [Amostra(t, (12.0, 4.0), 1.0 - t + 0.01 * t * t) for t in (i / 30 for i in range(7))]
assert ponto_de_contato(descida) is None

print("arbitragem ok")
