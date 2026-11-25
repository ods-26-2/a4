import type { Modalidade } from "./api";

// so os textos da tela; quem aplica a regra e o back
export const NOMES_MODALIDADE: Record<Modalidade, string> = {
  quadra: "Vôlei de quadra",
  areia: "Vôlei de areia",
};

export const REGRAS: Record<Modalidade, string> = {
  quadra: "Melhor de 5 · sets a 25 · 5º set a 15",
  areia: "Melhor de 3 · sets a 21 · 3º set a 15",
};
