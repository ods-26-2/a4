import type { Partida } from "@/lib/api";
import s from "./Placar.module.css";

/** Placar grande, legivel a distancia. So mostra; o calculo vem pronto do back. */
export default function Placar({ partida }: { partida: Partida }) {
  const { sets, pontos, saque, vencedor } = partida.placar;
  const total = partida.regra.sets_para_vencer;
  const nomeVencedor = vencedor === "A" ? partida.time_a : partida.time_b;
  const estado = vencedor ? `Vitória de ${nomeVencedor}` : partida.encerrada ? "Partida encerrada" : "Ao vivo";
  return (
    <section className={s.placar} aria-label="Placar">
      <Time nome={partida.time_a} pontos={pontos.A} sets={sets.A} total={total} sacando={saque === "A"} />
      <div className={s.meio}>
        <span className={s.set}>{vencedor ? "FIM" : `${sets.A + sets.B + 1}º SET`}</span>
        <span className={s.x}>×</span>
        <span className={s.estado}>{estado}</span>
        <span className={s.modalidade}>
          {partida.campeonato ? `${partida.campeonato.nome} · ` : ""}{partida.modalidade === "areia" ? "Areia" : "Quadra"}
        </span>
      </div>
      <Time nome={partida.time_b} pontos={pontos.B} sets={sets.B} total={total} sacando={saque === "B"} />
    </section>
  );
}

interface PropsTime { nome: string; pontos: number; sets: number; total: number; sacando: boolean }

function Time({ nome, pontos, sets, total, sacando }: PropsTime) {
  return (
    <div className={s.time}>
      <span className={s.nome}>{nome}</span>
      {/* altura reservada: o placar nao pula quando o saque troca de lado */}
      <span className={sacando ? s.saque : s.semSaque}>
        <b aria-hidden="true" /> Saque
      </span>
      <span className={s.pontos} aria-label={`${pontos} pontos`}>{pontos}</span>
      <span className={s.sets}>
        Sets
        <span className={s.bolinhas} aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <b key={i} className={i < sets ? s.ligada : undefined} />
          ))}
        </span>
        {sets}
      </span>
    </div>
  );
}
