# Como usar o A4 · back e front

Guia para rodar o A4 do Sprint 3 e para quem vai mexer no front. Todos os comandos rodam a
partir da pasta `a4/`.

O back hoje é um **mock**: não lê o Kafka nem roda o rule engine. Ele cria uma partida
chamada `demo` e inventa um lance a cada 6 s. O contrato da API já é o definitivo, então o
front feito contra o mock continua funcionando quando o back de verdade entrar.

---

## 1. Back (FastAPI, porta 8000)

Precisa de Python 3.10 ou mais novo.

```
cd back
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

- `--reload` reinicia sozinho quando o `main.py` muda.
- Documentação interativa de todas as rotas: http://localhost:8000/docs
- Para lances mais rápidos, mude o intervalo:
  `A4_INTERVALO_S=1 .venv/bin/uvicorn main:app --reload --port 8000`
- Teste da regra do placar: `.venv/bin/python test_placar.py` (tem que imprimir `placar ok`).

Para testar sem o front:

```
curl localhost:8000/partidas/demo
curl -N "localhost:8000/eventos?partida=demo"      # fica ouvindo; Ctrl+C para sair
curl -X POST localhost:8000/decisoes/<decisao_id>/correcao \
     -H 'content-type: application/json' -d '{"veredito":"fora","operador":"jose"}'
