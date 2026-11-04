# Como usar o A4 · back e front

Guia para rodar o A4 do Sprint 3 e para quem vai mexer no front. Todos os comandos rodam a
partir da pasta `a4/`.

Sem Kafka o back inventa os lances: cria uma partida chamada `demo` e põe um lance a cada
6 s. Com `A4_KAFKA_ENABLED=true` o lance é de verdade: o back lê a calibração do I3 e a
posição da bola do S1 e acha o quique (seções 1.1 e 5).

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

### 1.1 Barramento local

Kafka local só para o protótipo do squad (guia B2, seção 1); a integração com os outros
squads é no broker do projeto. Precisa de Docker.

```
docker compose up -d                                            # kafka em localhost:9092
A4_KAFKA_ENABLED=true A4_KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
    back/.venv/bin/uvicorn main:app --app-dir back --port 8000
```

Em outro terminal, publicar a calibração pelo I3 (repo `i3/`, com o venv dele):

```
cd ../i3
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py --kafka localhost:9092 < dados/pontos_quadra.csv
```

O back loga `Calibração I3 recebida: source_id=cam-ref versão=cal-cam-ref-1 …`. A calibração fica retida
no tópico `ods.i3.calibration`: reiniciar o back lê a última de novo, sem republicar.
Mensagem fora do envelope da 6c é descartada com o motivo no log. Para zerar o broker:
`docker compose down`.

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
| POST | `/decisoes/{id}/replay` | pedir o clipe do lance ao S4 (ainda não ligado: devolve `clip_id: null`) | `{ clip_id }` |
| POST | `/camera/enquadrar?pan_deg=&tilt_deg=` | apontar a câmera pelo P7 (ainda não ligado: só ecoa) | `{ status, pan_deg, tilt_deg }` |
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
python test_zonas.py
```

---

## 6. Zona da quadra (editor do B6)

A linha que decide dentro ou fora vem de uma zona marcada no editor do B6. Sem zona salva, vale a medida oficial de 18 × 9 m, e a decisão sai com `zones_version: null`.

```
aba Gestão (editor do B6) → POST /zonas → artefato ZONES em metros + ods.artifact.published
                                                                 ↓
back do A4 (regra de dentro ou fora) ← ods.s1.position ← S1
```

### Marcar a quadra

1. O back precisa de uma calibração de `ods.i3.calibration` para a câmera. Ela chega pelo Kafka ou por arquivo, em `A4_CALIBRACAO_ARQUIVO`. Pelo Kafka, o tópico é lido desde o começo, então vale também a calibração publicada antes de o back subir; sem Kafka, só pelo arquivo.
2. Na aba Gestão, em "Zona da quadra", escolha a câmera e envie uma foto de um quadro dela, na mesma proporção da calibração.
3. Clique nos 4 cantos e feche com o botão direito. O editor do B6 só funciona com mouse.
4. Clique em "Salvar zona". Cada salvamento cria uma versão nova. O editor do B6 não reabre zonas salvas, então para mudar é preciso desenhar de novo.

### Rotas

| método | rota | para quê |
|---|---|---|
| GET | `/zonas/{source_id}` | versão da calibração e zona atual da câmera |
| POST | `/zonas` | `{ source_id, largura, altura, pontos: [{ x, y }] }`, com pontos de 0 a 1 |

O `POST` responde 409 sem calibração e 422 quando o desenho não é um quadrilátero convexo ou a foto tem outra proporção.

### Como a zona entra na decisão

- `distancia_cm` é medida até a linha mais perto da zona.
- `erro_cm` é o quanto os lados desenhados fogem de 18 × 9 m. Ele soma na `banda_cm`, então um desenho ruim transforma lances perto da linha em `duvida`. Acima de `A4_ZONA_TOLERANCIA_CM` (padrão 30), a tela avisa.
- `lado` usa o centro da zona no eixo x, que corre ao longo dos 18 m no referencial do I3.
- A regra lê a zona direto do artefato, sem usar `zone_ids`: o S1 não informa a distância até a linha nem o instante do quique.

### Artefatos e S1

As versões ficam em `back/artefatos/a4/zones/<versao>/`, com `content.json` e `descriptor.json`. A pasta muda com `A4_ARTEFATOS_DIR` e é a que o S1 precisa receber em `S1_REGISTRY_DIR`. O S1 acompanha o `artifact_id` `zones-a4-<camera>`, então configure `S1_ZONES_FILE` e `S1_ZONES_VERSION` com uma versão salva. Ele só aplica uma versão nova na próxima sessão.

O A4 ainda não consta como produtor de `ZONES` na tabela de artefatos da 6c (A3, A5 e A8). Isso precisa ser combinado com a TRA-1 e a VER-6.

### Escolher a zona

Abaixo do editor ficam as zonas salvas da câmera. "Usar esta" volta uma zona antiga gravando uma versão nova com o mesmo desenho (`POST /zonas/{source_id}/{versao}/usar`): a mais nova continua sendo a que vale para a regra, para o S1 e depois de reiniciar o back.

---

## 7. Pseudo-P6, sem Kafka nem Docker

Enquanto o P6 da TRA-2 não serve vídeo, o back serve uma gravação em `GET /p6/video` e o painel "Replay e câmera" toca ela em laço, como se fosse a câmera ao vivo. Na 6c o vídeo fica fora do barramento, então nada disso passa pelo Kafka.

```
cd back && A4_CALIBRACAO_ARQUIVO=../old/yolo/calibracao-cam0.json .venv/bin/uvicorn main:app --port 8000
cd front && npm run dev
```

- **Vídeo:** `old/yolo/clipe.mp4` por padrão; outro `.mp4` com `A4_P6_VIDEO`.
- **Replay do lance:** volta o vídeo para 3 s antes do lance, toca 5 s e volta ao ao vivo. O instante do lance vira posição do vídeo pelo relógio que a tela guarda enquanto está aberta, então lance de antes de abrir a tela não tem replay. Os lances do modo demo são sorteados; o replay mostra o que o vídeo exibia naquela hora.
- **Zona:** na aba Gestão, "Usar quadro do vídeo" põe um quadro da gravação no editor do B6. A calibração vem de `old/yolo/calibracao-cam0.json`, saída do I3 para esse clipe (`main.py --source-id cam0 < dados/pontos_quadra.csv`).

### Com o barramento

Com a cadeia ligada (`sim/README.md`: câmera simulada → I1 → I2 → S1 → back com `A4_KAFKA_ENABLED=true` e `A4_MODO_DEMO=false`), o `A4_P6_VIDEO` aponta para o mesmo vídeo que a câmera toca, e o player segue a sessão dela:

- **Ao vivo:** o back guarda o último `ods.session.started` (lido do começo do tópico, como a calibração) e `GET /p6` devolve a sessão e qual vídeo serve. O player toca no mesmo ponto que a câmera e corrige se escorregar mais de 1 s; se o vídeo do back mudar, o player recarrega.
- **Replay:** o lance cai em `instante - started_at` no vídeo, exato, mesmo para lance de antes de abrir a tela.

Quando o P6 e o S4 entrarem, o player passa a tocar o stream do P6 e o replay vira o clipe de `ods.s4.clip`, pedido por `ods.s4.capture.command` (6c, A4).
