"""python test_arbitragem.py -- regra de dentro e fora e o quique pela trajetoria 3D"""
import numpy as np

import cena_sintetica as cena
from arbitragem import Detector, arbitrar, calibracao
from trajetoria import Arco, Camera, sem_distorcao


def decide(x, y, sigma_cm=5.0):
    return arbitrar((x, y), sigma_cm, "cam0", "cal-cam0-3", "t-0001", "2026-10-16T12:00:00.000Z")


d = decide(17.0, 4.5)
assert (d["veredito"], d["lado"]) == ("dentro", "B"), d
assert (d["artifact_version"], d["track_id"]) == ("cal-cam0-3", "t-0001"), d
d = decide(18.5, 4.5)
assert (d["veredito"], d["distancia_cm"]) == ("fora", 50.0), d
assert decide(18.02, 4.5)["veredito"] == "duvida"        # 2 cm fora, banda de 10 cm
d = decide(3.0, -0.4)
assert (d["veredito"], d["lado"]) == ("fora", "A"), d

CAL = calibracao(cena.envelope())
cam = Camera(CAL)
# a pose sai da homografia e dos intrinsecos
assert np.allclose(cam.centro, cena.CENTRO, atol=1e-6), cam.centro
assert np.allclose(cam.projetar(np.array([3.0, 2.0, 1.5])), cena.pixel(np.array([3.0, 2.0, 1.5])), atol=1e-6)

# distorcao: o pixel corrigido, distorcido de novo, volta ao bruto
K, dist = CAL.K, np.array([-0.3, 0.1, 0.001, -0.002, -0.02])
bruto = np.array([1100.0, 600.0])
x, y = (sem_distorcao(K, dist, bruto) - K[:2, 2]) / K[0, 0]
r2 = x * x + y * y
xd = x * (1 - 0.3 * r2 + 0.1 * r2 ** 2 - 0.02 * r2 ** 3) + 2 * 0.001 * x * y - 0.002 * (r2 + 2 * x * x)
assert abs(xd * K[0, 0] + K[0, 2] - bruto[0]) < 1e-6

# um voo so, com ruido de 1 px: a gravidade fixa a profundidade
pts = cena.toque((6.0, 4.0, 2.5), (0, 0, 0), (8.0, 1.0, 6.0), antes_s=0, depois_s=0.8)
arco = Arco(cam, [(t, *cam.pixel(px)) for t, px in cena.pixels(pts)])
# a altura sai precisa porque a camera ve a bola quase de lado; a profundidade, ao longo do
# raio, e o eixo fraco de uma camera so -- no quique ela nao pesa: no chao, z = 0 fixa o ponto
erro = arco.em(1.4) - pts[12][1]
assert abs(erro[2]) < 0.15 and abs(erro[0]) < 0.25, erro


def rodar(*trajetos, cal=CAL, extra=()):
    """passa os quadros pelo Detector: cada trajeto e [(t, px)] de um objeto"""
    det, decisoes = Detector(), []
    por_t = {}
    for k, tr in enumerate(trajetos):
        for t, px in tr:
            por_t.setdefault(round(t * cena.FPS), []).append((f"t-ball-{k}", px))
    # o s1 manda um quadro por quadro de camera, com bola ou sem: segue 2 s depois do fim (o
    # contato mal medido espera 1 s pela regra do jogo)
    for n in range(min(por_t), max(por_t) + 2 * int(cena.FPS) + 1):
        d = det.quadro(cal, 1_793_000_000 + n / cena.FPS, por_t.get(n, []) + list(extra))
        if d:
            decisoes.append(d)
    return decisoes


def instante_s(d):
    from datetime import datetime
    return datetime.fromisoformat(d["instante"].replace("Z", "+00:00")).timestamp() - 1_793_000_000


