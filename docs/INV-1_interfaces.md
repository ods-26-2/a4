# Formulário de interfaces dos componentes · INV-1

Respostas do squad INV-1 ao formulário de interfaces · ODS 2026/2 · v1

O formulário só lista componentes das camadas 1 a 3, então A4 (camada 4) fica de fora:
as respostas abaixo cobrem **I2** e **I3**.

---

## Q1 · Qual é a sua equipe?

```
INV-1
```

---

## Q2 · Componentes sob responsabilidade da equipe

Marcar **I2** e **I3**.

| Componente | Camada | O que afirma |
|---|---|---|
| I2 · Identidade e rastreio | 2 · Inferência | o objeto deste quadro é o mesmo do anterior |
| I3 · Geometria e calibração | 2 · Inferência | onde isso está, em medida real |
| ~~A4 · Esporte, arbitragem~~ | 4 · Aplicação | fora do escopo deste formulário |

---

## Q3 · Modelagem das saídas

Uma mensagem por componente: I2 publica um evento por quadro, I3 publica um evento por
calibração. Nenhum dos dois precisa de query ou command — quem chega atrasado lê a última
calibração retida no tópico, que é retenção de barramento (B3), não informação nova.

### I2 · evento por quadro

Trilhas confirmadas de uma câmera, publicadas a cada quadro.

```json
{
  "message_id": string,
  "message_type": "event",
  "schema": "ods.visao.identidade_atribuida",
  "schema_version": "1.0",
  "producer": "I2",
  "occurred_at": "2026-09-23T14:05:12.369Z",
  "published_at": "2026-09-23T14:05:12.402Z",
  "payload": {
    "camera_id": string,
    "session_id": string,
    "captured_at": string,
    "frame?": number,
    "tracks": [
      {
        "track_id": number,
        "class": string,
        "state": string,
        "u_px": number,
        "v_px": number,
        "predicted": boolean
      }
    ]
  }
}
```

### I3 · evento de calibração publicada

Artefato versionado. Publicado no bootstrap e sempre que a câmera se mover.

```json
{
  "message_id": string,
  "message_type": "event",
  "schema": "ods.visao.calibracao_publicada",
  "schema_version": "1.0",
  "producer": "I3",
  "occurred_at": "2026-09-23T14:05:12.369Z",
  "published_at": "2026-09-23T14:05:12.402Z",
  "payload": {
    "camera_id": string,
    "calibration_version": string,
    "valid_from": string,
    "homography": [[number, number, number],
                   [number, number, number],
                   [number, number, number]],
    "reference_frame": {
      "space_id": string,
      "origin": string,
      "axes": string,
      "unit": string
    },
    "reprojection_rms_cm": number,
    "holdout_points": number
  }
}
```

---

## Q4 · Significado dos campos, restrições e limitações

Transporte: Kafka do projeto (`docs/Guia_Kafka_B2_v2.pdf`). Cada schema acima é também o
nome do tópico; a chave da mensagem é o `camera_id`, para os quadros de uma câmera ficarem
na mesma partição e chegarem em ordem. `occurred_at` é o instante do fato (`captured_at` no
I2, `valid_from` no I3). `ods.visao.calibracao_publicada` é tópico novo, no padrão do guia;
falta comunicar o nome à TRA-1.

### I2 · `ods.visao.identidade_atribuida`

| Campo | Significado e restrição |
|---|---|
| `camera_id` | Câmera que originou o quadro. A identidade de I2 é intra-câmera: o mesmo objeto visto por duas câmeras tem dois `track_id`. Correlacionar fontes é de S2. |
| `session_id` | Sessão de captura. O `track_id` só é único dentro do par (`camera_id`, `session_id`). Troca de sessão — reinício, busca ou laço no replay de P6 — encerra as identidades e recomeça a numeração. |
| `captured_at` | ISO 8601 UTC com milissegundos (`...Z`). Instante de **captura** do quadro, nunca o de chegada. É o timestamp do fato; `published_at` é outra coisa e pode estar atrasado. |
| `frame?` | Índice do quadro na sessão. Opcional; existe para alinhar com o vídeo em cenário gravado (B4) e no replay (P6/S4). |
| `tracks` | Lista das trilhas confirmadas naquele quadro. Pode vir vazia. |
| `track_id` | Inteiro ≥ 1. Decisão de projeto documentada: objeto que sai de vista e volta recebe `track_id` **novo**. Isso muda o que a contagem de S1 e S5 significa, por isso está no contrato e não só no código. |
| `class` | Enum do contrato de I1: `"ball"` \| `"person"`. Fixada no nascimento da trilha, não muda depois. |
| `state` | Enum `"confirmed"` \| `"lost"`. Só trilha confirmada é publicada — o estado interno `tentativa` nunca vai ao barramento, porque publicá-lo mediria o falso positivo do detector, não a identidade. `"lost"` aparece uma única vez, no quadro em que a trilha é encerrada: é o sinal de fim para quem conta entrada e saída. |
| `u_px`, `v_px` | Centro da caixa em pixels, float (subpixel), origem no canto superior esquerdo da imagem de `camera_id`. Pode cair **fora** das dimensões do quadro quando `predicted` é `true`. |
| `predicted` | `true` = não houve detecção neste quadro; a posição vem da predição por velocidade constante. É o mecanismo que segura a identidade na oclusão e no borrão da bola. Quem precisa de posição medida filtra por `predicted: false`. |

**Cadência** · um evento por quadro por câmera (30/s na câmera de referência).

**Limitações declaradas**

