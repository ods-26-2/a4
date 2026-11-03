// cola entre o editor do b6 (vendor/b6, intocado) e a api do a4
import type { Point, ZonePayload } from "@/vendor/b6/b6-zone-editor/b6_zone_editor";

/** O A4 tem uma zona so, a quadra, com os quatro cantos. O id e o nome quem da e o back. */
export function cantosDaQuadra(zonas: ZonePayload[]): Point[] {
  if (zonas.length !== 1) {
    throw new Error(`Desenhe uma zona só, a quadra. Há ${zonas.length} no editor.`);
  }
  const { points } = zonas[0];
  if (points.length !== 4) {
    throw new Error(`A quadra tem 4 cantos, e o desenho tem ${points.length}.`);
  }
  return points.map(({ x, y }) => ({ x, y }));
}
