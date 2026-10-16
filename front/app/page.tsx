"use client";

import { useState } from "react";
import Gestao from "@/components/Gestao";
import LanceAtual from "@/components/LanceAtual";
import ListaLances from "@/components/ListaLances";
import Placar from "@/components/Placar";
import Quadra from "@/components/Quadra";
import ReplayCamera from "@/components/ReplayCamera";
import { usePartida } from "@/hooks/usePartida";
import { useAviso } from "@/hooks/useAviso";
import { corrigir, desfazer, type Veredito } from "@/lib/api";
import s from "./page.module.css";

const PARTIDA_INICIAL = "demo"; // a unica que o mock cria sozinho
const OPERADOR = "arbitro"; // TODO: vem do login quando existir

/**
 * Tela do arbitro. Aqui so mora o estado da tela (qual partida, qual lance, qual aba) e
 * a ligacao entre componentes e API; cada bloco visual esta em components/.
 */
export default function Home() {
  const [partidaId, setPartidaId] = useState(PARTIDA_INICIAL);
  const [aba, setAba] = useState<"partida" | "gestao">("partida");
  const [escolhido, setEscolhido] = useState<string>();
  const { partida, offline, trocar } = usePartida(partidaId);
  const { aviso, avisar } = useAviso();

  // sem escolha (ou escolha que sumiu), o foco acompanha o lance mais novo
  const lance = partida?.decisoes.find((d) => d.decisao_id === escolhido) ?? partida?.decisoes.at(-1);

  // o back devolve erro como excecao; mostramos como aviso em vez de quebrar a tela
  const tentar = (f: () => Promise<unknown>, ok: string) =>
    f().then(() => avisar(ok)).catch((e) => avisar(String(e)));

  const aoCorrigir = (v: Veredito) =>
    lance && tentar(() => corrigir(lance.decisao_id, v, OPERADOR), `Lance: ${v}. Placar recalculado.`);
  const aoDesfazer = () =>
    lance && tentar(() => desfazer(lance.decisao_id).then(trocar), "Ponto desfeito. Placar recalculado.");

  return (
    <div className={s.pagina}>
      <header className={s.barra}>
        <h1>A4 · Arbitragem</h1>
        <nav className={s.abas} aria-label="Telas">
          <button aria-current={aba === "partida"} onClick={() => setAba("partida")}>Partida</button>
          <button aria-current={aba === "gestao"} onClick={() => setAba("gestao")}>Gestão</button>
        </nav>
        <span className={`${s.conexao} ${offline ? s.offline : ""}`}>
          <i />{offline ? "Sem conexão com o back" : "Ligado ao back"}
        </span>
      </header>

      {aba === "gestao" ? (
        <Gestao
          partida={partida}
          aviso={avisar}
          aoCriar={(p) => { setPartidaId(p.id); setEscolhido(undefined); setAba("partida"); }}
          aoEncerrar={trocar}
        />
      ) : !partida ? (
        <p className={s.vazio}>{offline ? "Sem conexão com o back. Ele está rodando?" : "Conectando…"}</p>
      ) : (
        <>
          <Placar partida={partida} />
          <div className={s.corpo}>
            <div className={s.coluna}>
              {lance ? (
                <>
                  <LanceAtual d={lance} aoCorrigir={aoCorrigir} aoDesfazer={aoDesfazer} />
                  <Quadra d={lance} />
                </>
              ) : (
                <p className="painel">Nenhum lance ainda. O primeiro quique decidido aparece aqui.</p>
              )}
              <ReplayCamera lance={lance} aviso={avisar} />
            </div>
            <ListaLances decisoes={partida.decisoes} selecionada={lance?.decisao_id} aoSelecionar={setEscolhido} />
          </div>
        </>
      )}

      {aviso && <div className={s.aviso} role="status">{aviso}</div>}
    </div>
  );
}
