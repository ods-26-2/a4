"use client";

import { useEffect, useState } from "react";
import { enquadrar, estadoCamera, pedirReplay, type Decisao } from "@/lib/api";
import s from "./ReplayCamera.module.css";

const PASSO_GRAUS = 5;

/** Replay do lance e enquadramento P7. Os ângulos exibidos vêm do estado real de ods.p7.state. */
export default function ReplayCamera({ lance, aviso }: { lance: Decisao | undefined; aviso: (t: string) => void }) {
  const [clipe, setClipe] = useState("Peça o replay para ver o clipe do lance aqui.");
  const [angulo, setAngulo] = useState({ pan: 0, tilt: 0 });
  const [status, setStatus] = useState("Consultando estado do P7…");
  const [p7Disponivel, setP7Disponivel] = useState(false);
  const [estadoRecebido, setEstadoRecebido] = useState(false);

  useEffect(() => {
    let ativo = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function atualizarEstado() {
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
    };
  }, []);

  async function replay() {
    if (!lance) return aviso("Ainda não há lance para rever");
    setClipe("Pedindo o clipe ao S4…");
    try {
      const r = await pedirReplay(lance.decisao_id);
      setClipe(r.clip_id ? `Clipe ${r.clip_id} pronto` : (r.aviso ?? "Clipe indisponível"));
    } catch (e) {
      setClipe(String(e));
    }
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
      <div className={s.video}>{clipe}</div>
      <div>
        <button className="botao pri" onClick={replay}>Replay do lance</button>
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
