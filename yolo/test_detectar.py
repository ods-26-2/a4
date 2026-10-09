"""checagem de mapear_classes -- roda sem o venv, so stdlib

    python3 yolo/test_detectar.py

mapear_classes e a fronteira entre "qualquer peso de yolo" e os perfis do i2.
cada modelo nomeia as classes do seu jeito, e um alias que para de casar nao
quebra nada aqui: quebra la na frente, num csv vazio depois de rodar o stack
inteiro. por isso a checagem mora fora do caminho do torch.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from detectar import mapear_classes

# nomes como o coco os escreve, mais as variantes que pesos de volei usam
assert mapear_classes({0: "person", 32: "sports ball"}) == {0: "pessoa", 32: "bola"}
assert mapear_classes({0: "Volley-Ball"}) == {0: "bola"}, "maiuscula e hifen tem que casar"
assert mapear_classes({0: "volley_ball"}) == {0: "bola"}, "underscore tem que casar"
assert mapear_classes({0: "ball "}) == {0: "bola"}, "espaco sobrando tem que casar"
assert mapear_classes({0: "cachorro", 1: "cadeira"}) == {}, "o que nao casa fica de fora"
print("ok")
