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

export interface NovaPartida {
  time_a: string;
  time_b: string;
  source_id: string;
}

export const criarPartida = (n: NovaPartida) => post<Partida>("/partidas", n);
export const encerrarPartida = (id: string) => post<Partida>(`/partidas/${id}/encerrar`);

// no mock o clip_id vem null e "aviso" explica por que (o S4 ainda nao existe)
export const pedirReplay = (id: string) =>
  post<{ clip_id: string | null; aviso?: string }>(`/decisoes/${id}/replay`);

// pan e tilt vao na query, como o back espera
export interface EstadoCamera {
  conectado: boolean;
  disponivel: boolean;
  estado_recebido?: boolean;
  pan_deg: number;
  tilt_deg: number;
  atualizado_em: string | null;
  topico: string;
  mensagem: string;
}

export const estadoCamera = async (): Promise<EstadoCamera> => {
  const r = await fetch(`${API}/camera/estado`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/camera/estado: ${r.status} ${await r.text()}`);
  return r.json();
};

export const enquadrar = (pan_deg: number, tilt_deg: number) =>
  post<{ status: string; command_id?: string; pan_deg: number; tilt_deg: number; topico?: string; aviso?: string }>(
    `/camera/enquadrar?pan_deg=${encodeURIComponent(pan_deg)}&tilt_deg=${encodeURIComponent(tilt_deg)}`,
  );

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
