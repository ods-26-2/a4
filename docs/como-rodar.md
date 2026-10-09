# Como rodar o pipeline do A4

Como testar a cadeia **I3 → I2 → A4**: por arquivo e pipe, com janela, pelo Kafka local
e pelo Kafka do projeto. Cada seção funciona sozinha.

O A4 não roda sem os outros dois. Ele precisa da **calibração** do I3, a homografia que
converte pixel em metro, e das **trilhas** do I2. O I3 só precisa rodar de novo quando os
pontos da quadra mudarem ou quando a câmera se mexer.

---

## 0. Preparação (uma vez só)

### Pastas
Os três repositórios ficam clonados lado a lado. **Todos os comandos deste guia rodam a
partir da pasta que contém os três.**

```
git clone https://github.com/ods-26-2/i2
git clone https://github.com/ods-26-2/i3
git clone https://github.com/ods-26-2/a4
```

```
pasta/
├── i2/
├── i3/
└── a4/
```

### Imagens
Repita o build sempre que mudar o código de algum componente.

```
docker build -t inv-i3 i3
docker build -t inv-i2 i2
docker build -t inv-a4 a4
```

### Calibração em arquivo
Os modos 1 e 2 precisam da calibração gravada em arquivo:

```
docker run -i --rm inv-i3 < i3/dados/pontos_quadra.csv > a4/dados/calibracao.json
```

Tem que aparecer `i3: rms ... cm no holdout`. O arquivo está no `.gitignore`, então quem
acabou de clonar precisa gerar.

---

## 1. Local, sem Kafka, sem janela

O jeito mais simples. Não usa rede e não gasta crédito; só gera o vídeo.

```
cat a4/yolo/volei.csv a4/yolo/janela.csv | sort -t, -k1,1n \
  | docker run -i --rm inv-i2 --fps 29.97 --largura 1280 --altura 720 \
  | docker run -i --rm --user "$(id -u):$(id -g)" -v "$PWD/a4/dados:/app/dados" \
      inv-a4 yolo/clipe.mp4 --calib dados/calibracao.json
```

- Saída: `a4/dados/pipeline.mp4`. Para assistir: `mpv a4/dados/pipeline.mp4`, ou outro
  player.
- No fim aparece `299 quadros a 29.9700 fps · video em /app/dados/pipeline.mp4`.
- O `--user` faz o vídeo ser gravado como seu usuário, e não como root.
- O `sort` junta os dois csv por quadro. O i2 exige a entrada ordenada.

---

## 2. Local, sem Kafka, **com janela (GUI)**

A imagem do A4 usa OpenCV *headless* e não tem acesso à tela, então **a janela não abre
dentro do container**. O I2 continua no container; só o A4 roda fora, com o venv do yolo,
que tem OpenCV com Qt.

```
cat a4/yolo/volei.csv a4/yolo/janela.csv | sort -t, -k1,1n \
  | docker run -i --rm inv-i2 --fps 29.97 --largura 1280 --altura 720 \
  | (cd a4 && yolo/.venv/bin/python pipeline.py yolo/clipe.mp4 \
        --calib dados/calibracao.json --janela --velocidade 0.5)
```

| tecla / opção | efeito |
|---|---|
| `espaço` | pausa / continua |
| `q` | sai |
| `--velocidade 1.0` | tempo real |
| `--velocidade 0.25` | câmera lenta, para acompanhar a bola |

O vídeo continua sendo gravado em `a4/dados/pipeline.mp4`.

**Se o venv não existir** (clone novo), crie um só com o que o pipeline usa:

```
python3 -m venv a4/yolo/.venv
a4/yolo/.venv/bin/python -m pip install numpy opencv-python
```

O venv completo do yolo, com torch e pesos, está em `a4/yolo/requirements.txt`. Só
precisa dele para gerar detecções novas com o `detectar.py`.

---

## 3. Com Kafka **local** (broker de teste)

Exercita o caminho do barramento sem tocar no broker compartilhado. O guia
`Guia_Kafka_B2_v2.pdf` permite um broker de teste do próprio squad.

### 3.1 Subir o broker
```
docker run -d --rm --name kafka-teste -p 9092:9092 apache/kafka
```
Espere uns 10 s. Para ver se subiu:
`docker logs kafka-teste 2>&1 | grep "Kafka Server started"`.