curl -X POST localhost:8000/pontos/<decisao_id>/desfazer
```

O `decisao_id` vem do `GET /partidas/demo`.

---

## 2. Front (Next.js 16, porta 3000)

Precisa de Node 20 ou mais novo.

```
cd front
npm install
cp .env.example .env.local     # só se o back não estiver em localhost:8000
npm run dev
```

Abra http://localhost:3000. O back precisa estar rodando.

Onde mexer:

| arquivo | o que tem |
|---|---|
| `front/app/page.tsx` | a tela inteira: placar, último lance e lista de lances com botões |
| `front/app/page.module.css` | estilo da tela |
| `front/lib/api.ts` | tipos `Partida` e `Decisao`, chamadas à API e conexão SSE |
| `front/.env.example` | `NEXT_PUBLIC_API_URL`, o endereço do back |

A tela atual é só um ponto de partida para o time do front redesenhar.

Antes de subir, rode `npm run lint` e `npm run build`.

> O Next 16 mudou várias APIs. O `front/AGENTS.md` (gerado pelo Next) aponta a documentação
> da versão instalada, em `front/node_modules/next/dist/docs/`.

---

## 3. Contrato da API

É contrato interno do A4: o front fala só com o back, e nunca com o Kafka (regra da
arquitetura 6c). Mudança aqui precisa ser combinada entre back e front.

| método | rota | para quê | resposta |
|---|---|---|---|
| POST | `/partidas` | criar partida `{ time_a, time_b, source_id }` | Partida |
| GET | `/partidas/{id}` | estado atual | Partida |
| POST | `/partidas/{id}/encerrar` | encerrar; o mock para de inventar lances | Partida |
| POST | `/decisoes/{id}/correcao` | árbitro troca o veredito `{ veredito, operador }` | Decisao |
| POST | `/pontos/{id}/desfazer` | anula o lance; ele deixa de contar no placar | Partida |
| POST | `/decisoes/{id}/replay` | pedir o clipe do lance (no mock, sempre `clip_id: null`) | `{ clip_id }` |
| POST | `/camera/enquadrar?pan_deg=&tilt_deg=` | apontar a câmera (no mock, só ecoa) | `{ status, pan_deg, tilt_deg }` |
| GET | `/eventos?partida={id}` | SSE: evento `partida` com a Partida inteira a cada mudança | `text/event-stream` |

### Decisao

```json
{
  "decisao_id": "uuid",
  "veredito": "dentro | fora | duvida",
  "distancia_cm": 20.6,
  "banda_cm": 15.1,
  "lado": "A | B",
  "track_id": "t-0767",
  "source_id": "cam0",
  "artifact_version": "cal-cam0-3",
  "origem": "automatica | corrigida",
  "operador": null,
  "veredito_automatico": null,
  "anulada": false,
  "instante": "2026-10-14T13:41:49.287Z"
}
```

- `distancia_cm` positivo é fora; `banda_cm` é a incerteza (2σ).
- `duvida` quer dizer que a banda cruzou a linha. A tela deve mostrar isso como pedido de
  decisão ao árbitro, e não como erro.
- `lado` é o lado da quadra onde a bola quicou. Dentro no lado A dá ponto ao B; fora no
  lado A dá ponto ao A.
- Depois de uma correção, `origem` vira `corrigida` e `veredito_automatico` guarda o que o
  sistema tinha proposto.
- `artifact_version` é a versão da calibração do I3 que decidiu o lance.

### Partida

```json
{
  "id": "demo",
  "time_a": "Time A",
  "time_b": "Time B",
  "source_id": "cam0",
  "encerrada": false,
  "decisoes": [ /* Decisao, do mais antigo ao mais novo */ ],
  "placar": { "sets": { "A": 0, "B": 0 }, "pontos": { "A": 2, "B": 1 } }
}
```

O placar é sempre recalculado a partir das decisões (set a 25 com dois de vantagem, 5º set
a 15). Por isso corrigir ou desfazer qualquer lance antigo atualiza o placar sem nenhuma
lógica extra no front.

---

## 4. Problemas comuns

| sintoma | causa | o que fazer |
|---|---|---|
| tela em "conectando…" ou "sem conexão com o back" | back desligado ou em outra porta | suba o back; confira `NEXT_PUBLIC_API_URL` no `front/.env.local` |
| mudou o `.env.local` e nada aconteceu | o Next lê `NEXT_PUBLIC_` ao subir | pare e rode `npm run dev` de novo |
| `address already in use` | porta 8000 ou 3000 ocupada | `--port 8001` no uvicorn ou `npm run dev -- -p 3001`, e ajuste o `.env.local` |
| erro de CORS no console | back de outro lugar, sem o middleware | o mock libera qualquer origem; confira se está rodando o `back/main.py` |
| placar zerou | o back reiniciou (tudo fica em memória) | é esperado no mock |
| `uvicorn` não para no Ctrl+C | conexão SSE aberta | Ctrl+C de novo, ou feche a aba |

---

## 5. Score Manager e integração com P7/Kafka

O placar é recalculado a partir de `decisoes` sempre que entra um lance automático, o árbitro corrige o veredito ou anula um lance. A mesma decisão automática não é inserida duas vezes se chegar novamente com o mesmo `decisao_id`. O front não se conecta ao Kafka: todas as ações passam pela API A4.

### Modo local de desenvolvimento

Por padrão, `A4_MODO_DEMO=true` gera lances fictícios para testar a interface. Para desligar o gerador:

```bash
A4_MODO_DEMO=false uvicorn main:app --reload --port 8000
```

### Conectar ao Kafka real

Instale as dependências atualizadas e configure o backend:

```bash
pip install -r requirements.txt
export A4_KAFKA_ENABLED=true
export A4_KAFKA_BOOTSTRAP_SERVERS=34.66.235.91:9093
export A4_MODO_DEMO=false
uvicorn main:app --reload --port 8000
```

No PowerShell, use `$env:A4_KAFKA_ENABLED="true"`, `$env:A4_KAFKA_BOOTSTRAP_SERVERS="34.66.235.91:9093"` e `$env:A4_MODO_DEMO="false"` antes de iniciar o Uvicorn. As variáveis devem ser definidas no terminal do backend.

O A4 publica comandos de câmera em `ods.p7.move.command` usando um envelope com `message_type: "command"`, `schema: "ods.p7.move.command"` e `payload.pan_deg`/`payload.tilt_deg`. Ele consome `ods.p7.state` para atualizar a posição mostrada na interface e `ods.regra.evento_consolidado` para receber decisões automáticas. O evento de regra deve conter `payload.veredito` (`dentro`, `fora` ou `duvida`) e `payload.lado` (`A` ou `B`); também são aceitos os aliases `verdict`, `side`, `decision` e `decisao`.

Endpoints úteis:

- `GET /health`: informa se a integração Kafka está habilitada.
- `GET /camera/estado`: posição e estado mais recente recebido em `ods.p7.state`.
- `POST /camera/enquadrar?pan_deg=10&tilt_deg=5`: publica um comando em `ods.p7.move.command`. O ângulo mostrado na tela só muda quando chega o estado confirmado do P7.

Se o Kafka não estiver habilitado, `/camera/enquadrar` responde HTTP 503 em vez de fingir que a câmera se moveu. O host padrão é o do guia de Kafka do projeto; ajuste `A4_KAFKA_BOOTSTRAP_SERVERS` se o ambiente da equipe usar outro broker. Credenciais/TLS adicionais, se exigidas pelo cluster, devem ser adicionadas à configuração do cliente em `back/kafka_bridge.py`.

Teste rápido do Score Manager e do contrato de integração:

```bash
python test_score_manager.py
python test_placar.py
python test_arbitragem.py
```
