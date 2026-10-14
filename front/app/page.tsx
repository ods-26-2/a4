"use client";

import { useEffect, useState } from "react";
import { corrigir, desfazer, ouvirPartida, type Decisao, type Partida } from "@/lib/api";
import s from "./page.module.css";

const PARTIDA = "demo"; // a unica que o mock cria sozinho
const OPERADOR = "arbitro";

export default function Home() {
  const [partida, setPartida] = useState<Partida | null>(null);
  const [erro, setErro] = useState("");

  useEffect(
    () =>
      ouvirPartida(
        PARTIDA,
        (p) => {
          setPartida(p);
          setErro("");
        },
        () => setErro("sem conexão com o back — ele está rodando?"),
      ),
    [],
  );

  const agir = (f: () => Promise<unknown>) => f().catch((e) => setErro(String(e)));

  if (!partida) return <main className={s.main}>{erro || "conectando…"}</main>;

  const { placar } = partida;
  const lances = [...partida.decisoes].reverse();
  const ultimo = lances.find((d) => !d.anulada);

  return (
    <main className={s.main}>
      {erro && <p className={s.erro}>{erro}</p>}

      <section className={s.placar}>
        <Time nome={partida.time_a} sets={placar.sets.A} pontos={placar.pontos.A} />
        <span className={s.x}>×</span>
        <Time nome={partida.time_b} sets={placar.sets.B} pontos={placar.pontos.B} />
      </section>

      {ultimo && (
        <section className={`${s.ultimo} ${s[ultimo.veredito]}`}>
          <strong>{ultimo.veredito.toUpperCase()}</strong>
          <span>
            {ultimo.distancia_cm} cm ± {ultimo.banda_cm} cm · lado {ultimo.lado}
          </span>
        </section>
      )}

      <ul className={s.lances}>
        {lances.map((d) => (
          <Lance
            key={d.decisao_id}
            d={d}
            aoCorrigir={(v) => agir(() => corrigir(d.decisao_id, v, OPERADOR))}
            aoDesfazer={() => agir(() => desfazer(d.decisao_id))}
          />
        ))}
      </ul>
    </main>
  );
}

function Time({ nome, sets, pontos }: { nome: string; sets: number; pontos: number }) {
  return (
    <div className={s.time}>
      <span>{nome}</span>
      <b>{pontos}</b>
      <small>sets {sets}</small>
    </div>
  );
}

function Lance({
  d,
  aoCorrigir,
  aoDesfazer,
}: {
  d: Decisao;
  aoCorrigir: (v: "dentro" | "fora") => void;
  aoDesfazer: () => void;
}) {
  return (
    <li className={d.anulada ? s.anulado : undefined}>
      <span className={`${s.tag} ${s[d.veredito]}`}>{d.veredito}</span>
      <span>
        {new Date(d.instante).toLocaleTimeString()} · {d.distancia_cm} cm · lado {d.lado}
        {d.origem === "corrigida" && ` · corrigido (era ${d.veredito_automatico})`}
      </span>
      {!d.anulada && (
        <span className={s.botoes}>
          <button onClick={() => aoCorrigir("dentro")}>dentro</button>
          <button onClick={() => aoCorrigir("fora")}>fora</button>
          <button onClick={aoDesfazer}>desfazer</button>
        </span>
      )}
    </li>
  );
}