- `u_px,v_px` é o centro da caixa. Para ocupação de zona no plano do chão o ponto útil é
  o de contato com o solo, que no caso de pessoa fica abaixo do centro; I2 não publica
  esse ponto hoje.
- A confiança vinda de I1 não é propagada — I2 ainda não a usa.
- O raio de associação é calibrado para 1920 px e 30 fps e escalado para outras câmeras;
  resolução ou fps fora do declarado degradam o rastreio silenciosamente.

### I3 · `ods.visao.calibracao_publicada`

| Campo | Significado e restrição |
|---|---|
| `camera_id` | Câmera a que a calibração pertence. Não vale para outra câmera, nem para a mesma depois que ela se mexeu. |
| `calibration_version` | Identificador do artefato. O consumidor **deve** registrar qual versão usou: A4 carrega essa string na decisão, e é o que permite revisar um lance meses depois. |
| `valid_from` | ISO 8601 UTC. Instante a partir do qual a calibração vale — é o timestamp do fato. Um evento novo para o mesmo `camera_id` substitui o anterior. |
| `homography` | Matriz 3×3, linha a linha, normalizada com `H[2][2] = 1`. Converte `(u, v, 1)` em ponto do plano: multiplica e divide pela terceira componente. Vale **só** para pontos sobre o plano calibrado (o chão da quadra); ponto no ar converte errado por construção. |
| `reference_frame.space_id` | Identificador do espaço de coordenadas. Tem que ser o mesmo `coordinate_space` que S1 carrega, senão os metros de cada um apontam para lugares diferentes. |
| `reference_frame.origin` | Onde fica a origem na instalação (ex.: canto da quadra). Os valores concretos da instalação pertencem a A8. |
| `reference_frame.axes` | Orientação dos eixos (ex.: `x` ao longo dos 18 m, `y` ao longo dos 9 m). |
| `reference_frame.unit` | Fixo em `"m"`. Não publicamos calibração em pixel nem em centímetro. |
| `reprojection_rms_cm` | Erro em **centímetros** no plano, medido em pontos de holdout que não entraram no ajuste. Medir nos pontos do próprio ajuste é otimista por construção: deu 0,3 cm contra 0,9 cm em pontos novos, e o número publicado é o de holdout. |
| `holdout_points` | Quantos pontos ficaram de fora do ajuste (hoje 2 de 8). Sem isso o rms não é interpretável. |

**Restrições**

- I3 é artefato versionado, não serviço de runtime: publica a transformação, não uma
  posição por quadro. Converter pixel → metro é o consumidor que faz, com a matriz que
  recebeu. Isso evita acoplamento em execução e deixa cada consumidor escolher o ponto
  que lhe importa — centro da bola, pé da pessoa.
- Refazer e republicar sempre que a câmera se mover. Calibração antiga com câmera nova não
  quebra nada: erra em silêncio.
- Os parâmetros intrínsecos de lente e sensor, que P4 usa para corrigir distorção, ainda
  não são produzidos. Entram como campo opcional numa versão futura do payload, sem
  quebrar consumidor.

---

## Q5 · Por que os outros componentes precisam dessas informações

**I2 entrega a identidade** — a afirmação de que o objeto deste quadro é o mesmo do
anterior. Sem ela cada quadro é um mundo novo.

- **S1** conta entrada e saída de zona. Sem `track_id` estável, a mesma pessoa parada na
  fronteira é contada de novo a cada quadro; é por isso que `state: "lost"` e a decisão
  documentada sobre reentrada fazem parte do contrato, não do código.
- **S2** correlaciona fontes e deduplica. Precisa de uma chave local por câmera e sessão
  para amarrar às outras câmeras — é exatamente o que `track_id` + `camera_id` +
  `session_id` são.
- **S5** e as aplicações com sobreposição desenham trajetória: sem identidade não há
  rastro, só pontos soltos.
- **A4** precisa saber qual trilha é a bola para ajustar a trajetória do quique; e
  `predicted` é o que diz se aquele ponto foi medido ou inferido.

**I3 entrega a transformação** — o que fecha a conversão de pixel para metro.

- **S1** carrega o `coordinate_space`; sem o referencial declarado por I3, a zona desenhada
  em um componente e a posição vinda de outro não falam do mesmo lugar.
- **S5** e **A8** precisam de medida real: distância, velocidade e os valores da instalação
  só existem em metros.
- **A4** decide dentro/fora comparando o ponto do quique com a linha. Isso exige o ponto em
  metros e, para os casos de fronteira — os únicos em que arbitragem automática tem valor —,
  exige também `reprojection_rms_cm` para propagar a incerteza e devolver `duvida` em vez de
  um chute binário, e `calibration_version` para justificar o lance depois.
- **P4** (camada inferior) consome os intrínsecos para corrigir distorção do stream.

Em resumo: I2 diz **quem**, I3 diz **onde** em medida real. Todo componente acima da camada 2
depende de uma das duas afirmações, e as duas só são utilizáveis com proveniência junto —
câmera, sessão, versão da calibração e o instante de captura.

---

## Pendências do contrato

Dois pontos que o contrato acima promete e o código ainda não cumpre:

| Item | Onde | O que falta |
|---|---|---|
| `state: "lost"` no último quadro | `i2/i2_rastreio.py:73` | `atualizar_quadro()` filtra as perdidas antes de publicar, então o consumidor nunca vê o fim da trilha. |
| Parâmetros intrínsecos de I3 | `i3/i3_geometria.py:54` | já marcado como `falta:` no código; P4 espera por eles. |

Para prometer menos, basta tirar `"lost"` do enum de `state` e deixar só `"confirmed"`.
