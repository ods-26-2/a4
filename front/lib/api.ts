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
  position_m: [number, number] | null; // ponto do quique na quadra, x 0-18 m e y 0-9 m; null no mock
  track_id: string;
  source_id: string;
  artifact_version: string; // versao da calibracao que decidiu
  zones_version?: string | null; // versao da zona; null quando valeu a medida oficial
  clip?: ClipeS4; // replay do lance pelo S4 (ods.s4.clip), quando ja chegou
  point_px?: [number, number]; // onde o A4 calculou o quique, no quadro da camera
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

// 6c: o replay da jogada e um clipe do S4; o back pede (ods.s4.capture.command) e o clipe
// chega no proprio lance. url e null quando o back nao sabe abrir o media_uri do S4
export interface ClipeS4 {
  clip_id: string;
  media_uri: string;
  url: string | null;
  start_at: string;
  end_at: string;
  expires_at: string;
}

export const pedirReplay = (id: string) => post<{ pedido: string }>(`/decisoes/${id}/replay`);

// pseudo-P6: a gravacao servida pelo back no lugar do P6 e dos clipes do S4
export const VIDEO_P6 = `${API}/p6/video`;

// com o barramento ligado, a sessao de replay da camera: o player toca no mesmo ponto
export interface SessaoP6 {
  session_id: string;
  started_at: string; // origem do captured_at: lance em started_at + t esta em t no video
  publicada_em: string; // quando a volta atual comecou no relogio
}

// video muda quando o back troca de gravacao: entra na url do player para ele recarregar
export interface EstadoP6 {
  video: string | null;
  sessao: SessaoP6 | null;
}

// bolas do S1 no tempo do video (s), para desenhar por cima do player; em_jogo = a que o A4
// pos no voo da bola, as outras sao o que o detector achou e o filtro fisico descartou
export interface DeteccaoP6 {
  t: number;
  bolas: [number, number, boolean][];
}

export const deteccoesP6 = async (de: number, ate: number): Promise<DeteccaoP6[]> => {
  const r = await fetch(`${API}/p6/deteccoes?de=${de}&ate=${ate}`, { cache: "no-store" });
  return r.ok ? r.json() : [];
};

export const estadoP6 = async (): Promise<EstadoP6> => {
  const r = await fetch(`${API}/p6`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/p6: ${r.status}`);
  return r.json();
};


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

// zona da quadra: o front manda o desenho (0 a 1) e o back devolve o artefato em metros
export interface Zona {
  artifact_version: string;
  poligono_m: [number, number][];
  erro_cm: number;
  aviso?: string;
}

export interface VersaoZona {
  artifact_version: string;
  valid_from: string;
  poligono_m: [number, number][];
  erro_cm: number;
}

export interface EstadoZona {
  calibracao: string | null; // versao da calibracao do i3; sem ela nao da para converter
  zona: Zona | null; // a que vale: a versao mais nova
  versoes: VersaoZona[]; // da mais nova para a mais velha
}

export const lerZona = async (source_id: string): Promise<EstadoZona> => {
  const r = await fetch(`${API}/zonas/${encodeURIComponent(source_id)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/zonas: ${r.status} ${await r.text()}`);
  return r.json();
};

// voltar uma zona antiga cria uma versao nova com o mesmo desenho
export const usarZona = (source_id: string, versao: string) =>
  post<Zona>(`/zonas/${encodeURIComponent(source_id)}/${encodeURIComponent(versao)}/usar`);

export const salvarZona = (corpo: { source_id: string; largura: number; altura: number; pontos: { x: number; y: number }[] }) =>
  post<Zona>("/zonas", corpo);

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
