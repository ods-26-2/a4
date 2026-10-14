"""substituto do i1 (MOD-1) ate o outro grupo entregar a deteccao

nao e entrega do squad. roda um yolo pre-treinado e despeja o resultado no
contrato do i1 -- caixa, classe e confianca por quadro. o pipeline le o csv e
nao sabe quem escreveu: hoje o yolo, amanha a jetson.

    python detectar.py clipe.mp4 deteccoes.csv              # so o csv
    python detectar.py clipe.mp4 deteccoes.csv --ver        # + video anotado
    python detectar.py clipe.mp4 deteccoes.csv --janela     # + janela ao vivo

pra assistir, suba a confianca (--conf 0.6). no padrao baixo o pe vira bola.
"""
import argparse
import csv
import subprocess

# cada modelo nomeia as classes do seu jeito; casamos por nome, nao por indice,
# pra um peso treinado em volei entrar sem mexer no codigo
ALIASES = {
    "bola": ("sports ball", "ball", "volleyball", "volley ball"),
    "pessoa": ("person", "player", "people"),
}


def mapear_classes(nomes):
    """indice do modelo -> perfil do i2; o que nao casa fica de fora"""
    casadas = {}
    for i, nome in nomes.items():
        limpo = nome.lower().replace("-", " ").replace("_", " ").strip()
        for perfil, alias in ALIASES.items():
            if limpo in alias:
                casadas[i] = perfil
    return casadas


def fps_de(video):
    """fps exato do arquivo, como fracao -- 30000/1001 nao e 30"""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video],
        capture_output=True, text=True, check=True).stdout.strip()
    num, den = r.split("/")
    return float(num) / float(den)


def detectar(video, saida, modelo, imgsz, conf, ver=False, janela=False):
    import os
    from ultralytics import YOLO

    fps = fps_de(video)
    # ao lado do csv; project relativo colide com o runs_dir do proprio ultralytics
    destino = os.path.dirname(os.path.abspath(saida))
    rede = YOLO(modelo)
    classes = mapear_classes(rede.names)
    if not classes:
        raise SystemExit(f"nenhuma classe util em {modelo}: {rede.names}")
    print("classes:", {rede.names[i]: p for i, p in classes.items()})
    quadros = rede.predict(video, imgsz=imgsz, conf=conf,
                           classes=list(classes), stream=True, verbose=False,
                           save=ver, show=janela,
                           project=destino, name="anotado", exist_ok=True)
    n_linhas = 0
    with open(saida, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["quadro", "t_s", "x1", "y1", "x2", "y2", "classe", "confianca"])
        for n, r in enumerate(quadros):
            for b in r.boxes:
                x1, y1, x2, y2 = (round(v, 1) for v in b.xyxy[0].tolist())
                w.writerow([n, round(n / fps, 4), x1, y1, x2, y2,
                            classes[int(b.cls)], round(float(b.conf), 3)])
                n_linhas += 1
    print(f"{saida}: {n_linhas} deteccoes em {n + 1} quadros a {fps:.4f} fps")
    if ver:
        print(f"video anotado em {destino}/anotado/")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("saida")
    p.add_argument("--modelo", default="yolo11x.pt")
    p.add_argument("--imgsz", type=int, default=1280,
                   help="resolucao nativa; no padrao 640 a bola some")
    p.add_argument("--conf", type=float, default=0.05,
                   help="baixo de proposito: bola pequena sai com confianca baixa")
    p.add_argument("--ver", action="store_true", help="salva o video anotado")
    p.add_argument("--janela", action="store_true", help="abre janela ao vivo")
    a = p.parse_args()
    detectar(a.video, a.saida, a.modelo, a.imgsz, a.conf, a.ver, a.janela)
