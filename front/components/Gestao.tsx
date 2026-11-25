"use client";

import { useState, type FormEvent } from "react";
import { criarPartida, encerrarPartida, type Lado, type Modalidade, type Partida } from "@/lib/api";
import { NOMES_MODALIDADE, REGRAS } from "@/lib/modalidade";
import EditorZonas from "./EditorZonas";
import s from "./Gestao.module.css";

interface Props {
  partida: Partida | null;
  aoCriar: (p: Partida) => void;
  aoEncerrar: (p: Partida) => void;
  aviso: (t: string) => void;
}

/**
 * Criar e encerrar partida. O back nao tem rota para listar partidas nem para "iniciar":
 * criar ja deixa a partida ao vivo, e so a partida aberta na tela aparece aqui.
 */
export default function Gestao({ partida, aoCriar, aoEncerrar, aviso }: Props) {
  const [confirmando, setConfirmando] = useState(false);
  const [modalidade, setModalidade] = useState<Modalidade>("quadra");
  // os nomes digitados aparecem na escolha de quem saca
  const [timeA, setTimeA] = useState("Time A");
  const [timeB, setTimeB] = useState("Time B");

  async function criar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      aoCriar(await criarPartida({
        time_a: timeA.trim() || "Time A",
        time_b: timeB.trim() || "Time B",
        source_id: String(f.get("source_id")),
        modalidade: f.get("modalidade") as Modalidade,
        saque_inicial: f.get("saque_inicial") as Lado,
      }));
      aviso("Partida criada e ao vivo");
    } catch (err) {
      aviso(String(err));
    }
  }

  async function encerrar() {
    if (!partida) return;
    try {
      aoEncerrar(await encerrarPartida(partida.id));
      setConfirmando(false);
      aviso("Partida encerrada");
    } catch (err) {
      aviso(String(err));
    }
  }

  return (
    <>
      <section className="painel">
        <h2>Partida avulsa</h2>
        <form className={s.form} onSubmit={criar}>
          <div className={s.campos}>
            <label className={s.campo}>Time A
              <input name="time_a" value={timeA} maxLength={80} onChange={(e) => setTimeA(e.target.value)} />
            </label>
            <label className={s.campo}>Time B
              <input name="time_b" value={timeB} maxLength={80} onChange={(e) => setTimeB(e.target.value)} />
            </label>
            <label className={s.campo}>Modalidade
              <select name="modalidade" value={modalidade} onChange={(e) => setModalidade(e.target.value as Modalidade)}>
                {(Object.keys(NOMES_MODALIDADE) as Modalidade[]).map((m) => (
                  <option key={m} value={m}>{NOMES_MODALIDADE[m]}</option>
                ))}
              </select>
              <span className={s.dica}>{REGRAS[modalidade]}</span>
            </label>
            <label className={s.campo}>Começa sacando
              <select name="saque_inicial">
                <option value="A">{timeA.trim() || "Time A"}</option>
                <option value="B">{timeB.trim() || "Time B"}</option>
              </select>
            </label>
            <label className={s.campo}>Câmera
              <select name="source_id"><option>cam0</option><option>cam1</option></select>
            </label>
          </div>
          <div><button className="botao pri" type="submit">Criar partida</button></div>
        </form>
      </section>

      {partida && (
        <section className="painel">
          <h2>Partida aberta</h2>
          <p><b>{partida.time_a}</b> × <b>{partida.time_b}</b> · {partida.encerrada ? "encerrada" : "ao vivo"}</p>
          {!partida.encerrada && !confirmando && (
            <div><button className="botao perigo" onClick={() => setConfirmando(true)}>Encerrar</button></div>
          )}
          {confirmando && (
            <div className={s.confirma}>
              <b>Encerrar {partida.time_a} × {partida.time_b}?</b>
              <span>Depois disso a partida não recebe mais lances.</span>
              <div className={s.linha}>
                <button className="botao perigo" onClick={encerrar}>Sim, encerrar</button>
                <button className="botao" onClick={() => setConfirmando(false)}>Cancelar</button>
              </div>
            </div>
          )}
        </section>
      )}

      <EditorZonas sourceInicial={partida?.source_id ?? "cam0"} aviso={aviso} />
    </>
  );
}
