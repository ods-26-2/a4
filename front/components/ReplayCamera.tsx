"use client";

import { useEffect, useRef, useState } from "react";
import { VIDEO_P6, deteccoesP6, enquadrar, estadoCamera, estadoP6, pedirReplay, type Decisao, type DeteccaoP6, type SessaoP6 } from "@/lib/api";
import s from "./ReplayCamera.module.css";

const PASSO_GRAUS = 5;
const ANTES_S = 3; // replay: o lance e os segundos antes dele
const DEPOIS_S = 2;
const MARCAS = 600; // ~2 min de relogio do ao vivo, a 4-5 timeupdate por segundo
// o "ao vivo" roda atras da camera o tempo da analise (I1 -> I2 -> S1 -> A4, ~2 s): assim o quadro
// na tela ja tem as deteccoes e o lance dele, como numa transmissao com analise
const ATRASO_S = 3;

/**
 * Câmera ao vivo, replay do lance e enquadramento P7. Os ângulos exibidos vêm do estado real
 * de ods.p7.state.
 *
 * O vídeo é a gravação que a câmera do jogo toca, servida pelo back, e o replay é um salto
 * nela. Com o barramento, o player segue a sessão da câmera (ods.session.started) e o lance
 * cai em instante - started_at, exato; sem ele, pelo relógio guardado enquanto a tela está
 * aberta.
 */
