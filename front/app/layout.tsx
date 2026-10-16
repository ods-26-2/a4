import type { Metadata } from "next";
import { Barlow, Barlow_Condensed } from "next/font/google";
import "./globals.css";

// titulo/numeros em Barlow Condensed (legivel de longe); texto corrido em Barlow
const titulo = Barlow_Condensed({ weight: ["500", "600", "700"], subsets: ["latin"], variable: "--fonte-titulo" });
const corpo = Barlow({ weight: ["400", "500", "600"], subsets: ["latin"], variable: "--fonte-corpo" });

export const metadata: Metadata = {
  title: "A4 · Arbitragem",
  description: "Interface do árbitro do A4",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className={`${titulo.variable} ${corpo.variable}`}>
      <body>{children}</body>
    </html>
  );
}