# 1. quique no chao dentro, lado B: um lance, no ponto e no instante
(d,) = rodar(cena.pixels(cena.quique((12.0, 4.5), (6.0, 1.0, -9.0))))
assert (d["veredito"], d["lado"]) == ("dentro", "B"), d
assert np.hypot(d["position_m"][0] - 12.0, d["position_m"][1] - 4.5) < 0.15, d
assert abs(instante_s(d) - 1.0) < 0.02, instante_s(d)

# 2. toque de jogador a 1 m (manchete): a bola desce e sobe, mas no ar -- nao e lance
assert rodar(cena.pixels(cena.toque((5.0, 4.0, 1.0), (4.0, 0.5, -6.0), (2.0, 0.0, 7.0)))) == []

# 3. levantamento a 2,8 m, perto da rede: nao e lance
assert rodar(cena.pixels(cena.toque((8.0, 5.0, 2.8), (1.0, 0.5, -3.0), (0.5, 0.0, 4.0)))) == []

# 4. bola parada no banco e um falso positivo que pisca nao atrapalham
parada = [(t, (200.0, 500.0)) for t, _ in cena.quique((12.0, 4.5), (6.0, 1.0, -9.0))]
(d,) = rodar(cena.pixels(cena.quique((12.0, 4.5), (6.0, 1.0, -9.0))), parada,
             extra=[("t-ball-9", (900.0, 100.0))])
assert d["veredito"] == "dentro", d

# 5. fora pelo fundo: 60 cm alem da linha
(d,) = rodar(cena.pixels(cena.quique((18.6, 3.0), (8.0, 0.0, -10.0))))
assert d["veredito"] == "fora" and 45 < d["distancia_cm"] < 75, d

# 6. a bola some logo depois do chao (rastreio perde): o voo que chega a z = 0 decide
so_chegada = [(t, X) for t, X in cena.quique((10.5, 6.0), (-5.0, 1.0, -8.0)) if t <= 1.0]
# com um arco so a profundidade fica com a incerteza dele: o ponto erra mais, e a banda diz isso
(d,) = rodar(cena.pixels(so_chegada))
erro_cm = 100 * np.hypot(d["position_m"][0] - 10.5, d["position_m"][1] - 6.0)
assert d["veredito"] == "dentro" and erro_cm < 50 and d["banda_cm"] > erro_cm, d

# 7. o segundo quique do mesmo rally nao vira outro lance: a bola ja estava morta
primeiro = cena.quique((12.0, 4.5), (6.0, 1.0, -9.0), depois_s=0.45)
segundo = [(t + 0.95, X) for t, X in cena.quique((14.7, 4.95), (6.0, 1.0, -6.3), antes_s=0.5)]
assert len(rodar(cena.pixels(primeiro + segundo))) == 1

# 8. manchete rente (0,4 m) em que o rastreio perde a bola no toque, e 0,5 s depois o
# levantamento sai alto: a bola estava em jogo, nao e lance
chegada = [(t, X) for t, X in cena.toque((5.0, 4.0, 0.4), (4.0, 0.5, -7.0), (0, 0, 0)) if t <= 1.0]
levantamento = [(t + 0.5, X) for t, X in cena.toque((6.0, 4.5, 2.6), (0, 0, 0), (1.0, 0.3, 5.0), antes_s=0, depois_s=0.8)]
assert rodar(cena.pixels(chegada + levantamento)) == []

print("arbitragem ok")

# o lance traz o pixel do quique no quadro bruto, para o player desenhar: ida e volta da distorcao
cam_d = Camera(calibracao(cena.envelope()))
cam_d.dist = np.array([-0.3, 0.1, 0.001, -0.002, -0.02])
assert np.allclose(cam_d.pixel(cam_d.bruto(np.array([900.0, 500.0]))), [900.0, 500.0], atol=1e-3)
(d,) = rodar(cena.pixels(cena.quique((12.0, 4.5), (6.0, 1.0, -9.0))))
assert np.hypot(*(np.array(d["point_px"]) - cena.pixel(np.array([12.0, 4.5, 0.0])))) < 5, d["point_px"]
print("pixel do lance ok")
