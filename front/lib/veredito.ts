// textos e formatos que mais de um componente usa
import type { Veredito } from "./api";

export const ROTULO: Record<Veredito, string> = {
  dentro: "Dentro",
  fora: "Fora",
  duvida: "Dúvida",
};

// 21.7 -> "+21,7"; positivo e fora, negativo e dentro
export const formatarCm = (n: number) =>
  (n > 0 ? "+" : "") + n.toFixed(1).replace(".", ",");

export const horario = (iso: string) =>
  new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
