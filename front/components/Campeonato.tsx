"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  criarCampeonato, iniciarJogo, lerCampeonato, listarCampeonatos,
  type Campeonato as TipoCampeonato, type Jogo, type Lado, type Modalidade,
} from "@/lib/api";
import { NOMES_MODALIDADE, REGRAS } from "@/lib/modalidade";
import s from "./Campeonato.module.css";

const ATUALIZA_MS = 3000; // a tabela acompanha os jogos ao vivo sem SSE proprio

interface Props {
  campeonatoId: string | null;
  aoEscolher: (id: string | null) => void;
  aoAbrirPartida: (partidaId: string) => void;
  aviso: (t: string) => void;
}

/**
 * Campeonato todos contra todos: cadastra os times, o back gera os jogos por rodada, cada jogo
 * vira uma partida ao ser iniciado e o ranking (regra FIVB) sai dos resultados salvos.
 */
export default function Campeonato({ campeonatoId, aoEscolher, aoAbrirPartida, aviso }: Props) {
  return campeonatoId ? (
    <Detalhe id={campeonatoId} aoVoltar={() => aoEscolher(null)} aoAbrirPartida={aoAbrirPartida} aviso={aviso} />
  ) : (
    <Lista aoEscolher={aoEscolher} aviso={aviso} />
  );
}

