"""python test_persistencia.py -- as partidas sobrevivem ao back reiniciar"""
import importlib
import os
import tempfile
from pathlib import Path

PASTA = tempfile.mkdtemp()
os.environ["A4_DADOS_DIR"] = PASTA

import main  # noqa: E402

p = main.nova_partida("Minas", "Sesi", "cam0", pid="final")
for i, (v, lado) in enumerate([("dentro", "A"), ("fora", "B"), ("dentro", "B")]):
    main.adicionar_decisao(p, {"decisao_id": f"d{i}", "veredito": v, "lado": lado, "source_id": "cam0"})
main.desfazer("d2")
antes = main.visao(main.partidas["final"])

# o back reinicia: o modulo volta do zero e le o arquivo
main.partidas.clear()
importlib.reload(main)
assert main.partidas == {}, "o estado em memoria some com o processo"
main.carregar_partidas()
depois = main.visao(main.partidas["final"])
assert depois == antes, (antes, depois)
# dentro no lado A e fora no lado B dao ponto ao B; o terceiro lance foi desfeito
assert depois["placar"]["pontos"] == {"A": 0, "B": 2}, depois["placar"]

# arquivo truncado (o back caiu gravando, ou alguem editou) nao derruba o back
arquivo = Path(PASTA) / "partidas.json"
arquivo.write_text('[{"id": "final", "decis', encoding="utf-8")
main.partidas.clear()
main.carregar_partidas()
assert main.partidas == {}
assert not arquivo.exists() and list(Path(PASTA).glob("partidas-ilegivel-*.json")), "o ilegivel fica guardado"
print("partidas salvas ok")
