import type { Decisao } from "@/lib/api";
import { formatarCm, horario, ROTULO } from "@/lib/veredito";
import s from "./ListaLances.module.css";

interface Props {
  decisoes: Decisao[];
  selecionada: string | undefined;
  aoSelecionar: (id: string) => void;
}

/** Historico da partida, do mais novo para o mais antigo. Clicar escolhe o lance em foco. */
export default function ListaLances({ decisoes, selecionada, aoSelecionar }: Props) {
  return (
    <section className="painel" aria-label="Lances da partida">
      <h2>Lances · mais recente primeiro</h2>
      <ul className={s.lista}>
        {[...decisoes].reverse().map((d) => (
          <li key={d.decisao_id} className={d.anulada ? s.anulado : undefined}>
            <button type="button" aria-current={d.decisao_id === selecionada} onClick={() => aoSelecionar(d.decisao_id)}>
              <span className={`${s.tag} ${s[d.veredito]}`}>{ROTULO[d.veredito]}</span>
              <span className={s.texto}>
                {formatarCm(d.distancia_cm)} cm · lado {d.lado}
                <small>
                  {d.anulada ? "ponto desfeito" : d.origem === "corrigida" ? `corrigido por ${d.operador}` : "automático"}
                </small>
              </span>
              <span className={s.hora}>{horario(d.instante)}</span>
            </button>
          </li>
        ))}
        {decisoes.length === 0 && <li className={s.vazio}>Nenhum lance ainda.</li>}
      </ul>
    </section>
  );
}