function Lista({ aoEscolher, aviso }: { aoEscolher: (id: string) => void; aviso: (t: string) => void }) {
  const [lista, setLista] = useState<TipoCampeonato[] | null>(null);
  const [modalidade, setModalidade] = useState<Modalidade>("quadra");

  useEffect(() => {
    listarCampeonatos().then(setLista).catch((e) => { setLista([]); aviso(String(e)); });
  }, [aviso]);

  async function criar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const times = String(f.get("times")).split("\n").map((t) => t.trim()).filter(Boolean);
    try {
      const c = await criarCampeonato({ nome: String(f.get("nome")).trim(), modalidade, times });
      aviso(`Campeonato criado com ${c.jogos.length} jogos`);
      aoEscolher(c.id);
    } catch (err) {
      aviso(String(err));
    }
  }

  return (
    <>
      <section className="painel">
        <h2>Novo campeonato</h2>
        <form className={s.form} onSubmit={criar}>
          <div className={s.campos}>
            <label className={s.campo}>Nome
              <input name="nome" required maxLength={120} placeholder="Copa da Faculdade" />
            </label>
            <label className={s.campo}>Modalidade
              <select value={modalidade} onChange={(e) => setModalidade(e.target.value as Modalidade)}>
                {(Object.keys(NOMES_MODALIDADE) as Modalidade[]).map((m) => (
                  <option key={m} value={m}>{NOMES_MODALIDADE[m]}</option>
                ))}
              </select>
              <span className={s.dica}>{REGRAS[modalidade]}</span>
            </label>
          </div>
          <label className={s.campo}>Times · um por linha
            <textarea name="times" required rows={6} placeholder={"Time A\nTime B\nTime C"} />
            <span className={s.dica}>Todos contra todos: cada time joga uma vez contra cada outro.</span>
          </label>
          <div><button className="botao pri" type="submit">Criar campeonato</button></div>
        </form>
      </section>

      <section className="painel">
        <h2>Campeonatos</h2>
        {lista === null ? (
          <p className={s.vazio}>Carregando…</p>
        ) : lista.length === 0 ? (
          <p className={s.vazio}>Nenhum campeonato ainda.</p>
        ) : (
          <ul className={s.lista}>
            {lista.map((c) => {
              const feitos = c.jogos.filter((j) => j.situacao === "concluido").length;
              return (
                <li key={c.id}>
                  <button className={s.item} onClick={() => aoEscolher(c.id)}>
                    <b>{c.nome}</b>
                    <span>{NOMES_MODALIDADE[c.modalidade]} · {c.times.length} times · {feitos}/{c.jogos.length} jogos</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </>
  );
}

interface PropsDetalhe {
  id: string;
  aoVoltar: () => void;
  aoAbrirPartida: (partidaId: string) => void;
  aviso: (t: string) => void;
}

function Detalhe({ id, aoVoltar, aoAbrirPartida, aviso }: PropsDetalhe) {
  const [c, setC] = useState<TipoCampeonato | null>(null);

  useEffect(() => {
    let vivo = true;
    const buscar = () => lerCampeonato(id).then((novo) => vivo && setC(novo)).catch(() => {});
    buscar();
    const t = setInterval(buscar, ATUALIZA_MS);
    return () => { vivo = false; clearInterval(t); };
  }, [id]);

  if (!c || c.id !== id) return <p className={s.vazio}>Carregando campeonato…</p>;

  const rodadas = [...new Set(c.jogos.map((j) => j.rodada))];
  const feitos = c.jogos.filter((j) => j.situacao === "concluido").length;

  async function iniciar(j: Jogo, saque: Lado, camera: string) {
    try {
      const p = await iniciarJogo(id, j.id, { source_id: camera, saque_inicial: saque });
      aviso(`${j.time_a} × ${j.time_b} ao vivo`);
      aoAbrirPartida(p.id);
    } catch (err) {
      aviso(String(err));
    }
  }

  return (
    <>
      <section className={`painel ${s.cabeca}`}>
        <div>
          <h2 className="rotulo">Campeonato</h2>
          <p className={s.titulo}>{c.nome}</p>
          <p className={s.dica}>{NOMES_MODALIDADE[c.modalidade]} · {REGRAS[c.modalidade]} · {feitos}/{c.jogos.length} jogos</p>
        </div>
        <button className="botao" onClick={aoVoltar}>Todos os campeonatos</button>
      </section>

      <section className="painel">
        <h2>Classificação</h2>
        <div className={s.rolagem}>
          <table className={s.tabela}>
            <thead>
              <tr>
                <th>#</th><th className={s.nomeTime}>Time</th>
                <th title="Pontos (regra FIVB)">Pts</th><th title="Jogos">J</th>
                <th title="Vitórias">V</th><th title="Derrotas">D</th>
                <th title="Sets ganhos : perdidos">Sets</th><th title="Saldo de pontos">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {c.ranking.map((t) => (
                <tr key={t.time}>
                  <td>{t.posicao}</td>
                  <td className={s.nomeTime}>{t.time}</td>
                  <td><b>{t.pontos}</b></td>
                  <td>{t.jogos}</td>
                  <td>{t.vitorias}</td>
                  <td>{t.derrotas}</td>
                  <td>{t.sets_pro}:{t.sets_contra}</td>
                  <td>{saldo(t.pontos_pro - t.pontos_contra)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={s.dica}>
          {c.modalidade === "areia"
            ? "Vitória vale 2 pontos e derrota 1."
            : "Vitória por 3×0 ou 3×1 vale 3 pontos; 3×2 vale 2 ao vencedor e 1 ao perdedor."}
          {" "}Desempate por vitórias, saldo de sets e saldo de pontos.
        </p>
      </section>

      <section className="painel">
        <h2>Jogos</h2>
        {rodadas.map((r) => (
          <div key={r} className={s.rodada}>
            <h3 className="rotulo">{r}ª rodada</h3>
            <ul className={s.jogos}>
              {c.jogos.filter((j) => j.rodada === r).map((j) => (
                <LinhaJogo key={j.id} j={j} aoIniciar={iniciar} aoAbrir={aoAbrirPartida} />
              ))}
            </ul>
          </div>
        ))}
      </section>
    </>
  );
}

const ROTULOS = { a_jogar: "A jogar", ao_vivo: "Ao vivo", concluido: "Encerrado", interrompido: "Interrompido" };

interface PropsJogo {
  j: Jogo;
  aoIniciar: (j: Jogo, saque: Lado, camera: string) => void;
  aoAbrir: (partidaId: string) => void;
}

function LinhaJogo({ j, aoIniciar, aoAbrir }: PropsJogo) {
  const [saque, setSaque] = useState<Lado>("A");
  const [camera, setCamera] = useState("cam0");
  const res = j.resultado;
  const nome = (l: Lado) => (l === "A" ? j.time_a : j.time_b);

  return (
    <li className={s.jogo}>
      <div className={s.confronto}>
        <span className={res?.vencedor === "A" ? s.vencedor : undefined}>{j.time_a}</span>
        <span className={s.sets}>{res ? `${res.sets.A} × ${res.sets.B}` : "×"}</span>
        <span className={res?.vencedor === "B" ? s.vencedor : undefined}>{j.time_b}</span>
      </div>
      <div className={s.estado}>
        <span className={`${s.chip} ${s[j.situacao]}`}>{ROTULOS[j.situacao]}</span>
        {res && <span className={s.dica}>{res.parciais.map((p) => `${p.A}-${p.B}`).join(", ")}</span>}
      </div>
      <div className={s.acoes}>
        {j.situacao === "a_jogar" || j.situacao === "interrompido" ? (
          <>
            <label className={s.mini}>Saque
              <select value={saque} onChange={(e) => setSaque(e.target.value as Lado)}>
                <option value="A">{nome("A")}</option>
                <option value="B">{nome("B")}</option>
              </select>
            </label>
            <label className={s.mini}>Câmera
              <select value={camera} onChange={(e) => setCamera(e.target.value)}>
                <option>cam0</option><option>cam1</option>
              </select>
            </label>
            <button className="botao pri" onClick={() => aoIniciar(j, saque, camera)}>
              {j.situacao === "interrompido" ? "Recomeçar" : "Iniciar"}
            </button>
          </>
        ) : (
          j.partida_id && (
            <button className="botao" onClick={() => aoAbrir(j.partida_id!)}>
              {j.situacao === "ao_vivo" ? "Acompanhar" : "Ver partida"}
            </button>
          )
        )}
      </div>
    </li>
  );
}

function saldo(n: number) {
  return n > 0 ? `+${n}` : String(n);
}
