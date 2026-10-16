import type { Partida } from "@/lib/api";
import s from "./Placar.module.css";

const SETS_PARA_VENCER = 3;

/** Placar grande, legivel a distancia. So mostra; o calculo vem pronto do back. */
export default function Placar({ partida }: { partida: Partida }) {
  const { sets, pontos } = partida.placar;
  return (
    <section className={s.placar} aria-label="Placar">
      <Time nome={partida.time_a} pontos={pontos.A} sets={sets.A} />
      <div className={s.meio}>
        <span className={s.set}>{sets.A + sets.B + 1}º SET</span>
        <span className={s.x}>×</span>
        <span className={s.estado}>{partida.encerrada ? "Partida encerrada" : "Ao vivo"}</span>
      </div>
      <Time nome={partida.time_b} pontos={pontos.B} sets={sets.B} />
    </section>
  );
}

function Time({ nome, pontos, sets }: { nome: string; pontos: number; sets: number }) {
  return (
    <div className={s.time}>
      <span className={s.nome}>{nome}</span>
      <span className={s.pontos} aria-label={`${pontos} pontos`}>{pontos}</span>
      <span className={s.sets}>
        Sets
        <span className={s.bolinhas} aria-hidden="true">
          {Array.from({ length: SETS_PARA_VENCER }, (_, i) => (
            <b key={i} className={i < sets ? s.ligada : undefined} />
          ))}
        </span>
        {sets}
      </span>
    </div>
  );
}
