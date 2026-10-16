"use client";

import { useState } from "react";
import Gestao from "@/components/Gestao";
import Placar from "@/components/Placar";
import ReplayCamera from "@/components/ReplayCamera";
import { usePartida } from "@/hooks/usePartida";
import { useAviso } from "@/hooks/useAviso";
import s from "./page.module.css";

const PARTIDA_INICIAL = "demo"; // a unica que o mock cria sozinho

/**
 * Tela do arbitro. Aqui so mora o estado da tela (qual partida, qual lance, qual aba) e
 * a ligacao entre componentes e API; cada bloco visual esta em components/.
 */
export default function Home() {
  const [partidaId, setPartidaId] = useState(PARTIDA_INICIAL);
  const [aba, setAba] = useState<"partida" | "gestao">("partida");
  const { partida, offline, trocar } = usePartida(partidaId);
  const { aviso, avisar } = useAviso();

  // enquanto o lance em foco nao tem seletor (A4.3c, do Davi), vale o mais novo
  const lance = partida?.decisoes.at(-1);

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
          aoCriar={(p) => { setPartidaId(p.id); setAba("partida"); }}
          aoEncerrar={trocar}
        />
      ) : !partida ? (
        <p className={s.vazio}>{offline ? "Sem conexão com o back. Ele está rodando?" : "Conectando…"}</p>
      ) : (
        <>
          <Placar partida={partida} />
          <div className={s.corpo}>
            <div className={s.coluna}>
              {/* A4.3c e A4.3d (Davi): indicacao do lance, quadra e correcao manual entram aqui */}
              <ReplayCamera lance={lance} aviso={avisar} />
            </div>
            {/* A4.3c (Davi): lista de lances entra aqui */}
          </div>
        </>
      )}

      {aviso && <div className={s.aviso} role="status">{aviso}</div>}
    </div>
  );
}
