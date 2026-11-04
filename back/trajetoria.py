"""trajetoria 3D da bola numa camera so, com a calibracao do i3

entre dois toques a bola e um projetil: X(t) = X0 + V0 t - g t^2 / 2 em z. com a camera
calibrada (intrinsecos, distorcao e homografia do chao dao a pose), o arco que melhor explica
os pixels sai de um ajuste de 6 incognitas; a gravidade conhecida fixa a profundidade. onde dois
arcos se encontram houve um toque, e a altura desse ponto diz se foi o chao ou um jogador.

6c: homography_px_to_m vale do pixel bruto no chao; fora do chao, quem usa a calibracao corrige
as coordenadas com intrinsecos e distorcao. o ponto seguido e o pe da caixa (point_px de i2/s1),
a base da bola: ela toca o chao em z = 0.
"""
import math

import numpy as np

G = 9.81
SIGMA_PX = 1.5            # ruido do pe da caixa da bola, em px: caixa de 10 a 20 px, borrada


def sem_distorcao(K, dist, px):
    """pixel bruto -> pixel do modelo pinhole (brown-conrady k1 k2 p1 p2 k3, por iteracao)"""
    k1, k2, p1, p2, k3 = (list(dist) + [0.0] * 5)[:5]
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    xd, yd = (px[0] - cx) / fx, (px[1] - cy) / fy
    x, y = xd, yd
    for _ in range(20):
        r2 = x * x + y * y
        radial = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 ** 3
        dx = 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
        dy = p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
        x, y = (xd - dx) / radial, (yd - dy) / radial
    return np.array([fx * x + cx, fy * y + cy])


class Camera:
    """projecao 3D -> pixel sem distorcao; z do mundo para cima, metros do referencial do i3"""

    def __init__(self, cal):
        self.K, self.dist = cal.K, cal.dist
        # a homografia vale no pixel bruto: refaz chao -> pixel sem distorcao por pontos do chao
        chao = np.array([(x, y) for x in np.linspace(-3, 21, 7) for y in np.linspace(-3, 12, 6)])
        H_inv = np.linalg.inv(cal.H)
        brutos = [H_inv @ np.array([x, y, 1.0]) for x, y in chao]
        pinhole = np.array([sem_distorcao(self.K, self.dist, b[:2] / b[2]) for b in brutos])
        Hm = _homografia(chao, pinhole)                       # metro -> pixel sem distorcao
        B = np.linalg.inv(self.K) @ Hm
        lam = 1 / np.linalg.norm(B[:, 0])
        r1, r2, t = lam * B[:, 0], lam * B[:, 1], lam * B[:, 2]
        if t[2] < 0:                                          # o chao fica na frente da camera
            r1, r2, t = -r1, -r2, -t
        U, _, Vt = np.linalg.svd(np.column_stack([r1, r2, np.cross(r1, r2)]))
        R = U @ Vt
        if (-R.T @ t)[2] < 0:                                 # camera acima do chao: z para cima
            R[:, 2] *= -1
        self.P = self.K @ np.column_stack([R, t])
        self.centro = -R.T @ t

    def pixel(self, px):
        return sem_distorcao(self.K, self.dist, px)

    def projetar(self, X):
        p = self.P @ np.append(X, 1.0)
        return p[:2] / p[2]

    def raio_na_altura(self, px, z):
        """ponto do raio do pixel (ja sem distorcao) na altura z"""
        M = self.P[:, :3]
        d = np.linalg.solve(M, np.array([px[0], px[1], 1.0]))
        return self.centro + d * (z - self.centro[2]) / d[2]


def _homografia(origem, destino):
    """DLT: H com destino ~ H origem"""
    linhas = []
    for (x, y), (u, v) in zip(origem, destino):
        linhas.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        linhas.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, Vt = np.linalg.svd(np.array(linhas))
    return Vt[-1].reshape(3, 3)


