"""rule engine do a4 -- card A4.1 do sprint 3

entra a posicao da bola por quadro (point_px de ods.s1.position) e a calibracao de
ods.i3.calibration; sai uma decisao dentro, fora ou duvida no formato da api do a4.
a decisao automatica e so proposta: o arbitro decide.

o quique sai da trajetoria 3D (trajetoria.py): arcos balisticos e a altura de cada contato.
so contato no chao, dentro da incerteza do ajuste, vira lance; toque de jogador fica no ar.
"""
import math
import uuid
from collections import namedtuple
from datetime import datetime, timezone

import numpy as np

from trajetoria import (Arco, Camera, SIGMA_PX, chegada_ao_chao, contato, contato_conjunto,
                        quique_possivel)

QUADRA = (18.0, 9.0)                                  # volei FIVB, rede em x = 9
CANTOS = ((0.0, 0.0), (18.0, 0.0), (18.0, 9.0), (0.0, 9.0))  # medida oficial, sem zona salva

# o que a fisica e a regra pedem, nao o video
MIN_ARCO = 8           # quadros de um voo: 0,27 s a 30 fps, a gravidade ja curva o arco
FOLGA = 4.0            # erro, em sigmas do ponto, para o ponto ainda ser do arco
VAO_S = 0.3            # buraco maximo entre o fim de um arco e o comeco do outro no mesmo toque
SALTO_PX = 45          # quanto a bola anda entre dois quadros: 30 m/s a 18 m da camera
JANELA_S = 1.0         # pontos soltos guardados para achar o proximo arco
VEL_MAX = 40.0         # m/s; saque mais forte do volei fica perto de 35
Z_JOGADOR = 0.6        # m; acima disso o contato e de jogador mesmo com 2 sigma de folga
# o chao nao da energia a bola nem desvia o movimento no plano: ela volta mais devagar na
# vertical (restituicao < 1) e segue na mesma direcao, perdendo um pouco de velocidade
RESTITUICAO = (0.3, 1.0)
HORIZONTAL = (0.4, 1.0)    # velocidade no plano depois / antes, mesma direcao
BOLA_MORTA_S = 3.0     # bola no chao encerra o rally; o saque seguinte vem bem depois disso
GINASIO = ((-12.0, 30.0), (-12.0, 21.0), (-1.0, 25.0))  # x, y, z possiveis da bola, em m

Calibracao = namedtuple("Calibracao", "source_id versao K dist H rms_cm space_id largura altura")
# a quadra marcada no editor do b6, em metros (zonas.py)
Zona = namedtuple("Zona", "poligono erro_cm versao")


def calibracao(ev):
    """envelope de ods.i3.calibration -> Calibracao"""
    p = ev["payload"]
    i = p["intrinsics"]
    K = np.array([[i["fx"], 0, i["cx"]], [0, i["fy"], i["cy"]], [0, 0, 1]], float)
    return Calibracao(ev["source_id"], ev["artifact_version"], K,
                      np.array(p["distortion"], float),
                      np.array(p["homography_px_to_m"], float), p["reprojection_rms_cm"],
                      p["reference_frame"]["space_id"], p.get("image_width"), p.get("image_height"))


def para_metros(cal, px):
    """6c: homography_px_to_m sai do pixel bruto, entao nao se corrige a distorcao antes"""
    v = cal.H @ np.array([px[0], px[1], 1.0])
    return tuple(v[:2] / v[2])


def banda_de_duvida_cm(rms_calib_cm, sigma_contato_cm, erro_zona_cm=0.0):
    """junta os erros de i3, do ponto de contato (do ajuste) e do desenho da zona num sigma"""
    return float(np.hypot(np.hypot(rms_calib_cm, sigma_contato_cm), erro_zona_cm))


