"""zonas do a4 -- do desenho do editor do b6 ate o artefato ZONES

entra o desenho do front (4 cantos de 0 a 1, em cima de um quadro da camera) e a calibracao
do i3; sai o artefato ZONES em metros, com hash e versao, no formato que o s1 le. a mesma
zona e a que a regra usa para decidir dentro ou fora (arbitragem.py).
"""
import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from arbitragem import QUADRA, Zona, para_metros

PRODUTOR = "A4"
TOPICO_PUBLICADO = "ods.artifact.published"
ZONE_ID = "quadra"
HISTERESE_MS = 100                                    # o a4 nao usa a transicao para decidir
TOLERANCIA_CM = float(os.getenv("A4_ZONA_TOLERANCIA_CM", "30"))
TOLERANCIA_ASPECTO = 0.01


class ZonaInvalida(ValueError):
    """desenho que nao da para virar quadra; a mensagem vai para a tela"""


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def pontos_para_metros(cal, pontos, largura, altura):
    """(x, y) de 0 a 1 no quadro -> metros, pelo mesmo caminho do ponto do quique

    6c: homography_px_to_m vale do pixel do quadro bruto no chao, e os cantos estao no chao
    """
    w, h = cal.largura or largura, cal.altura or altura
    if abs(largura / altura - w / h) > TOLERANCIA_ASPECTO:
        raise ZonaInvalida(f"o quadro enviado ({largura}x{altura}) não tem a proporção da câmera calibrada ({w}x{h})")
    return [tuple(float(v) for v in para_metros(cal, (x * w, y * h))) for x, y in pontos]


def validar_quadra(poligono):
    """quatro cantos, convexo; pega desenho cruzado e calibracao que distorce a quadra"""
    if len(poligono) != 4:
        raise ZonaInvalida(f"a quadra tem 4 cantos, e o desenho tem {len(poligono)}")
    giros = []
    for i in range(4):
        a, b, c = (np.array(poligono[(i + k) % 4]) for k in range(3))
        u, v = b - a, c - b
        giros.append(u[0] * v[1] - u[1] * v[0])
    if not (all(g > 0 for g in giros) or all(g < 0 for g in giros)):
        raise ZonaInvalida("os cantos da quadra não formam um quadrilátero convexo")


def erro_quadra_cm(poligono):
    """quanto os lados desenhados fogem de 18 x 9 m, em rms; entra na banda de duvida"""
    lados = [math.dist(poligono[i], poligono[(i + 1) % 4]) for i in range(4)]
    longo, curto = QUADRA
    return min(
        math.sqrt(sum((lado - alvo) ** 2 for lado, alvo in zip(lados, alvos)) / 4) * 100
        for alvos in ((longo, curto, longo, curto), (curto, longo, curto, longo))
    )


def conteudo_zones(cal, poligono):
    return {
        "space_id": cal.space_id,
        "coordinates": "METERS",
        "source_ids": [cal.source_id],
        "zones": [{
            "zone_id": ZONE_ID,
            "name": "Quadra",
            "polygon": [[round(x, 4), round(y, 4)] for x, y in poligono],
            "enter_hysteresis_ms": HISTERESE_MS,
            "exit_hysteresis_ms": HISTERESE_MS,
            "classes": ["ball"],
        }],
    }


def mensagem_publicada(descritor):
    """envelope de ods.artifact.published; o payload e o proprio descritor"""
    return {
        "message_type": "event",
        "message_id": str(uuid.uuid4()),
        "schema": TOPICO_PUBLICADO,
        "schema_version": "1.0",
        "producer": PRODUTOR,
        "published_at": agora(),
        "payload": descritor,
    }


