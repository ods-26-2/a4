"use client";

import { useState, type FormEvent } from "react";
import { criarPartida, encerrarPartida, type Lado, type Modalidade, type Partida } from "@/lib/api";
import EditorZonas from "./EditorZonas";
import s from "./Gestao.module.css";

// so o texto de ajuda; quem aplica a regra e o back
const REGRAS: Record<Modalidade, string> = {
  quadra: "Melhor de 5 · sets a 25 · 5º set a 15",
  areia: "Melhor de 3 · sets a 21 · 3º set a 15",
};

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

  async function criar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      aoCriar(await criarPartida({
        time_a: String(f.get("time_a")) || "Time A",
        time_b: String(f.get("time_b")) || "Time B",
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
        <h2>Nova partida</h2>
        <form className={s.form} onSubmit={criar}>
          <div className={s.campos}>
            <label className={s.campo}>Time A<input name="time_a" defaultValue="Time A" /></label>
            <label className={s.campo}>Time B<input name="time_b" defaultValue="Time B" /></label>
            <label className={s.campo}>Modalidade
              <select name="modalidade" value={modalidade} onChange={(e) => setModalidade(e.target.value as Modalidade)}>
                <option value="quadra">Vôlei de quadra</option>
                <option value="areia">Vôlei de areia</option>
              </select>
              <span className={s.dica}>{REGRAS[modalidade]}</span>
            </label>
            <label className={s.campo}>Começa sacando
              <select name="saque_inicial">
                <option value="A">Time A</option>
                <option value="B">Time B</option>
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
