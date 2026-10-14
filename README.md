# A4 · esporte, captação e arbitragem

Parte do INV-1 · ODS 2026/2. O A4 é a aplicação de arbitragem: decide se a bola quicou
dentro ou fora, mantém o placar com correção manual e dá ao árbitro a tela da partida.
O sistema propõe, o árbitro decide.

Este repositório está no começo do Sprint 3. Por enquanto o back é um **mock** que inventa
lances, para o front já ter com o que trabalhar.

## Estrutura

```
a4/
├── back/    API do A4 (FastAPI). Hoje é mock: inventa um lance a cada 6 s
├── front/   tela do árbitro (Next.js 16)
├── docs/    como usar, contrato da API e documentos de referência do squad
└── old/     o que existia antes do Sprint 3: pipeline com Kafka, rule engine, yolo
```

## Rodar em dois terminais

```
# terminal 1, back na porta 8000
cd back
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000

# terminal 2, front na porta 3000
cd front
npm install
npm run dev
```

Abra http://localhost:3000. O placar muda sozinho a cada lance inventado pelo mock, e os
botões de cada lance corrigem o veredito ou desfazem o ponto.

O passo a passo completo, o contrato da API e os problemas comuns estão em
[`docs/como-usar.md`](docs/como-usar.md).

## Documentos

| arquivo | o que é |
|---|---|
| [`docs/como-usar.md`](docs/como-usar.md) | como rodar back e front, contrato da API, problemas comuns |
| [`docs/INV-1_arquitetura.pdf`](docs/INV-1_arquitetura.pdf) | projeto de componente do squad (I2, I3, A4) e divisão em sprints |
| [`docs/INV-1_interfaces.md`](docs/INV-1_interfaces.md) | contratos de I2 e I3 entregues no Sprint 2 |
| [`docs/Guia_Kafka_B2_v2.pdf`](docs/Guia_Kafka_B2_v2.pdf) | guia do barramento Kafka do projeto |
| [`old/README.md`](old/README.md) e [`old/docs/como-rodar.md`](old/docs/como-rodar.md) | o pipeline antigo I3 → I2 → A4 |

## Pasta `old/`

É o A4 de antes do Sprint 3, guardado como referência. O `old/a4_arbitragem.py` já tem o
esboço do rule engine, e o `old/pipeline.py` tem o consumidor Kafka; os dois vão ser
reaproveitados no `back/`.

O venv do yolo (`old/yolo/.venv`) foi movido de pasta, então os scripts dentro dele apontam
para o caminho antigo. Use `old/yolo/.venv/bin/python -m pip ...` em vez de `.../bin/pip`, ou
recrie o venv.
