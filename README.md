# A4 · esporte, captação e arbitragem

Parte do INV-1 · ODS 2026/2. O squad tem três componentes, cada um no seu repositório
e no seu container: [I2](https://github.com/ods-26-2/i2) (identidade e rastreio), [I3](https://github.com/ods-26-2/i3) (geometria e
calibração) e [A4](https://github.com/ods-26-2/a4) (arbitragem). Nenhum importa o outro: eles conversam pelo
Kafka do projeto, no envelope de `docs/INV-1_interfaces.md`, seguindo o guia
`docs/Guia_Kafka_B2_v2.pdf`.

Por enquanto este container roda o **mockup** do pipeline (`pipeline.py`); o
`a4_arbitragem.py` ainda não está ligado nele.

## Rodar

```
docker build -t inv-a4 .
<eventos do i2> | docker run -i --rm --user "$(id -u):$(id -g)" -v "$PWD/dados:/app/dados" \
    inv-a4 yolo/clipe.mp4 --calib dados/calibracao.json
```

Pelo barramento, sem stdin nem arquivo:

```
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/dados:/app/dados" \
    inv-a4 yolo/clipe.mp4 --kafka 34.66.235.91:9093 --sessao sessao-1
```

Com `--kafka`, ele lê `ods.visao.calibracao_publicada` e `ods.visao.identidade_atribuida`
com `group.id` `A4-arbitragem`, sem gravar offset. Por isso cada execução relê desde o
começo e fica com a câmera (`--camera-id`) e a sessão (`--sessao`) pedidas. Ele para
sozinho depois de `--ocioso` segundos sem mensagem nova (padrão 10), como o guia pede para
não gastar crédito. Mensagem fora do envelope é descartada e o motivo vai para o stderr.

No modo local, as entradas são `--calib`, o arquivo JSON que o i3 publicou, e no stdin os eventos do i2, uma linha
JSON por quadro. Saída: `dados/pipeline.mp4`, com a quadra reprojetada e cada trilha com id
e posição em metros. Fora do container, `--janela` abre a visualização ao vivo.
A cadeia completa está logo abaixo.

Entra trajetória já convertida por I3 e identidade de I2. Ponta da cadeia.

**Entrada** `Amostra(t_s, ponto_m, altura)`

| campo | formato | observação |
|---|---|---|
| `t_s` | float em s | mesmo relógio de I2 |
| `ponto_m` | `(x, y)` em m | **já convertido por I3** — A4 não vê homografia |
| `altura` | float | altura aparente, só precisa ter mínimo no contato |

**Saída** `Decisao(veredito, distancia_cm, banda_cm, trilha_id, camera_id, versao_calibracao, origem, operador, veredito_automatico)`

| campo | formato | observação |
|---|---|---|
| `veredito` | str | `dentro`, `fora`, `duvida` |
| `distancia_cm` | float | positivo é fora |
| `banda_cm` | float | incerteza propagada, 2σ |
| `versao_calibracao` | str | qual artefato de I3 decidiu este lance |
| `origem` / `operador` | str | `automatica` ou `corrigida`, e por quem |

**O que importa**

- A decisão não sai de um quadro. A 20 m/s a bola anda 67 cm entre quadros a 30 fps.
  O instante do quique sai do ajuste da trajetória, interpolado em sub-quadro.
- A incerteza é propagada em quadratura: calibração (I3) + rastreio (I2) + tempo. Deu
  banda de ±21 cm. Se a banda cruza a linha, o veredito é `duvida` — não um chute binário.
- Decisão automática é proposta. `origem` e `operador` existem desde o primeiro dia.

## Cadeia completa · I3 → I2 → A4

Com os três repositórios clonados lado a lado, numa mesma pasta:

```
git clone https://github.com/ods-26-2/i2 && git clone https://github.com/ods-26-2/i3 && git clone https://github.com/ods-26-2/a4
```

```
docker build -t inv-i3 i3 && docker build -t inv-i2 i2 && docker build -t inv-a4 a4

docker run -i --rm inv-i3 < i3/dados/pontos_quadra.csv > a4/dados/calibracao.json

cat a4/yolo/volei.csv a4/yolo/janela.csv | sort -t, -k1,1n \
  | docker run -i --rm inv-i2 --fps 29.97 --largura 1280 --altura 720 \
  | docker run -i --rm --user "$(id -u):$(id -g)" -v "$PWD/a4/dados:/app/dados" \
      inv-a4 yolo/clipe.mp4 --calib dados/calibracao.json
```

Isso gera `a4/dados/pipeline.mp4`. Pelo barramento, a mesma cadeia fica assim:

```
K=34.66.235.91:9093
docker run -i --rm inv-i3 --kafka $K < i3/dados/pontos_quadra.csv
cat a4/yolo/volei.csv a4/yolo/janela.csv | sort -t, -k1,1n \
  | docker run -i --rm inv-i2 --fps 29.97 --largura 1280 --altura 720 --kafka $K
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/a4/dados:/app/dados" \
    inv-a4 yolo/clipe.mp4 --kafka $K
```

Para testar sem o broker da nuvem: `docker run -d --rm --name kafka-teste -p 9092:9092
apache/kafka`, `K=localhost:9092` e `--network=host` em cada `docker run`.

## Mockup · pipeline de teste (José)

`pipeline.py` não roda mais o i2 nem o i3 dentro do processo: recebe as mensagens deles.
O pixel → metro é feito aqui com a homografia recebida, como o contrato do I3 manda.

O que ficou de fora nesta versão:
- yolo ao vivo: rode `yolo/detectar.py` para gerar o csv e mande esse csv para o i2;
- filtro `em_quadra`: ele precisava da H antes do i2, então hoje a torcida também é rastreada;
- caixa crua da detecção no vídeo.

A detecção vem de `yolo/detectar.py`, que **não é entrega do squad**: é o produtor falso que
ocupa o lugar do I1 (MOD-1) até o outro grupo entregar. O `torch` mora em `yolo/`, com o
próprio venv (`yolo/requirements.txt`), e fica fora da imagem.

**Projeto Compoonente**
- `docs/INV-1_arquitetura.pdf` declara nosso projeto de componente.
  ele deve ser seguido a fim de manter a ordem e a organização dentro do grupo.
- Onde lê-se LARA dentro dos componentes, leia-se Diego, e vice e versa.