class Registro:
    """pasta no formato do registro de artefatos: registry://<caminho> e <raiz>/<caminho>

    cada versao e imutavel. a pasta e a que o s1 recebe em S1_REGISTRY_DIR.
    """

    def __init__(self, raiz=None):
        self.raiz = Path(raiz or os.getenv("A4_ARTEFATOS_DIR") or Path(__file__).parent / "artefatos")
        self._atuais = {}                             # source_id -> (descritor, conteudo, Zona)

    def carregar(self):
        """volta as ultimas versoes depois de reiniciar o back"""
        ordem = {}
        for arquivo in (self.raiz / "a4" / "zones").glob("*/descriptor.json"):
            descritor = json.loads(arquivo.read_text(encoding="utf-8"))
            dados = (self.raiz / descritor["uri"].removeprefix("registry://")).read_bytes()
            if hashlib.sha256(dados).hexdigest() != descritor["hash_sha256"]:
                continue
            conteudo = json.loads(dados)
            source_id = conteudo["source_ids"][0]
            n = _numero(descritor["artifact_version"])
            if n > ordem.get(source_id, 0):
                ordem[source_id] = n
                self._atuais[source_id] = (descritor, conteudo, _zona(descritor, conteudo))

    def atual(self, source_id):
        item = self._atuais.get(source_id)
        return item[2] if item else None

    def resumo(self, source_id):
        item = self._atuais.get(source_id)
        if not item:
            return None
        descritor, conteudo, zona = item
        return {"artifact_version": descritor["artifact_version"],
                "poligono_m": conteudo["zones"][0]["polygon"], "erro_cm": round(zona.erro_cm, 1)}

    def versoes(self, source_id):
        """versoes salvas da camera, da mais nova para a mais velha"""
        saida = []
        for arquivo in (self.raiz / "a4" / "zones").glob(f"zones-a4-{source_id}-*/descriptor.json"):
            descritor = json.loads(arquivo.read_text(encoding="utf-8"))
            conteudo = json.loads((self.raiz / descritor["uri"].removeprefix("registry://")).read_bytes())
            if conteudo["source_ids"] != [source_id]:
                continue                              # zones-a4-cam0-* pega tambem a cam0-x
            poligono = conteudo["zones"][0]["polygon"]
            saida.append({"artifact_version": descritor["artifact_version"], "valid_from": descritor["valid_from"],
                          "poligono_m": poligono, "erro_cm": round(erro_quadra_cm(poligono), 1)})
        return sorted(saida, key=lambda v: _numero(v["artifact_version"]), reverse=True)

    def salvar(self, cal, poligono):
        """grava uma versao nova; devolve o descritor"""
        artifact_id = f"zones-a4-{cal.source_id}"
        pasta_tipo = self.raiz / "a4" / "zones"
        existentes = [_numero(p.name) for p in pasta_tipo.glob(f"{artifact_id}-*")]
        versao = f"{artifact_id}-{max(existentes, default=0) + 1}"
        conteudo = conteudo_zones(cal, poligono)
        dados = json.dumps(conteudo, ensure_ascii=False, indent=2).encode("utf-8")
        descritor = {
            "artifact_id": artifact_id,
            "artifact_version": versao,
            "kind": "ZONES",
            "owner": PRODUTOR,
            "uri": f"registry://a4/zones/{versao}/content.json",
            "hash_sha256": hashlib.sha256(dados).hexdigest(),
            "valid_from": agora(),
            "schema_version": "1.0",
        }
        pasta = pasta_tipo / versao
        pasta.mkdir(parents=True)
        (pasta / "content.json").write_bytes(dados)
        (pasta / "descriptor.json").write_text(json.dumps(descritor, indent=2), encoding="utf-8")
        self._atuais[cal.source_id] = (descritor, conteudo, _zona(descritor, conteudo))
        return descritor


def _numero(versao):
    achado = re.search(r"-(\d+)$", versao)
    return int(achado.group(1)) if achado else 0


def _zona(descritor, conteudo):
    poligono = [tuple(p) for p in conteudo["zones"][0]["polygon"]]
    return Zona(poligono, erro_quadra_cm(poligono), descritor["artifact_version"])
