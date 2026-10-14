import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "A4 · Arbitragem",
  description: "Interface do árbitro do A4",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
