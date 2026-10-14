// contrato da api do a4 -- docs/como-usar.md, secao "Contrato"
export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Veredito = "dentro" | "fora" | "duvida";
export type Lado = "A" | "B";

export interface Decisao {
  decisao_id: string;
  veredito: Veredito;
  distancia_cm: number; // positivo e fora
  banda_cm: number; // incerteza, 2 sigma
  lado: Lado; // onde a bola quicou
  track_id: string;
  source_id: string;
  artifact_version: string; // versao da calibracao que decidiu
  origem: "automatica" | "corrigida";
  operador: string | null;
  veredito_automatico: Veredito | null;
  anulada: boolean;
  instante: string;
}

export interface Partida {
  id: string;
  time_a: string;
  time_b: string;
  source_id: string;
  encerrada: boolean;
  decisoes: Decisao[];
  placar: { sets: Record<Lado, number>; pontos: Record<Lado, number> };
}

async function post<T>(caminho: string, corpo?: unknown): Promise<T> {
  const r = await fetch(`${API}${caminho}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (!r.ok) throw new Error(`${caminho}: ${r.status} ${await r.text()}`);
  return r.json();
}

export const corrigir = (id: string, veredito: Veredito, operador: string) =>
  post<Decisao>(`/decisoes/${id}/correcao`, { veredito, operador });

export const desfazer = (id: string) => post<Partida>(`/pontos/${id}/desfazer`);

// o back manda a partida inteira a cada mudanca; devolve a funcao que fecha a conexao
export function ouvirPartida(id: string, aoMudar: (p: Partida) => void, aoCair: () => void) {
  const fonte = new EventSource(`${API}/eventos?partida=${encodeURIComponent(id)}`);
  fonte.addEventListener("partida", (e) => aoMudar(JSON.parse((e as MessageEvent).data)));
  fonte.onerror = aoCair;
  return () => fonte.close();
}
