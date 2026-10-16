"use client";

import { useCallback, useRef, useState } from "react";

/** Mensagem curta no rodape ("Ponto desfeito"). `avisar` a mostra por 2,2 s. */
export function useAviso() {
  const [aviso, setAviso] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const avisar = useCallback((texto: string) => {
    setAviso(texto);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setAviso(""), 2200);
  }, []);

  return { aviso, avisar };
}
