"""a4 esporte captacao e arbitragem -- sprint 3"""
from collections import namedtuple

import numpy as np

# entrada, trajetoria ja em metros e altura com minimo no contato
Amostra = namedtuple("Amostra", "t_s ponto_m altura")

# saida, veredito dentro fora ou duvida
Decisao = namedtuple(
    "Decisao",
    "veredito distancia_cm banda_cm trilha_id camera_id versao_calibracao "
    "origem operador veredito_automatico",
    defaults=("automatica", None, None))


def instante_de_contato(amostras):
    """acha o instante do quique entre dois quadros

    card A4.1 · rule engine dentro/fora -- sprint 3, etapa 11 (Jose)
    sub-quadro, senao o caso de fronteira some entre dois quadros
    """
    ts = np.array([a.t_s for a in amostras], float)
    a2, b, _ = np.polyfit(ts, [a.altura for a in amostras], 2)
    assert a2 > 0, "sem quique, a altura nao tem minimo"
    return float(-b / (2.0 * a2))


def ponto_de_contato(amostras, janela=4):
    """acha o ponto do quique no plano

    card A4.1 · rule engine dentro/fora -- sprint 3, etapa 11 (Jose)
    """
    tc = instante_de_contato(amostras)
    # perto do chao a projecao vale, grau dois ajuda
    perto = sorted(amostras, key=lambda a: abs(a.t_s - tc))[:janela]
    ts = np.array([a.t_s for a in perto], float)
    xy = np.array([a.ponto_m for a in perto], float)
    return tc, tuple(float(np.polyval(np.polyfit(ts, xy[:, i], 2), tc)) for i in (0, 1))


def banda_de_duvida_cm(rms_calib_cm, ruido_trilha_cm, vel_ms, erro_t_s):
    """junta os erros de i3, de i2 e do tempo

    card A4.1 · rule engine, a tolerancia -- sprint 3, etapa 11 (Jose)
    """
    return float(np.hypot(np.hypot(rms_calib_cm, ruido_trilha_cm), vel_ms * erro_t_s * 100))


def arbitrar(ponto_m, linha_x_m, sigma_cm, calibracao, trilha_id):
    """decide dentro ou fora, na duvida devolve duvida

    card A4.1 · rule engine dentro/fora -- sprint 3, etapa 11 (Jose), 1a do sprint
    """
    d_cm = (float(ponto_m[0]) - linha_x_m) * 100.0    # positivo quer dizer fora
    banda = 2.0 * sigma_cm                            # banda de dois sigma
    veredito = "fora" if d_cm - banda > 0 else "dentro" if d_cm + banda < 0 else "duvida"
    # decisao automatica e so uma proposta
    return Decisao(veredito, round(d_cm, 1), round(banda, 1), trilha_id,
                   calibracao.camera_id, calibracao.versao)


def corrigir(decisao, veredito, operador):
    """troca o veredito pelo do arbitro

    card A4.2 · score manager, a correcao manual -- sprint 3, etapa 12 (Davi)
    falta: o placar automatico; aqui so o veredito e corrigido
    """
    return decisao._replace(veredito=veredito, origem="corrigida", operador=operador,
                            veredito_automatico=decisao.veredito)