class Arco:
    """um voo da bola entre dois toques, ajustado aos pixels sem distorcao (t, u, v, ...)"""

    def __init__(self, cam, obs, partida=None):
        """partida: o arco anterior, quando este e ele com um ponto a mais (comeca de la)"""
        self.cam, self.obs = cam, list(obs)
        self.t0 = self.obs[0][0]
        if partida is not None and partida.t0 == self.t0:
            theta, voltas = partida.theta, 4
        else:
            a = cam.raio_na_altura(self.obs[0][1:3], 1.5)      # chute: bola a 1,5 m de altura
            b = cam.raio_na_altura(self.obs[-1][1:3], 1.5)
            T = max(self.obs[-1][0] - self.t0, 1e-3)
            theta, voltas = np.concatenate([a, (b - a) / T + np.array([0, 0, G * T / 2])]), 20
        self.theta, self.cov = _gauss_newton(cam, self.obs, self.t0, theta, voltas)
        self.res = np.hypot(*_residuos(cam, self.obs, self.t0, self.theta).reshape(-1, 2).T)

    @property
    def inicio(self):
        return self.obs[0][0]

    @property
    def fim(self):
        return self.obs[-1][0]

    def em(self, t):
        dt = t - self.t0
        return self.theta[:3] + self.theta[3:] * dt + np.array([0, 0, -G * dt * dt / 2])

    def vz(self, t):
        return self.theta[5] - G * (t - self.t0)

    def cov_em(self, t):
        A = np.hstack([np.eye(3), np.eye(3) * (t - self.t0)])
        return A @ self.cov @ A.T

    def erro_px(self, t, px):
        return float(np.hypot(*(self.cam.projetar(self.em(t)) - px)))


def _projecao(P, X):
    """pixels de X (n x 3) e a derivada de cada pixel em X (n x 2 x 3)"""
    p = X @ P[:, :3].T + P[:, 3]
    uv = p[:, :2] / p[:, 2:3]
    d = (P[None, :2, :3] - uv[:, :, None] * P[None, 2:3, :3]) / p[:, 2, None, None]
    return uv, d


def _residuos(cam, obs, t0, theta, com_jacobiano=False):
    """erro em pixels de cada ponto e, se pedido, o jacobiano analitico (2n x 6)"""
    obs = np.asarray([o[:3] for o in obs], float)
    dts = obs[:, 0] - t0
    X = theta[:3] + np.outer(dts, theta[3:]) + np.outer(-G * dts ** 2 / 2, [0, 0, 1])
    uv, d = _projecao(cam.P, X)
    r = (uv - obs[:, 1:3]).ravel()
    if not com_jacobiano:
        return r
    return r, np.concatenate([d, d * dts[:, None, None]], axis=2).reshape(-1, 6)


def _gauss_newton(cam, obs, t0, theta, voltas=20):
    """minimiza o erro em pixels (levenberg-marquardt); devolve theta e a covariancia"""
    mu = 1e-3
    r, J = _residuos(cam, obs, t0, theta, True)
    for _ in range(voltas):
        JtJ = J.T @ J
        passo = np.linalg.solve(JtJ + mu * np.diag(np.diag(JtJ)), -J.T @ r)
        r_novo, J_novo = _residuos(cam, obs, t0, theta + passo, True)
        if r_novo @ r_novo < r @ r:
            theta, r, J, mu = theta + passo, r_novo, J_novo, mu / 3
            if np.abs(passo).max() < 1e-6:
                break
        else:
            mu *= 5
    return theta, SIGMA_PX ** 2 * np.linalg.pinv(J.T @ J)


def contato(a, b):
    """onde o arco a termina e o b comeca: instante, ponto 3D, covariancia e desencontro"""
    ts = np.linspace(a.fim - 0.05, b.inicio + 0.05, 41)
    dist = [np.linalg.norm(a.em(t) - b.em(t)) for t in ts]
    t = float(ts[int(np.argmin(dist))])
    return t, (a.em(t) + b.em(t)) / 2, (a.cov_em(t) + b.cov_em(t)) / 4, float(min(dist))


def chegada_ao_chao(a):
    """instante em que o arco a, descendo, chega a z = 0 (depois do inicio), ou None"""
    z0, vz0 = a.theta[2], a.theta[5]
    disc = vz0 * vz0 + 2 * G * z0
    if disc < 0:
        return None
    dt = (vz0 + math.sqrt(disc)) / G
    return a.t0 + dt if dt > 0 else None


