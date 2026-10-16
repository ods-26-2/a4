"use client";

import { useEffect, useState } from "react";
import { ouvirPartida, type Partida } from "@/lib/api";

/**
 * Mantem a partida atualizada pelo SSE do back. O back manda a partida inteira a cada
 * mudanca, entao nao ha nada para mesclar: o estado e sempre a ultima mensagem.
 * `trocar` serve para as acoes que ja devolvem a Partida (desfazer, encerrar) aparecerem
 * na hora, sem esperar o proximo evento.
 */
export function usePartida(id: string) {
  // guardamos o id junto: ao trocar de partida, a anterior deixa de valer sem precisar zerar o estado
  const [guardada, setGuardada] = useState<Partida | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(
    () =>
      ouvirPartida(
        id,
        (p) => {
          setGuardada(p);
          setOffline(false);
        },
        () => setOffline(true),
      ),
    [id],
  );

  const partida = guardada?.id === id ? guardada : null;
  return { partida, offline, trocar: setGuardada };
}