### 3.2 Publicar calibração e trilhas
```
docker run -i --rm --network=host inv-i3 --kafka localhost:9092 < i3/dados/pontos_quadra.csv

cat a4/yolo/volei.csv a4/yolo/janela.csv | sort -t, -k1,1n \
  | docker run -i --rm --network=host inv-i2 --fps 29.97 --largura 1280 --altura 720 \
      --kafka localhost:9092
```
Cada um termina com `publicado em ods.visao....`.

### 3.3 Consumir no A4

Sem janela, dentro do container:
```
docker run --rm --network=host --user "$(id -u):$(id -g)" -v "$PWD/a4/dados:/app/dados" \
    inv-a4 yolo/clipe.mp4 --kafka localhost:9092 --ocioso 5
```

Com janela, fora do container:
```
cd a4 && yolo/.venv/bin/python -m pip install confluent-kafka   # uma vez
yolo/.venv/bin/python pipeline.py yolo/clipe.mp4 --kafka localhost:9092 --ocioso 5 --janela
```

Tem que aparecer `a4: 299 quadros da sessao sessao-1 lidos de ods.visao.identidade_atribuida`.

### 3.4 Derrubar o broker
```
docker stop kafka-teste
```
O `--rm` apaga o container e os tópicos junto. O próximo teste começa limpo.

---

## 4. Com Kafka **do projeto** (nuvem)

Os comandos são os mesmos da seção 3, com duas trocas: o endereço passa a ser
`34.66.235.91:9093` e **sai o `--network=host`**.

```
K=34.66.235.91:9093

docker run -i --rm inv-i3 --kafka $K < i3/dados/pontos_quadra.csv

cat a4/yolo/volei.csv a4/yolo/janela.csv | sort -t, -k1,1n \
  | docker run -i --rm inv-i2 --fps 29.97 --largura 1280 --altura 720 --kafka $K \
      --sessao teste-$(date +%H%M)

docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/a4/dados:/app/dados" \
    inv-a4 yolo/clipe.mp4 --kafka $K --sessao teste-HHMM
```

**Cuidados**, porque o broker é compartilhado pelos 15 squads e pago com crédito:
- Use uma `--sessao` nova a cada teste e a mesma no i2 e no a4. O a4 relê o tópico desde
  o começo e filtra pela sessão; sem isso, ele mistura testes antigos.
- Cada execução do i2 publica cerca de 300 mensagens, uma por quadro. Não deixe nada em
  loop.
- O a4 para sozinho depois de `--ocioso` segundos sem mensagem nova (padrão 10).
- O tópico `ods.visao.calibracao_publicada` é novo. Avise a TRA-1 antes do primeiro uso.

---

## 5. Só I2 → A4, sem refazer a calibração

Se o `a4/dados/calibracao.json` já existe, é o modo 1 sem o passo do I3. No Kafka, a
última calibração continua no tópico, então basta publicar as trilhas de novo.

---

## Problemas comuns

| sintoma | causa | o que fazer |
|---|---|---|
| `The function is not implemented. Rebuild the library with ... GTK` | `--janela` dentro do container | use o modo 2, fora do container |
| `FileNotFoundError: ... dados/calibracao.json` | o i3 não rodou | rode a calibração da seção 0 |
| `a4: nenhuma calibracao de cam-ref em ods.visao.calibracao_publicada` | o i3 não publicou nesse broker, ou o `--camera-id` é diferente | rode o 3.2 / 4 do i3 no mesmo broker |
| `a4: 0 quadros da sessao ...` | `--sessao` diferente entre i2 e a4 | use o mesmo valor nos dois |
| `pipeline.mp4` com dono root | faltou o `--user` no `docker run` do a4 | apague com `sudo rm` e rode com `--user` |
| `yolo/.venv/bin/pip: bad interpreter` | o venv mudou de pasta | use `yolo/.venv/bin/python -m pip` |
| `a4: mensagem descartada: ...` no stderr | mensagem fora do envelope no tópico | é esperado: ele descarta e segue (guia B2, 4.3) |

## Opções do `pipeline.py`

| opção | modo | padrão |
|---|---|---|
| `video` | todos | — (ex.: `yolo/clipe.mp4`) |
| `--calib ARQ` | arquivo e pipe; as trilhas vêm do stdin | — |
| `--kafka HOST:PORTA` | Kafka; exclusivo com `--calib` | — |
| `--camera-id` | Kafka | `cam-ref` |
| `--sessao` | Kafka | `sessao-1` |
| `--ocioso S` | Kafka | `10` |
| `--saida ARQ` | todos | `dados/pipeline.mp4` |
| `--janela` / `--velocidade` | só fora do container | desligado / `1.0` |