export default function ReplayCamera({ lance, aviso }: { lance: Decisao | undefined; aviso: (t: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const relogio = useRef<[number, number][]>([]); // [Date.now(), currentTime] do ao vivo
  const aoVivo = useRef(true);
  const sessao = useRef<SessaoP6 | null>(null);
  const fimReplay = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [modo, setModo] = useState<"ao vivo" | "replay">("ao vivo");
  const [gravacao, setGravacao] = useState<string | null>(null);
  const [falhou, setFalhou] = useState<string | null>(null); // gravacao que o navegador nao abriu
  const [clipe, setClipe] = useState<string | null>(null); // url do clipe do S4 tocando
  const pedidos = useRef(new Set<string>()); // lances ja pedidos ao S4
  const tela = useRef<HTMLCanvasElement>(null);
  const deteccoes = useRef<DeteccaoP6[]>([]);
  const [mostrar, setMostrar] = useState(true);
  const semVideo = !gravacao || falhou === gravacao;
  const [angulo, setAngulo] = useState({ pan: 0, tilt: 0 });
  const [status, setStatus] = useState("Consultando estado do P7…");
  const [p7Disponivel, setP7Disponivel] = useState(false);
  const [estadoRecebido, setEstadoRecebido] = useState(false);

  useEffect(() => {
    let ativo = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function atualizarEstado() {
      try {
        const p6 = await estadoP6();
        sessao.current = p6.sessao;
        if (ativo && p6.video) setGravacao(p6.video);
      } catch {
        // back fora do ar: o estado do P7 abaixo avisa
      }
      try {
        const estado = await estadoCamera();
        if (!ativo) return;
        setP7Disponivel(estado.disponivel);
        setEstadoRecebido(Boolean(estado.estado_recebido));
        setStatus(estado.mensagem || (estado.disponivel ? "Kafka conectado" : "P7 indisponível"));
        if (estado.disponivel) setAngulo({ pan: estado.pan_deg, tilt: estado.tilt_deg });
      } catch {
        if (ativo) {
          setP7Disponivel(false);
          setEstadoRecebido(false);
          setStatus("Não foi possível consultar ods.p7.state");
        }
      } finally {
        if (ativo) timer = setTimeout(atualizarEstado, 2000);
      }
    }

    void atualizarEstado();
    return () => {
      ativo = false;
      if (timer) clearTimeout(timer);
      clearTimeout(fimReplay.current);
    };
  }, []);

  // sobreposicao: busca as bolas do S1 em volta do ponto do video e desenha a do quadro atual
  useEffect(() => {
    if (!mostrar || clipe) return;
    let ativo = true;
    let quadro = 0;
    const canvas = tela.current;
    const busca = setInterval(async () => {
      const v = video.current;
      if (v && sessao.current) deteccoes.current = await deteccoesP6(v.currentTime - 1, v.currentTime + 2);
    }, 700);
    const desenhar = () => {
      const v = video.current, c = tela.current;
      if (v && c && ativo) {
        c.width = c.clientWidth;
        c.height = c.clientHeight;
        const g = c.getContext("2d")!;
        g.clearRect(0, 0, c.width, c.height);
        // o video fica inteiro dentro da caixa (object-fit: contain)
        const esc = Math.min(c.width / (v.videoWidth || 1280), c.height / (v.videoHeight || 720));
        const ox = (c.width - (v.videoWidth || 1280) * esc) / 2, oy = (c.height - (v.videoHeight || 720) * esc) / 2;
        const t = v.currentTime;
        const perto = deteccoes.current.reduce<DeteccaoP6 | null>((m, d) => (!m || Math.abs(d.t - t) < Math.abs(m.t - t) ? d : m), null);
        if (perto && Math.abs(perto.t - t) < 0.04) {
          for (const [u, w, emJogo] of perto.bolas) {
            g.beginPath();
            g.arc(ox + u * esc, oy + w * esc, emJogo ? 9 : 7, 0, 2 * Math.PI);
            g.lineWidth = emJogo ? 3 : 1.5;
            g.strokeStyle = emJogo ? "#22e06b" : "#ffd23f";
            g.stroke();
          }
        }
        // onde o A4 calculou o quique, perto do instante do lance
        const s = sessao.current;
        if (lance?.point_px && s) {
          const tl = (Date.parse(lance.instante) - Date.parse(s.started_at)) / 1000;
          if (Math.abs(t - tl) < 0.6) {
            g.beginPath();
            g.arc(ox + lance.point_px[0] * esc, oy + lance.point_px[1] * esc, 16, 0, 2 * Math.PI);
            g.lineWidth = 3;
            g.strokeStyle = "#ff3b3b";
            g.stroke();
          }
        }
      }
      quadro = requestAnimationFrame(desenhar);
    };
    quadro = requestAnimationFrame(desenhar);
    return () => {
      ativo = false;
      clearInterval(busca);
      cancelAnimationFrame(quadro);
      canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [mostrar, clipe, lance]);

  function marcar() {
    const v = video.current;
    if (!v || !aoVivo.current) return;
    const s = sessao.current;
    if (s) {
      // o quadro que a camera mandou ao I1 ha ATRASO_S; corrige se escorregar mais de 1 s
      const esperado = (((Date.now() - Date.parse(s.publicada_em)) / 1000 - ATRASO_S) % v.duration + v.duration) % v.duration;
      if (Math.abs(v.currentTime - esperado) > 1) v.currentTime = esperado;
    }
    relogio.current.push([Date.now(), v.currentTime]);
    if (relogio.current.length > MARCAS) relogio.current.shift();
  }

  function replay() {
    const v = video.current;
    if (!lance) return aviso("Ainda não há lance para rever");
    // 6c: o replay e o clipe do S4. se ja chegou, toca ele; senao pede (uma vez) e, ate chegar,
    // salta na gravacao que ja toca
    if (lance.clip?.url) {
      aoVivo.current = false;
      clearTimeout(fimReplay.current);
      setModo("replay");
      return setClipe(lance.clip.url);
    }
    if (!pedidos.current.has(lance.decisao_id)) {
      pedidos.current.add(lance.decisao_id);
      pedirReplay(lance.decisao_id).catch(() => pedidos.current.delete(lance.decisao_id));
    }
    if (!v || semVideo) return aviso("Pseudo-P6 sem vídeo");
    const alvo = Date.parse(lance.instante);
    const marca = relogio.current.findLast(([t]) => t <= alvo);
    const s = sessao.current;
    if (!s && !marca) return aviso("Esse lance é de antes desta tela abrir o vídeo; não há gravação dele");
    const instante = s ? (alvo - Date.parse(s.started_at)) / 1000 : (marca![1] + (alvo - marca![0]) / 1000) % v.duration;
    if (instante < 0 || instante > v.duration) return aviso("Esse lance não é da gravação que está tocando");
    const volta = { t: Date.now(), pos: v.currentTime };
    aoVivo.current = false;
    setModo("replay");
    v.currentTime = Math.max(0, instante - ANTES_S);
    clearTimeout(fimReplay.current);
    fimReplay.current = setTimeout(() => {
      // volta para onde o ao vivo estaria se não tivesse parado
      v.currentTime = (volta.pos + (Date.now() - volta.t) / 1000) % v.duration;   // ja com o atraso
      aoVivo.current = true;
      setModo("ao vivo");
    }, (ANTES_S + DEPOIS_S) * 1000);
  }

  async function mover(dPan: number, dTilt: number, centralizar = false) {
    if (!p7Disponivel) return aviso("Câmera P7 indisponível. Verifique A4_KAFKA_ENABLED e a conexão Kafka.");
    const pan = centralizar ? 0 : angulo.pan + dPan;
    const tilt = centralizar ? 0 : angulo.tilt + dTilt;
    try {
      const r = await enquadrar(pan, tilt);
      setStatus(r.aviso ?? `Comando enviado (${r.command_id ?? "sem ID"}); aguardando ods.p7.state`);
      // Não altera os ângulos de forma otimista: só o estado publicado pelo P7 confirma a posição.
    } catch (e) {
      aviso(String(e));
      setStatus("Falha ao enviar comando para o P7");
    }
  }

  return (
    <section className="painel" aria-label="Replay e câmera">
      <h2>Replay e câmera</h2>
      {semVideo ? (
        <div className={s.video}>{gravacao ? "Pseudo-P6 sem vídeo. Confira A4_P6_VIDEO no back." : "Carregando o vídeo…"}</div>
      ) : (
        <div className={s.tela}>
          <video ref={video} src={clipe ?? `${VIDEO_P6}?gravacao=${encodeURIComponent(gravacao)}`} autoPlay muted
            loop={!clipe} playsInline onTimeUpdate={marcar}
            onEnded={() => { if (clipe) { setClipe(null); aoVivo.current = true; setModo("ao vivo"); } }}
            onError={() => { if (clipe) { setClipe(null); aoVivo.current = true; setModo("ao vivo"); aviso("O clipe do S4 não abriu; replay na gravação"); } else setFalhou(gravacao); }} />
          <canvas ref={tela} className={s.sobreposicao} aria-hidden="true" />
          <span className={`${s.selo} ${modo === "replay" ? s.replay : ""}`}>{clipe ? "replay · S4" : modo}</span>
        </div>
      )}
      <div>
        <button className="botao pri" onClick={replay}>Replay do lance</button>
        <label className={s.opcao}>
          <input type="checkbox" checked={mostrar} onChange={(e) => setMostrar(e.target.checked)} /> Mostrar detecções
        </label>
      </div>

      <div className={s.camera}>
        <div className={s.pad} role="group" aria-label="Enquadramento da câmera">
          <span />
          <button disabled={!p7Disponivel} onClick={() => mover(0, PASSO_GRAUS)} aria-label="Para cima">▲</button>
          <span />
          <button disabled={!p7Disponivel} onClick={() => mover(-PASSO_GRAUS, 0)} aria-label="Para a esquerda">◀</button>
          <button disabled={!p7Disponivel} onClick={() => mover(0, 0, true)} aria-label="Centralizar">0°</button>
          <button disabled={!p7Disponivel} onClick={() => mover(PASSO_GRAUS, 0)} aria-label="Para a direita">▶</button>
          <span />
          <button disabled={!p7Disponivel} onClick={() => mover(0, -PASSO_GRAUS)} aria-label="Para baixo">▼</button>
          <span />
        </div>
        <div className={s.angulos}>
          <span className="rotulo">P7 · {!p7Disponivel ? "indisponível" : estadoRecebido ? "estado recebido" : "barramento conectado"}</span>
          <span>pan <b>{angulo.pan.toFixed(1)}°</b></span>
          <span>tilt <b>{angulo.tilt.toFixed(1)}°</b></span>
          <span className={s.status}>{status}</span>
          <span className={s.status}>Tópicos: ods.p7.move.command / ods.p7.state</span>
        </div>
      </div>
    </section>
  );
}
