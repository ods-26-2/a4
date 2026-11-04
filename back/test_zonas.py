"""python test_zonas.py -- do desenho do editor ate o lance decidido pela zona, sem kafka"""
import json
import tempfile
from pathlib import Path

import numpy as np

import cena_sintetica as cena

from arbitragem import Calibracao, Detector, Zona, arbitrar, banda_de_duvida_cm, calibracao, distancia_cm
from kafka_bridge import TOPICO_POSICAO, KafkaBridge, motivo_invalido
from zonas import (Registro, ZonaInvalida, erro_quadra_cm,
                   pontos_para_metros, validar_quadra)

# 100 px = 1 m, com a quadra comecando em (100, 100) num quadro de 2000 x 1100
H = [[0.01, 0, -1], [0, 0.01, -1], [0, 0, 1]]
ENVELOPE_CAL = {
    "source_id": "cam0", "artifact_version": "cal-cam0-1",
    "payload": {
        "intrinsics": {"fx": 1000, "fy": 1000, "cx": 1000, "cy": 550}, "distortion": [0, 0, 0, 0, 0],
        "homography_px_to_m": H, "reprojection_rms_cm": 1.0, "image_width": 2000, "image_height": 1100,
        "reference_frame": {"space_id": "quadra-1"},
    },
}
CAL = calibracao(ENVELOPE_CAL)
assert isinstance(CAL, Calibracao) and (CAL.space_id, CAL.largura) == ("quadra-1", 2000), CAL

# desenho perfeito, normalizado no quadro
DESENHO = [(0.05, 100 / 1100), (0.95, 100 / 1100), (0.95, 1000 / 1100), (0.05, 1000 / 1100)]
poligono = pontos_para_metros(CAL, DESENHO, 2000, 1100)
assert np.allclose(poligono, [(0, 0), (18, 0), (18, 9), (0, 9)], atol=1e-6), poligono
validar_quadra(poligono)
assert erro_quadra_cm(poligono) < 1e-3

# foto em outra resolucao vale, com outra proporcao nao
assert np.allclose(pontos_para_metros(CAL, DESENHO, 1000, 550), poligono, atol=1e-6)
try:
    pontos_para_metros(CAL, DESENHO, 1920, 1080)
    raise AssertionError("proporcao errada devia ser recusada")
except ZonaInvalida:
    pass

# desenho cruzado e numero errado de cantos
for ruim in ([(0, 0), (18, 9), (18, 0), (0, 9)], [(0, 0), (18, 0), (18, 9)]):
    try:
        validar_quadra(ruim)
        raise AssertionError(f"devia recusar {ruim}")
    except ZonaInvalida:
        pass

# 20 cm a mais nos dois lados longos
assert abs(erro_quadra_cm([(0, 0), (18.2, 0), (18.2, 9), (0, 9)]) - np.sqrt(2 * 20 ** 2 / 4)) < 1e-6

# distancia com sinal: fora positivo, dentro negativo, inclusive em zona torta
assert abs(distancia_cm((18.5, 4.5), poligono) - 50) < 1e-3
assert abs(distancia_cm((17, 4.5), poligono) + 100) < 1e-3
assert abs(distancia_cm((19, 10), poligono) - np.hypot(100, 100)) < 1e-3
assert distancia_cm((9, 0.1), [(0, 0.2), (18, 0), (18, 9), (0, 9)]) > -11

# a regra usa a zona: o mesmo ponto muda de veredito com a linha deslocada 1 m
zona = Zona([(0, 0), (19, 0), (19, 9), (0, 9)], 0.0, "zones-a4-cam0-7")
ponto = (18.5, 4.5)
assert arbitrar(ponto, 5.0, "cam0", "cal", "t-1", "agora")["veredito"] == "fora"
d = arbitrar(ponto, 5.0, "cam0", "cal", "t-1", "agora", zona)
assert (d["veredito"], d["zones_version"], d["lado"]) == ("dentro", "zones-a4-cam0-7", "B"), d

# o erro do desenho alarga a banda: o que era certo vira duvida
ponto = (18.3, 4.5)
assert arbitrar(ponto, banda_de_duvida_cm(1, 3), "cam0", "cal", "t-1", "agora")["veredito"] == "fora"
assert arbitrar(ponto, banda_de_duvida_cm(1, 3, 20), "cam0", "cal", "t-1", "agora")["veredito"] == "duvida"

# quique vindo do s1, passando pela zona (camera e voo sinteticos, chao em (12, 4.5))
detector, decisao = Detector(), None
cal_cena = calibracao(cena.envelope())
pontos = dict((round(t * cena.FPS), px) for t, px in cena.pixels(cena.quique((12.0, 4.5), (6.0, 1.0, -9.0))))
for n in range(min(pontos), max(pontos) + 30):
    pts = [("t-9", pontos[n])] if n in pontos else []
    decisao = detector.quadro(cal_cena, 1000 + n / cena.FPS, pts, Zona(poligono, 5.0, "zones-a4-cam0-1")) or decisao
assert decisao and decisao["zones_version"] == "zones-a4-cam0-1" and decisao["veredito"] == "dentro", decisao

# registro: hash confere, versao sobe e volta depois de reiniciar
with tempfile.TemporaryDirectory() as raiz:
    registro = Registro(raiz)
    descritor = registro.salvar(CAL, poligono)
    assert descritor["artifact_version"] == "zones-a4-cam0-1", descritor
    assert registro.salvar(CAL, poligono)["artifact_version"] == "zones-a4-cam0-2"
    assert [v["artifact_version"] for v in registro.versoes("cam0")] == ["zones-a4-cam0-2", "zones-a4-cam0-1"]
    assert registro.versoes("cam1") == []
    conteudo = json.loads((Path(raiz) / "a4/zones/zones-a4-cam0-1/content.json").read_text(encoding="utf-8"))
    assert (conteudo["coordinates"], conteudo["space_id"], conteudo["source_ids"]) == ("METERS", "quadra-1", ["cam0"])
    assert conteudo["zones"][0]["polygon"][1] == [18.0, 0.0], conteudo

    outro = Registro(raiz)
    outro.carregar()
    assert outro.atual("cam0").versao == "zones-a4-cam0-2"


# validacao e mensagem repetida no consumidor
assert "ausente" in motivo_invalido({"schema": TOPICO_POSICAO}, TOPICO_POSICAO)
base = {"message_id": "m1", "message_type": "event", "schema": TOPICO_POSICAO,
        "schema_version": "1.0", "producer": "S1", "payload": {}}
assert motivo_invalido(base, TOPICO_POSICAO) is None
assert "versão" in motivo_invalido(base | {"schema_version": "2.0"}, TOPICO_POSICAO)
assert "schema" in motivo_invalido(base, "ods.i3.calibration")
recebidas = []
ponte = KafkaBridge(ao_receber_posicao=recebidas.append)
ponte._tratar_contrato(TOPICO_POSICAO, base)
ponte._tratar_contrato(TOPICO_POSICAO, base)
ponte._tratar_contrato(TOPICO_POSICAO, base | {"message_id": "m2", "schema_version": "2.0"})
assert len(recebidas) == 1, recebidas

print("zonas ok")
