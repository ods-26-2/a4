"""rule engine do a4 -- card A4.1 do sprint 3

entra a posicao da bola por quadro (point_px do rastro) e a calibracao de
ods.i3.calibration; sai uma decisao dentro, fora ou duvida no formato da api do a4.
a decisao automatica e so proposta: o arbitro decide.
"""
import os
import uuid
from collections import defaultdict, namedtuple
from datetime import datetime, timezone

import numpy as np

QUADRA = (18.0, 9.0)                                  # volei FIVB, rede em x = 9
JANELA = 15                                           # amostras guardadas por trilha
N_SUBIDA = 3                                          # quadros subindo depois do quique
# erros que se ajustam no campo
RUIDO_TRILHA_CM = float(os.getenv("A4_RUIDO_TRILHA_CM", "3"))
ERRO_T_S = float(os.getenv("A4_ERRO_T_S", str(1 / 60)))     # meio quadro a 30 fps
# o que separa quique de bola parada no chao (tenis amarelo, logo, bola na mao): a bola
# chega rapido e sai rapido. o sacador quicando a bola fica em 3,6 a 5,4 m/s
DESCIDA_MIN_MS = float(os.getenv("A4_DESCIDA_MIN_MS", "6"))
SUBIDA_MIN_MS = float(os.getenv("A4_SUBIDA_MIN_MS", "3"))
# largura/altura da caixa: bola em voo deu 0,83 a 0,96 no video, tenis ate 1,64
FORMATO = (float(os.getenv("A4_FORMATO_MIN", "0.8")), float(os.getenv("A4_FORMATO_MAX", "1.25")))

Calibracao = namedtuple("Calibracao", "source_id versao K dist H rms_cm")
# altura so precisa ter minimo no contato
Amostra = namedtuple("Amostra", "t_s ponto_m altura")


def calibracao(ev):
    """envelope de ods.i3.calibration -> Calibracao"""
    p = ev["payload"]
    i = p["intrinsics"]
    K = np.array([[i["fx"], 0, i["cx"]], [0, i["fy"], i["cy"]], [0, 0, 1]], float)
    return Calibracao(ev["source_id"], ev["artifact_version"], K,
                      np.array(p["distortion"], float),
                      np.array(p["homography_px_to_m"], float), p["reprojection_rms_cm"])


def para_metros(cal, px):
    """6c: homography_px_to_m sai do pixel bruto, entao nao se corrige a distorcao antes"""
    v = cal.H @ np.array([px[0], px[1], 1.0])
    return tuple(v[:2] / v[2])


def px_por_metro(cal, ponto_m):
    """escala da imagem no ponto do chao, medida ao longo de x

    ponytail: a bola sobe e desce perpendicular a camera, como x; e uma aproximacao da escala
    vertical que vale perto do chao. trocar pela projecao com os intrinsecos se precisar
    """
    H_inv = np.linalg.inv(cal.H)
    a, b = (H_inv @ np.array([ponto_m[0] + d, ponto_m[1], 1.0]) for d in (-0.5, 0.5))
    return float(np.hypot(*(a[:2] / a[2] - b[:2] / b[2])))


def instante_de_contato(amostras):
    """acha o instante do quique entre dois quadros, ou None se as amostras nao tem um

    sub-quadro, senao o caso de fronteira some entre dois quadros
    """
    # t_s e epoch (~1.8e9): ao quadrado o ajuste perde a precisao, entao vai relativo
    t0 = amostras[0].t_s
    ts = np.array([a.t_s - t0 for a in amostras], float)
    a2, b, _ = np.polyfit(ts, [a.altura for a in amostras], 2)
    if a2 <= 0:                                       # sem minimo nao ha quique
        return None
    tc = float(-b / (2.0 * a2))
    # vertice fora das amostras e extrapolacao, nao quique: daria ponto a quilometros
    return t0 + tc if ts[0] <= tc <= ts[-1] else None


def ponto_de_contato(amostras, janela=4):
    """acha o ponto do quique no plano, ou None se nao ha quique nas amostras"""
    tc = instante_de_contato(amostras)
    if tc is None:
        return None
    # perto do chao a projecao vale, grau dois ajuda
    perto = sorted(amostras, key=lambda a: abs(a.t_s - tc))[:janela]
    ts = np.array([a.t_s - tc for a in perto], float)          # relativo, pelo mesmo motivo
    xy = np.array([a.ponto_m for a in perto], float)
    return tc, tuple(float(np.polyval(np.polyfit(ts, xy[:, i], 2), 0.0)) for i in (0, 1))