def distancia_cm(ponto, poligono):
    """distancia ate a linha mais perto: positivo fora, negativo dentro"""
    x, y = ponto
    dentro, menor = False, float("inf")
    for (ax, ay), (bx, by) in zip(poligono, (*poligono[1:], poligono[0])):
        dx, dy = bx - ax, by - ay
        t = np.clip(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
        menor = min(menor, float(np.hypot(x - (ax + t * dx), y - (ay + t * dy))))
        if (ay > y) != (by > y) and x < ax + (y - ay) * dx / dy:
            dentro = not dentro
    return (-menor if dentro else menor) * 100.0


def arbitrar(ponto_m, sigma_cm, source_id, versao, track_id, instante, zona=None):
    """decide dentro ou fora pela zona; sem zona, pela medida oficial. se a banda cruza a linha, duvida"""
    poligono = zona.poligono if zona else CANTOS
    d_cm = distancia_cm(ponto_m, poligono)
    # eixo x ao longo dos 18 m, como no referencial do i3; a rede fica no meio da quadra
    rede_x = sum(p[0] for p in poligono) / len(poligono)
    banda = 2.0 * sigma_cm                            # banda de dois sigma
    veredito = "fora" if d_cm - banda > 0 else "dentro" if d_cm + banda < 0 else "duvida"
    return {"decisao_id": str(uuid.uuid4()), "veredito": veredito,
            "distancia_cm": round(d_cm, 1), "banda_cm": round(banda, 1),
            "lado": "A" if ponto_m[0] < rede_x else "B",
            "position_m": [round(ponto_m[0], 2), round(ponto_m[1], 2)], "track_id": track_id,
            "source_id": source_id, "artifact_version": versao,
            "zones_version": zona.versao if zona else None, "origem": "automatica",
            "operador": None, "veredito_automatico": None, "anulada": False,
            "instante": instante}


class Detector:
    """acha o toque da bola no chao numa camera, quadro a quadro

    a bola em jogo e a que voa como projetil: o arco atual fica com o ponto que ele preve, e
    os pontos soltos (outra bola, falso positivo, bola parada) so viram arco se voarem.
    """

    def __init__(self):
        self._cam, self._versao = None, None
        self.zerar()

    def zerar(self):
        """sessao nova: os arcos e pontos da anterior nao valem mais"""
        self.arco, self.anterior, self.soltos, self.morta_ate = None, None, [], -math.inf

    def quadro(self, cal, t_s, pontos, zona=None):
        """pontos: [(track_id, point_px bruto)] da bola neste quadro, t_s em segundos epoch.
        devolve a decisao quando um contato no chao se confirma, senao None"""
        if cal.versao != self._versao:
            self._cam, self._versao = Camera(cal), cal.versao
            self.zerar()
        cam = self._cam
        obs = [(t_s, *cam.pixel(px), tid) for tid, px in pontos]
        if self.arco is not None and obs:
            erro, o = min((self.arco.erro_px(t_s, np.array(o[1:3])), o) for o in obs)
            if erro <= FOLGA * SIGMA_PX:
                self.arco = Arco(cam, self.arco.obs + [o], partida=self.arco)
                obs.remove(o)
        self.soltos = [o for o in self.soltos + obs if t_s - o[0] <= JANELA_S]
        if self.arco is not None and t_s - self.arco.fim > 2.5 / 30:
            self.anterior, self.arco = self.arco, None          # sem ponto ha 3 quadros: acabou
        decisao = None
        if self.arco is None:
            novo = self._novo_arco(cam)
            if novo is not None:
                if self.anterior is not None and novo.inicio - self.anterior.fim <= VAO_S:
                    decisao = self._decidir(cal, zona, *contato(self.anterior, novo),
                                            self.anterior, novo)
                    self.anterior = None
                self.arco = novo
        if self.anterior is not None and t_s - self.anterior.fim > VAO_S:
            decisao = decisao or self._chegou_ao_chao(cal, zona, self.anterior)
            self.anterior = None
        return decisao

    def _novo_arco(self, cam):
        """o voo mais longo nos pontos soltos: encadeia quadro a quadro e ajusta"""
        cadeias = []
        for o in sorted(self.soltos):
            for c in cadeias:
                u = c[-1]
                if 0 < o[0] - u[0] <= 2.5 / 30 and math.hypot(o[1] - u[1], o[2] - u[2]) <= SALTO_PX:
                    c.append(o)
                    break
            else:
                cadeias.append([o])
        agora = max((o[0] for o in self.soltos), default=None)
        for c in sorted(cadeias, key=len, reverse=True):
            if len(c) < MIN_ARCO:
                break
            if c[-1][0] != agora:
                continue                                         # nao cresceu: ja foi tentada
            passos = [math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(c, c[1:])]
            if np.median(passos) < 2:                          # parada nao voa
                continue
            if not _parece_parabola(c):
                continue                                         # mistura de objetos: nem ajusta
            arco = Arco(cam, c)
            for _ in range(3):
                if arco.res.max() <= FOLGA * SIGMA_PX or len(arco.obs) <= MIN_ARCO:
                    break
                pior = int(np.argmax(arco.res))                  # ponto previsto, outro objeto
                arco = Arco(cam, arco.obs[:pior] + arco.obs[pior + 1:])
            if arco.res.max() <= FOLGA * SIGMA_PX and _plausivel(arco):
                usados = set(map(id, arco.obs))
                self.soltos = [o for o in self.soltos if id(o) not in usados]
                return arco
        return None

    def _decidir(self, cal, zona, t_c, X, cov, desencontro, a, b):
        """contato entre dois arcos: chao se a altura cabe em z = 0 e o voo depois e um quique"""
        if desencontro > 3 * math.sqrt(np.trace(cov)) + 0.3:
            return None                                          # os arcos nao se encontram
        t_c, X, cov, v_antes, v_depois = contato_conjunto(self._cam, a, b)
        if not (v_antes[2] < 0 < v_depois[2]):
            return None                                          # no chao a bola desce e volta
        if not quique_possivel(cov, v_antes, v_depois, RESTITUICAO, HORIZONTAL)[0]:
            return None                                          # mao de jogador, nao chao
        altura, sigma_z = X[2], math.sqrt(max(cov[2, 2], 0.0))
        t_c, X, cov, *_ = contato_conjunto(self._cam, a, b, no_chao=True)
        return self._lance(cal, zona, t_c, X, cov[:3, :3], sigma_z, altura=altura)

    def _chegou_ao_chao(self, cal, zona, a):
        """arco que desce e some sem outro depois: chao se o fim dele ja esta em z = 0"""
        t_g = chegada_ao_chao(a)
        if t_g is None or not (a.fim - 0.05 <= t_g <= a.fim + VAO_S):
            return None
        return self._lance(cal, zona, t_g, a.em(t_g), a.cov_em(a.fim),
                           math.sqrt(max(a.cov_em(a.fim)[2, 2], 0.0)), altura=a.em(a.fim)[2])

    def _lance(self, cal, zona, t_c, X, cov, sigma_z, altura=None):
        altura = X[2] if altura is None else altura
        # o chao (z = 0) tem que caber na incerteza da altura, dos dois lados, o contato nao pode
        # estar na altura de jogador e tem que ser um lugar do ginasio
        if not (abs(altura) < 2 * sigma_z + 0.1 and altura < Z_JOGADOR):
            return None
        if not all(lo <= v <= hi for v, (lo, hi) in zip(X[:2], GINASIO[:2])):
            return None
        if t_c < self.morta_ate:
            return None                                          # quique seguinte do mesmo rally
        self.morta_ate = t_c + BOLA_MORTA_S
        sigma_xy_cm = 100 * math.sqrt(max(np.linalg.eigvalsh(cov[:2, :2]).max(), 0.0))
        sigma = banda_de_duvida_cm(cal.rms_cm, sigma_xy_cm, zona.erro_cm if zona else 0.0)
        tid = (self.arco or self.anterior).obs[-1][3] if (self.arco or self.anterior) else None
        instante = datetime.fromtimestamp(t_c, timezone.utc).isoformat(timespec="milliseconds")
        return arbitrar((float(X[0]), float(X[1])), sigma, cal.source_id, cal.versao, tid,
                        instante.replace("+00:00", "Z"), zona) | {"altura_contato_m": round(float(altura), 2)}


def _parece_parabola(cadeia, descartes=3):
    """teste barato antes do ajuste 3D: na imagem, um voo de ate ~1 s e quase uma parabola
    no tempo. folga larga (a perspectiva entorta um pouco) e os mesmos 3 pontos que o ajuste
    pode descartar; o que nao passa nisso nao passaria no ajuste 3D"""
    obs = np.array([o[:3] for o in cadeia])
    t = obs[:, 0] - obs[0, 0]
    erro = np.hypot(*(obs[:, k] - np.polyval(np.polyfit(t, obs[:, k], 2), t) for k in (1, 2)))
    return int((erro > 3 * FOLGA * SIGMA_PX).sum()) <= descartes


def _plausivel(arco):
    """o arco precisa ser um voo possivel dentro do ginasio"""
    if np.linalg.norm(arco.theta[3:]) > VEL_MAX:
        return False
    for t in (arco.inicio, arco.fim):
        X = arco.em(t)
        if not all(lo <= v <= hi for v, (lo, hi) in zip(X, GINASIO)):
            return False
    return True