def contato_conjunto(cam, a, b, no_chao=False):
    """os dois voos ajustados juntos, passando pelo mesmo ponto de contato no mesmo instante

    incognitas: ponto (x, y, z), instante, velocidade de chegada e de saida (10). o ponto comum
    amarra a profundidade dos dois arcos, e a altura dele sai com a incerteza do ajuste.
    no_chao prende z = 0: depois de decidido que foi o chao, o ponto do quique sai preciso
    devolve (t_c, X, cov 10x10 na ordem ponto, instante, v antes, v depois, v antes, v depois)
    """
    t_c, X, _, _ = contato(a, b)
    theta = np.concatenate([X, [t_c], a.theta[3:] + np.array([0, 0, -G * (t_c - a.t0)]),
                            b.theta[3:] + np.array([0, 0, -G * (t_c - b.t0)])])
    lados = [(o, 0) for o in a.obs] + [(o, 1) for o in b.obs]
    livres = [i for i in range(10) if not (no_chao and i == 2)]
    if no_chao:
        theta[2] = 0.0

    obs = np.array([o[:3] for o, _ in lados], float)
    depois = np.array([lado for _, lado in lados], bool)

    def residuos(th, com_jacobiano=False):
        dt = obs[:, 0] - th[3]
        v = np.where(depois[:, None], th[7:10], th[4:7])
        X = th[:3] + v * dt[:, None] + np.outer(-G * dt * dt / 2, [0, 0, 1])
        uv, d = _projecao(cam.P, X)
        r = (uv - obs[:, 1:3]).ravel()
        if not com_jacobiano:
            return r
        # dX/d(ponto) = I; dX/d(instante) = -v + g dt z; dX/d(v do lado) = dt I
        dX_dt = -v + np.outer(G * dt, [0, 0, 1])
        J = np.zeros((len(obs), 2, 10))
        J[:, :, 0:3] = d
        J[:, :, 3] = np.einsum("nij,nj->ni", d, dX_dt)
        lado_v = d * dt[:, None, None]
        J[~depois, :, 4:7] = lado_v[~depois]
        J[depois, :, 7:10] = lado_v[depois]
        return r, J.reshape(-1, 10)[:, livres]

    def jacobiano(th, r):
        return residuos(th, True)[1]

    mu, r = 1e-3, residuos(theta)
    for _ in range(30):
        J = jacobiano(theta, r)
        JtJ = J.T @ J
        passo = np.zeros(10)
        passo[livres] = np.linalg.solve(JtJ + mu * np.diag(np.diag(JtJ)), -J.T @ r)
        r_novo = residuos(theta + passo)
        if r_novo @ r_novo < r @ r:
            theta, r, mu = theta + passo, r_novo, mu / 3
            if np.abs(passo).max() < 1e-7:
                break
        else:
            mu *= 5
    cov = np.zeros((10, 10))
    J = jacobiano(theta, r)
    cov[np.ix_(livres, livres)] = SIGMA_PX ** 2 * np.linalg.pinv(J.T @ J)
    return float(theta[3]), theta[:3], cov, theta[4:7], theta[7:10]


CHI2_3_95 = 7.81


def quique_possivel(cov, v_antes, v_depois, restituicao, horizontal):
    """existe um quique fisico (restituicao e e perda horizontal k nas faixas) que explique a
    saida dentro da incerteza? teste de chi-quadrado sobre v_depois - (k vx, k vy, -e vz)"""
    S_aa, S_dd, S_ad = cov[4:7, 4:7], cov[7:10, 7:10], cov[4:7, 7:10]
    melhor = math.inf
    for k in np.linspace(*horizontal, 15):
        for e in np.linspace(*restituicao, 15):
            M = np.diag([k, k, -e])
            r = v_depois - M @ v_antes
            C = S_dd + M @ S_aa @ M.T - M @ S_ad - S_ad.T @ M.T
            melhor = min(melhor, float(r @ np.linalg.solve(C, r)))
    return melhor <= CHI2_3_95, melhor