def banda_de_duvida_cm(rms_calib_cm, ruido_trilha_cm, vel_ms, erro_t_s):
    """junta os erros de i3, do rastro e do tempo num sigma"""
    return float(np.hypot(np.hypot(rms_calib_cm, ruido_trilha_cm), vel_ms * erro_t_s * 100))


def arbitrar(ponto_m, sigma_cm, source_id, versao, track_id, instante):
    """decide dentro ou fora; se a banda cruza a linha, duvida"""
    x, y = ponto_m
    # distancia ate a linha mais perto: positivo fora, negativo dentro
    d_cm = max(-x, x - QUADRA[0], -y, y - QUADRA[1]) * 100.0
    banda = 2.0 * sigma_cm                            # banda de dois sigma
    veredito = "fora" if d_cm - banda > 0 else "dentro" if d_cm + banda < 0 else "duvida"
    return {"decisao_id": str(uuid.uuid4()), "veredito": veredito,
            "distancia_cm": round(d_cm, 1), "banda_cm": round(banda, 1),
            "lado": "A" if x < QUADRA[0] / 2 else "B",
            "position_m": [round(x, 2), round(y, 2)], "track_id": track_id,
            "source_id": source_id, "artifact_version": versao, "origem": "automatica",
            "operador": None, "veredito_automatico": None, "anulada": False,
            "instante": instante}


class Detector:
    """acha o quique em cada trilha da bola de uma camera"""

    def __init__(self):
        self.trilhas = defaultdict(list)

    def zerar(self):
        """sessao nova: os track_id antigos nao valem mais"""
        self.trilhas.clear()

    def amostra(self, cal, track_id, t_s, point_px, bbox=None):
        """um quadro da bola, t_s em segundos epoch do captured_at; devolve a decisao
        quando reconhece um quique, senao None"""
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            if not FORMATO[0] <= (x2 - x1) / max(y2 - y1, 1) <= FORMATO[1]:
                return None                           # caixa comprida: tenis, nao bola
        u, v = point_px
        # ponytail: altura pelo v da imagem (no quique a bola esta mais baixa no quadro);
        # trocar por altura de verdade se entrar uma segunda camera
        hist = self.trilhas[track_id]
        hist.append(Amostra(t_s, para_metros(cal, (u, v)), -v))
        del hist[:-JANELA]
        i = min(range(len(hist)), key=lambda k: hist[k].altura)
        # minimo no meio da janela, com a bola subindo nos ultimos N_SUBIDA quadros
        if i < N_SUBIDA or len(hist) - 1 - i < N_SUBIDA:
            return None
        antes, fundo, depois = hist[i - N_SUBIDA], hist[i], hist[i + N_SUBIDA]
        escala = px_por_metro(cal, fundo.ponto_m)
        descida = (antes.altura - fundo.altura) / (fundo.t_s - antes.t_s) / escala
        subida = (depois.altura - fundo.altura) / (depois.t_s - fundo.t_s) / escala
        if descida < DESCIDA_MIN_MS or subida < SUBIDA_MIN_MS:
            return None                               # parada no chao nao quica
        # so os quadros em volta do minimo: a janela inteira mistura outros trechos do voo
        contato = ponto_de_contato(hist[i - N_SUBIDA:i + N_SUBIDA + 1])
        if contato is None:
            return None
        tc, ponto = contato
        vizinhos = hist[i - 1], hist[i + 1]
        vel = np.hypot(*np.subtract(vizinhos[1].ponto_m, vizinhos[0].ponto_m)) / (
            vizinhos[1].t_s - vizinhos[0].t_s)
        sigma = banda_de_duvida_cm(cal.rms_cm, RUIDO_TRILHA_CM, vel, ERRO_T_S)
        hist.clear()                                  # um quique por minimo
        instante = datetime.fromtimestamp(tc, timezone.utc).isoformat(timespec="milliseconds")
        return arbitrar(ponto, sigma, cal.source_id, cal.versao, track_id,
                        instante.replace("+00:00", "Z"))
