"use client";

import { useState } from "react";
import { enquadrar, pedirReplay, type Decisao } from "@/lib/api";
import s from "./ReplayCamera.module.css";

const PASSO_GRAUS = 5;

/**
 * Replay do lance (back -> S4) e enquadramento da camera (back -> P7).
 * O player de B6 ainda nao existe, entao o clipe aparece num espaco reservado; troque o
 * <div> do video pelo player quando ele chegar. `aviso` repassa mensagens para o Toast.
 */
export default function ReplayCamera({ lance, aviso }: { lance: Decisao | undefined; aviso: (t: string) => void }) {
  const [clipe, setClipe] = useState("Peça o replay para ver o clipe do lance aqui.");
  const [angulo, setAngulo] = useState({ pan: 0, tilt: 0 });
  const [status, setStatus] = useState("OK");

  async function replay() {
    if (!lance) return aviso("Ainda não há lance para rever");
    setClipe("Pedindo o clipe ao S4…");
    try {
      const r = await pedirReplay(lance.decisao_id);
      // clip_id null = S4 indisponivel (hoje, sempre, no mock)
      setClipe(r.clip_id ? `Clipe ${r.clip_id} pronto` : (r.aviso ?? "Clipe indisponível"));
    } catch (e) {
      setClipe(String(e));
    }
  }

  async function mover(dPan: number, dTilt: number, centralizar = false) {
    const pan = centralizar ? 0 : angulo.pan + dPan;
    const tilt = centralizar ? 0 : angulo.tilt + dTilt;
    try {
      const r = await enquadrar(pan, tilt);
      setStatus(r.status);
      if (r.status === "OK") setAngulo({ pan: r.pan_deg, tilt: r.tilt_deg }); // fora do alcance: fica onde estava
    } catch (e) {
      aviso(String(e));
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
          <button onClick={() => mover(0, PASSO_GRAUS)} aria-label="Para cima">▲</button>
          <span />
          <button onClick={() => mover(-PASSO_GRAUS, 0)} aria-label="Para a esquerda">◀</button>
          <button onClick={() => mover(0, 0, true)} aria-label="Centralizar">0°</button>
          <button onClick={() => mover(PASSO_GRAUS, 0)} aria-label="Para a direita">▶</button>
          <span />
          <button onClick={() => mover(0, -PASSO_GRAUS)} aria-label="Para baixo">▼</button>
          <span />
        </div>
        <div className={s.angulos}>
          <span className="rotulo">Câmera</span>
          <span>pan <b>{angulo.pan.toFixed(1)}°</b></span>
          <span>tilt <b>{angulo.tilt.toFixed(1)}°</b></span>
          <span className={s.status}>status: {status}</span>
        </div>
      </div>
    </section>
  );
}
