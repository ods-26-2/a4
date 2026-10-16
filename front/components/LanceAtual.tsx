import type { Decisao, Veredito } from "@/lib/api";
import { formatarCm, horario, ROTULO } from "@/lib/veredito";
import s from "./LanceAtual.module.css";

interface Props {
  d: Decisao;
  aoCorrigir: (v: Veredito) => void;
  aoDesfazer: () => void;
}

/**
 * O lance selecionado: veredito grande, distancia e banda, botoes de correcao e os dados
 * de auditoria (calibracao, rastro, operador). Cada bloco tem altura reservada para a tela
 * nao pular quando o veredito muda de dentro para fora ou duvida.
 */
export default function LanceAtual({ d, aoCorrigir, aoDesfazer }: Props) {
  const emDuvida = d.veredito === "duvida" && !d.anulada;
  const outro = d.veredito === "dentro" ? "fora" : "dentro";

  const origem = d.anulada
    ? "ponto desfeito"
    : d.origem === "corrigida"
      ? `corrigido por ${d.operador} (sistema disse ${d.veredito_automatico ? ROTULO[d.veredito_automatico] : "?"})`
      : "proposta automática";

  return (
    <section className="painel" aria-label="Lance atual">
      <h2>Último lance</h2>

      <div className={`${s.lance} ${s[d.veredito]}`}>
        {/* o ::after do CSS reserva a largura de "DENTRO" para os tres vereditos terem o mesmo cartao */}
        <span className={s.veredito}>
          <span>{ROTULO[d.veredito]}</span>
        </span>
        <div className={s.detalhe}>
          <strong>
            {formatarCm(d.distancia_cm)} cm ± {d.banda_cm.toFixed(1).replace(".", ",")} cm
          </strong>
          <span>Bola no lado {d.lado} · {origem}</span>
        </div>
      </div>

      {/* "duvida" nao e erro: a banda cruzou a linha e o arbitro precisa decidir */}
      <div className={s.reserva}>
        {emDuvida && (
          <p className={s.aviso}>A margem de erro cruza a linha. Decida este lance: dentro ou fora.</p>
        )}
      </div>

      <div className={s.acoes}>
        {d.anulada ? null : emDuvida ? (
          <>
            <button className={s.dentro} onClick={() => aoCorrigir("dentro")}>Dentro</button>
            <button className={s.fora} onClick={() => aoCorrigir("fora")}>Fora</button>
            <button onClick={aoDesfazer}>Desfazer ponto</button>
          </>
        ) : (
          <>
            {/* confirmar = corrigir para o mesmo veredito: so registra o operador */}
            <button className={s.pri} onClick={() => aoCorrigir(d.veredito)}>
              Confirmar
              <small>{d.origem === "automatica" ? "mantém a proposta" : "mantém a correção"}</small>
            </button>
            <button className={s[outro]} onClick={() => aoCorrigir(outro)}>Trocar para {outro}</button>
            <button onClick={aoDesfazer}>Desfazer ponto</button>
          </>
        )}
      </div>

      <dl className={s.meta}>
        <Dado nome="Calibração" valor={d.artifact_version} />
        <Dado nome="Rastro" valor={d.track_id} />
        <Dado nome="Câmera" valor={d.source_id} />
        <Dado nome="Origem" valor={d.origem === "corrigida" ? "Corrigida" : "Automática"} />
        <Dado nome="Operador" valor={d.operador ?? "—"} />
        <Dado nome="Lance" valor={`às ${horario(d.instante)}`} />
      </dl>
    </section>
  );
}

function Dado({ nome, valor }: { nome: string; valor: string }) {
  return (
    <div>
      <dt className="rotulo">{nome}</dt>
      <dd>{valor}</dd>
    </div>
  );
}
