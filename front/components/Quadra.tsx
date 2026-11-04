import type { Decisao } from "@/lib/api";
import s from "./Quadra.module.css";

// quadra de volei: 18 x 9 m. 1 m = 20 unidades do desenho, com 2 m de margem
const M = 20, MARGEM = 2 * M, L = 18 * M, A = 9 * M;

/**
 * Quadra vista de cima com o quique e o circulo da banda de erro, na orientacao da camera:
 * x de 0 a 18 m da esquerda para a direita, y = 0 (linha de fundo proxima) embaixo.
 * Lance sem position_m (o mock) fica no centro do lado, afastado da linha pela distancia.
 */
export default function Quadra({ d }: { d: Decisao }) {
  const [x, y] = d.position_m ?? [d.lado === "A" ? 4.5 : 13.5, 9 + d.distancia_cm / 100];
  const cx = MARGEM + x * M;
  const cy = MARGEM + (9 - y) * M;
  const raio = Math.max((d.banda_cm / 100) * M, 4);
  const cor = `var(--${d.veredito})`;

  return (
    <section className="painel" aria-label="Posição do quique">
      <h2>Onde a bola quicou · quadra 18 × 9 m</h2>
      <svg className={s.svg} viewBox={`0 0 ${L + 2 * MARGEM} ${A + 2 * MARGEM}`} role="img"
        aria-label={`Quique a ${Math.abs(d.distancia_cm)} cm da linha, lado ${d.lado}`}>
        <rect width={L + 2 * MARGEM} height={A + 2 * MARGEM} fill="var(--surface2)" rx="8" />
        <rect x={MARGEM} y={MARGEM} width={L} height={A} fill="var(--quadra)" stroke="var(--quadra-linha)" strokeWidth="2" />
        {/* rede e linhas de ataque (a 3 m da rede) */}
        <line x1={MARGEM + L / 2} y1={MARGEM - 6} x2={MARGEM + L / 2} y2={MARGEM + A + 6} stroke="var(--quadra-linha)" strokeWidth="3" />
        <line x1={MARGEM + L / 2 - 3 * M} y1={MARGEM} x2={MARGEM + L / 2 - 3 * M} y2={MARGEM + A} stroke="var(--quadra-linha)" opacity=".5" />
        <line x1={MARGEM + L / 2 + 3 * M} y1={MARGEM} x2={MARGEM + L / 2 + 3 * M} y2={MARGEM + A} stroke="var(--quadra-linha)" opacity=".5" />
        <text x={MARGEM + L / 4} y={MARGEM + A + 28} textAnchor="middle" className={s.lado}>LADO A</text>
        <text x={MARGEM + (3 * L) / 4} y={MARGEM + A + 28} textAnchor="middle" className={s.lado}>LADO B</text>
        <circle cx={cx} cy={cy} r={raio} fill={cor} fillOpacity=".25" stroke={cor} strokeWidth="1.5" strokeDasharray="3 2" />
        <circle cx={cx} cy={cy} r="4" fill={cor} />
      </svg>
    </section>
  );
}
