"""artefato MODEL do a4 para o I1 (MOD-1), no formato do pacote do B5

    old/yolo/.venv/bin/python modelo/exportar.py old/yolo/bola_volei.pt

sai modelo/app-volei/<versao>/ com o .onnx, o metadata.json que o I1 le (classes e versao)
e o descriptor.json do registro de artefatos.

o peso treinado e de segmentacao, e o I1 carrega o modelo como detector: o onnx de
segmentacao tem uma saida a mais (mascara) e o I1 le lixo dela. a cabeca de segmentacao
herda da de deteccao, entao trocar a classe dela exporta as mesmas caixas sem a mascara.
imgsz fixo em 1280: em 640 a bola some.
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from onnxruntime import InferenceSession
from ultralytics import YOLO
from ultralytics.nn.modules.head import Detect, Segment

ID, VERSAO, IMGSZ = "app-volei", "1.0.0", 1280
AQUI = Path(__file__).resolve().parent


def gravar(caminho, conteudo):
    caminho.write_text(json.dumps(conteudo, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def main(pt):
    yolo = YOLO(pt)
    if isinstance(yolo.model.model[-1], Segment):
        yolo.model.model[-1].__class__ = Detect
    yolo.model.task = yolo.task = yolo.overrides["task"] = "detect"
    classes = [yolo.names[i] for i in sorted(yolo.names)]

    destino = AQUI / ID / VERSAO
    destino.mkdir(parents=True, exist_ok=True)
    onnx = destino / f"{ID}.onnx"
    shutil.move(yolo.export(format="onnx", imgsz=IMGSZ), onnx)
    saidas = InferenceSession(onnx).get_outputs()
    assert len(saidas) == 1 and saidas[0].shape[1] == 4 + len(classes), \
        f"o I1 espera so caixa e classe, saiu {[s.shape for s in saidas]}"

    hash_sha256 = hashlib.sha256(onnx.read_bytes()).hexdigest()
    gravar(destino / "metadata.json", {
        "artifact_id": ID, "artifact_version": VERSAO, "classes": classes,
        "input_shape": [1, 3, IMGSZ, IMGSZ], "precision": "FP32",
        "onnx_file": onnx.name, "hash_sha256": hash_sha256})
    gravar(destino / "descriptor.json", {
        "artifact_id": ID, "artifact_version": VERSAO, "kind": "MODEL", "owner": "INV-1",
        "uri": f"modelo/{ID}/{VERSAO}/{onnx.name}", "hash_sha256": hash_sha256,
        "valid_from": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")})
    print(f"{destino}: {classes}, sha256 {hash_sha256[:12]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pt", help="peso treinado do yolo, ex. old/yolo/bola_volei.pt")
    main(p.parse_args().pt)
