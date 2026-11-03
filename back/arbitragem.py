"""rule engine do a4 -- card A4.1 do sprint 3

entra a posicao da bola por quadro (point_px de ods.s1.position) e a calibracao de
ods.i3.calibration; sai uma decisao dentro, fora ou duvida no formato da api do a4.
a decisao automatica e so proposta: o arbitro decide.
"""
import os
import uuid
from collections import defaultdict, namedtuple
from datetime import datetime, timezone

import cv2
import numpy as np

QUADRA = (18.0, 9.0)                                  # volei FIVB, rede em x = 9
CANTOS = ((0.0, 0.0), (18.0, 0.0), (18.0, 9.0), (0.0, 9.0))  # medida oficial, sem zona salva
JANELA = 15                                           # amostras guardadas por trilha
N_SUBIDA = 3                                          # quadros subindo depois do quique
# erros que se ajustam no campo
RUIDO_TRILHA_CM = float(os.getenv("A4_RUIDO_TRILHA_CM", "3"))
ERRO_T_S = float(os.getenv("A4_ERRO_T_S", str(1 / 60)))     # meio quadro a 30 fps

Calibracao = namedtuple("Calibracao", "source_id versao K dist H rms_cm space_id largura altura")
# a quadra marcada no editor do b6, em metros (zonas.py)
Zona = namedtuple("Zona", "poligono erro_cm versao")
# altura so precisa ter minimo no contato
Amostra = namedtuple("Amostra", "t_s ponto_m altura")


def calibracao(ev):
    """envelope de ods.i3.calibration -> Calibracao"""
    p = ev["payload"]
    i = p["intrinsics"]
    K = np.array([[i["fx"], 0, i["cx"]], [0, i["fy"], i["cy"]], [0, 0, 1]], float)
    return Calibracao(ev["source_id"], ev["artifact_version"], K,
                      np.array(p["distortion"], float),
                      np.array(p["homography_px_to_m"], float), p["reprojection_rms_cm"],
                      p["reference_frame"]["space_id"], p.get("image_width"), p.get("image_height"))


def corrigir_px(cal, point_px):
    """pixel do quadro bruto -> pixel sem distorcao, na mesma camera"""
    pts = np.array([[point_px]], float)
    return tuple(cv2.undistortPoints(pts, cal.K, cal.dist, P=cal.K)[0, 0])


def para_metros(cal, px):
    v = cal.H @ np.array([px[0], px[1], 1.0])
    return tuple(v[:2] / v[2])


def instante_de_contato(amostras):
    """acha o instante do quique entre dois quadros

    sub-quadro, senao o caso de fronteira some entre dois quadros
    """
    ts = np.array([a.t_s for a in amostras], float)
    t0 = ts[0]                                        # epoch e grande demais para o polyfit
    a2, b, _ = np.polyfit(ts - t0, [a.altura for a in amostras], 2)
    assert a2 > 0, "sem quique, a altura nao tem minimo"
    return float(t0 - b / (2.0 * a2))


def ponto_de_contato(amostras, janela=4):
    """acha o ponto do quique no plano"""
    tc = instante_de_contato(amostras)
    # perto do chao a projecao vale, grau dois ajuda
    perto = sorted(amostras, key=lambda a: abs(a.t_s - tc))[:janela]
    ts = np.array([a.t_s for a in perto], float)
    t0 = ts[0]
    xy = np.array([a.ponto_m for a in perto], float)
    return tc, tuple(float(np.polyval(np.polyfit(ts - t0, xy[:, i], 2), tc - t0)) for i in (0, 1))


def banda_de_duvida_cm(rms_calib_cm, ruido_trilha_cm, vel_ms, erro_t_s, erro_zona_cm=0.0):
    """junta os erros de i3, do rastro, do tempo e do desenho da zona num sigma"""
    return float(np.hypot(np.hypot(np.hypot(rms_calib_cm, ruido_trilha_cm), vel_ms * erro_t_s * 100), erro_zona_cm))


def distancia_cm(ponto, poligono):
    """distancia ate a linha mais perto: positivo fora, negativo dentro"""
    x, y = ponto
    dentro, menor = False, float("inf")
    for (ax, ay), (bx, by) in zip(poligono, (*poligono[1:], poligono[0])):
        dx, dy = bx - ax, by - ay
        t = np.clip(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
        menor = min(menor, float(np.hypot(x - (ax + t * dx), y - (ay + t * dy))))
        if (ay > y) != (by > y) and x < ax + (y - ay) * dx / dy:
            dentro = not dentro
    return (-menor if dentro else menor) * 100.0


def arbitrar(ponto_m, sigma_cm, source_id, versao, track_id, instante, zona=None):
    """decide dentro ou fora pela zona; sem zona, pela medida oficial. se a banda cruza a linha, duvida"""
    poligono = zona.poligono if zona else CANTOS
    d_cm = distancia_cm(ponto_m, poligono)
    # eixo x ao longo dos 18 m, como no referencial do i3; a rede fica no meio da quadra
    rede_x = sum(p[0] for p in poligono) / len(poligono)
    banda = 2.0 * sigma_cm                            # banda de dois sigma
    veredito = "fora" if d_cm - banda > 0 else "dentro" if d_cm + banda < 0 else "duvida"
    return {"decisao_id": str(uuid.uuid4()), "veredito": veredito,
            "distancia_cm": round(d_cm, 1), "banda_cm": round(banda, 1),
            "lado": "A" if ponto_m[0] < rede_x else "B", "track_id": track_id,
            "source_id": source_id, "artifact_version": versao,
            "zones_version": zona.versao if zona else None, "origem": "automatica",
            "operador": None, "veredito_automatico": None, "anulada": False,
            "instante": instante}


class Detector:
    """acha o quique em cada trilha da bola de uma camera"""

    def __init__(self):
        self.trilhas = defaultdict(list)

    def zerar(self):
        """sessao nova: os track_id antigos nao valem mais"""
        self.trilhas.clear()

    def amostra(self, cal, track_id, t_s, point_px, zona=None):
        """um quadro da bola, t_s em segundos epoch do captured_at; devolve a decisao
        quando reconhece um quique, senao None"""
        u, v = corrigir_px(cal, point_px)
        # ponytail: altura pelo v da imagem (no quique a bola esta mais baixa no quadro);
        # trocar por altura de verdade se entrar uma segunda camera
        hist = self.trilhas[track_id]
        hist.append(Amostra(t_s, para_metros(cal, (u, v)), -v))
        del hist[:-JANELA]
        i = min(range(len(hist)), key=lambda k: hist[k].altura)
        # minimo no meio da janela, com a bola subindo nos ultimos N_SUBIDA quadros
        if i < N_SUBIDA or len(hist) - 1 - i < N_SUBIDA:
            return None
        tc, ponto = ponto_de_contato(hist)
        vizinhos = hist[i - 1], hist[i + 1]
        vel = np.hypot(*np.subtract(vizinhos[1].ponto_m, vizinhos[0].ponto_m)) / (
            vizinhos[1].t_s - vizinhos[0].t_s)
        sigma = banda_de_duvida_cm(cal.rms_cm, RUIDO_TRILHA_CM, vel, ERRO_T_S, zona.erro_cm if zona else 0.0)
        hist.clear()                                  # um quique por minimo
        instante = datetime.fromtimestamp(tc, timezone.utc).isoformat(timespec="milliseconds")
        return arbitrar(ponto, sigma, cal.source_id, cal.versao, track_id,
                        instante.replace("+00:00", "Z"), zona)
