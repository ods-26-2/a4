"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { VIDEO_P6, lerZona, salvarZona, usarZona, type EstadoZona, type Zona } from "@/lib/api";
import { cantosDaQuadra } from "@/lib/zonas";
import { ZoneEditor } from "@/vendor/b6/b6-zone-editor/b6_zone_editor";
import s from "./EditorZonas.module.css";

const CAIXA_ID = "a4-editor-zonas"; // o ZoneEditor acha a caixa pelo id

interface Quadro {
  url: string;
  largura: number;
  altura: number;
}

/**
 * Marca a quadra com o editor do B6, por cima de um quadro da camera. O desenho so vale em
 * metros, e quem converte e o back, com a calibracao do I3. O editor nao reabre zonas salvas:
 * para mudar, desenha de novo e sai outra versao; voltar uma antiga tambem sai versao nova.
 */
export default function EditorZonas({ sourceInicial, aviso }: { sourceInicial: string; aviso: (t: string) => void }) {
  const [sourceId, setSourceId] = useState(sourceInicial);
  const [quadro, setQuadro] = useState<Quadro | null>(null);
  const [estado, setEstado] = useState<EstadoZona | null>(null);
  const [salvando, setSalvando] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const editor = useRef<ZoneEditor | null>(null);

  useEffect(() => {
    let ativo = true;
    lerZona(sourceId)
      .then((e) => { if (ativo) setEstado(e); })
      .catch((e) => aviso(String(e)));
    return () => { ativo = false; };
  }, [sourceId, aviso]);

  useEffect(() => {
    const el = caixa.current;
    if (!quadro || !el) return;
    const novo = new ZoneEditor(CAIXA_ID);
    novo.startDrawingMode();
    editor.current = novo;
    return () => {
      // o ZoneEditor nao tem destroy: tira o canvas para o proximo nao ficar por cima
      el.replaceChildren();
      editor.current = null;
      URL.revokeObjectURL(quadro.url);
    };
  }, [quadro]);

  // um quadro do pseudo-P6, a mesma camera que o player mostra; o back serve com CORS
  async function quadroDoP6() {
    const v = document.createElement("video");
    v.crossOrigin = "anonymous";
    v.muted = true;
    v.src = VIDEO_P6;
    try {
      await new Promise((ok, falha) => {
        v.onloadeddata = () => { v.currentTime = 0.1; }; // so depois do seek o quadro esta pronto para o canvas
        v.onseeked = ok;
        v.onerror = () => falha(new Error("Pseudo-P6 sem vídeo. Confira A4_P6_VIDEO no back."));
      });
      const tela = document.createElement("canvas");
      tela.width = v.videoWidth;
      tela.height = v.videoHeight;
      tela.getContext("2d")?.drawImage(v, 0, 0);
      const imagem = await new Promise<Blob | null>((ok) => tela.toBlob(ok, "image/jpeg", 0.9));
      if (!imagem) throw new Error("Não foi possível tirar o quadro do vídeo");
      setQuadro({ url: URL.createObjectURL(imagem), largura: tela.width, altura: tela.height });
    } catch (e) {
      aviso(e instanceof Error ? e.message : String(e));
    } finally {
      v.removeAttribute("src");
    }
  }

  // depois de gravar, a lista de versoes muda; a zona da resposta traz o aviso do desenho
  async function atualizar(zona: Zona) {
    const e = await lerZona(sourceId);
    setEstado({ ...e, zona });
    aviso(`Zona ${zona.artifact_version} em uso`);
  }

  async function usar(versao: string) {
    try {
      await atualizar(await usarZona(sourceId, versao));
    } catch (e) {
      aviso(e instanceof Error ? e.message : String(e));
    }
  }

  function escolherQuadro(e: ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    if (!arquivo) return;
    const url = URL.createObjectURL(arquivo);
    const img = new Image();
    img.onload = () => setQuadro({ url, largura: img.naturalWidth, altura: img.naturalHeight });
    img.onerror = () => { URL.revokeObjectURL(url); aviso("Não foi possível abrir essa imagem"); };
    img.src = url;
  }

  async function publicar() {
    if (!quadro || !editor.current) return;
    setSalvando(true);
    try {
      const pontos = cantosDaQuadra(editor.current.exportAllZones("Quadra", "QUADRA"));
      await atualizar(await salvarZona({ source_id: sourceId, largura: quadro.largura, altura: quadro.altura, pontos }));
    } catch (e) {
      aviso(e instanceof Error ? e.message : String(e));
    } finally {
      setSalvando(false);
    }
  }

  const zona = estado?.zona;
  const semCalibracao = estado !== null && !estado.calibracao;

  return (
    <section className="painel" aria-label="Zona da quadra">
      <h2>Zona da quadra</h2>
      <div className={s.campos}>
        <label className={s.campo}>Câmera
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
            <option>cam0</option><option>cam1</option>
          </select>
        </label>
        <label className={s.campo}>Quadro da câmera (foto)
          <input type="file" accept="image/*" onChange={escolherQuadro} />
        </label>
      </div>
      <div className={s.linha}>
        <button className="botao" onClick={quadroDoP6}>Usar quadro do vídeo</button>
      </div>

      {semCalibracao && <p className={s.alerta}>Ainda não chegou calibração do I3 para {sourceId}. Sem ela, a zona não pode ser salva.</p>}

      {quadro && (
        <>
          <p className={s.ajuda}>
            Clique nos 4 cantos da quadra e feche com o botão direito. Arraste um ponto para ajustar.
            Botão direito sobre a zona apaga.
          </p>
          <div
            id={CAIXA_ID}
            ref={caixa}
            className={s.caixa}
            style={{ aspectRatio: `${quadro.largura} / ${quadro.altura}`, backgroundImage: `url(${quadro.url})` }}
          />
          <div className={s.linha}>
            <button className="botao pri" onClick={publicar} disabled={salvando || semCalibracao}>Salvar zona</button>
            <button className="botao" onClick={() => editor.current?.clearAll()}>Limpar</button>
          </div>
        </>
      )}

      {zona ? (
        <div className={s.resumo}>
          <p><b>{zona.artifact_version}</b> · erro do desenho de {zona.erro_cm.toFixed(1).replace(".", ",")} cm em relação a 18 × 9 m</p>
          <p className={s.ajuda}>Cantos em metros: {zona.poligono_m.map(([x, y]) => `(${x.toFixed(2)}, ${y.toFixed(2)})`).join(" · ")}</p>
          {zona.aviso && <p className={s.alerta}>{zona.aviso}</p>}
        </div>
      ) : (
        estado && <p className={s.ajuda}>Sem zona salva: os lances usam a medida oficial de 18 × 9 m.</p>
      )}

      {estado && estado.versoes.length > 1 && (
        <div className={s.resumo}>
          <span className="rotulo">Zonas salvas de {sourceId}</span>
          <ul className={s.versoes}>
            {estado.versoes.map((v) => (
              <li key={v.artifact_version}>
                <span>
                  <b>{v.artifact_version}</b> · {new Date(v.valid_from).toLocaleString("pt-BR")} · erro de{" "}
                  {v.erro_cm.toFixed(1).replace(".", ",")} cm
                </span>
                {v.artifact_version === zona?.artifact_version ? (
                  <span className={s.ajuda}>em uso</span>
                ) : (
                  <button className="botao" onClick={() => usar(v.artifact_version)} disabled={semCalibracao}>Usar esta</button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
