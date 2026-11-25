import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // no `npm run dev` o Next so libera os scripts para localhost: aberta por 127.0.0.1 ou pelo IP da
  // maquina, a pagina nao hidrata e fica em "Conectando…". Outros enderecos (sem porta, separados
  // por virgula) em A4_DEV_ORIGINS, por exemplo A4_DEV_ORIGINS=172.18.186.193
  allowedDevOrigins: [
    "127.0.0.1",
    ...(process.env.A4_DEV_ORIGINS ?? "").split(",").map((o) => o.trim()).filter(Boolean),
  ],
};

export default nextConfig;
