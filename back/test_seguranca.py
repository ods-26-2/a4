"""python test_seguranca.py -- o token do arbitro protege toda rota que altera o jogo ou move a camera"""
import os
import tempfile

os.environ.setdefault("A4_DADOS_DIR", tempfile.mkdtemp())  # as partidas do teste nao vao para back/dados

from fastapi import HTTPException
from fastapi.routing import APIRoute

import main


def recusa(authorization):
    try:
        main.exige_token(authorization)
    except HTTPException as exc:
        return exc.status_code
    return None


# sem A4_TOKEN a API fica aberta (desenvolvimento local)
main.TOKEN = None
assert recusa(None) is None and recusa("Bearer qualquer") is None

main.TOKEN = "segredo-do-arbitro"
assert recusa("Bearer segredo-do-arbitro") is None
assert recusa(None) == 401, "sem header nao altera o jogo"
assert recusa("Bearer outro") == 401
assert recusa("segredo-do-arbitro") == 401, "so no formato Bearer"
main.TOKEN = None

# toda rota POST tem o token; nenhuma GET tem (ler o placar e o /eventos ficam livres)
for rota in main.app.routes:
    if not isinstance(rota, APIRoute):               # /docs e /openapi.json sao do proprio FastAPI
        continue
    metodos = rota.methods
    protegida = any(d.call is main.exige_token for d in rota.dependant.dependencies)
    assert protegida == ("POST" in metodos), f"{sorted(metodos)} {rota.path}: token {'falta' if not protegida else 'sobra'}"
print("token do arbitro ok")
