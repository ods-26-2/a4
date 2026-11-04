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


# arrasto do ar: a 20 m/s o arrasto de uma bola de volei (270 g, 21 cm) passa do peso, e um saque
# ou um ataque nao e parabola. modelo de arrasto linear, dV/dt = -g z - c V, com c = k |v| por voo
# (k ~ 0,03/m): tem solucao fechada. c fica em [0, C_MAX] e tem referencia fraca em C0 (12 m/s),
# para o voo curto nao inventar arrasto
C0, SIGMA_C, C_MAX = 0.4, 0.4, 3.0


def _expoentes(c, tau):
    """E1 = (1 - e^-c tau)/c, E2 = (tau - E1)/c e as derivadas em c; serie quando c tau ~ 0"""
    ct = c * tau
    if np.all(np.abs(ct) < 1e-3):
        E1 = tau - c * tau ** 2 / 2 + c ** 2 * tau ** 3 / 6
        E2 = tau ** 2 / 2 - c * tau ** 3 / 6 + c ** 2 * tau ** 4 / 24
        dE1 = -tau ** 2 / 2 + c * tau ** 3 / 3
        dE2 = -tau ** 3 / 6 + c * tau ** 4 / 12
        return E1, E2, dE1, dE2
    ex = np.exp(-ct)
    E1 = (1 - ex) / c
    E2 = (tau - E1) / c
    dE1 = (tau * ex - E1) / c
    dE2 = -(dE1 + E2) / c
    return E1, E2, dE1, dE2


def voo(X0, V0, c, tau):
    """posicoes (n x 3) e velocidades no voo que passa por X0 com V0 em tau = 0 (vale para tras)"""
    tau = np.atleast_1d(np.asarray(tau, float))
    E1, E2, _, _ = _expoentes(c, tau)
    z = np.array([0, 0, 1.0])
    X = X0 + np.outer(E1, V0) - np.outer(G * E2, z)
    V = np.outer(np.exp(-c * tau), V0) - np.outer(G * E1, z)
    return X, V


def _voo_jacobiano(X0, V0, c, tau):
    """posicoes e dX/d(X0, V0, c): n x 3 x 7"""
    E1, E2, dE1, dE2 = _expoentes(c, tau)
    z = np.array([0, 0, 1.0])
    X = X0 + np.outer(E1, V0) - np.outer(G * E2, z)
    J = np.zeros((len(tau), 3, 7))
    J[:, :, 0:3] = np.eye(3)
    J[:, :, 3:6] = E1[:, None, None] * np.eye(3)
    J[:, :, 6] = np.outer(dE1, V0) - np.outer(G * dE2, z)
    return X, J


class Arco:
    """um voo da bola entre dois toques, ajustado aos pixels sem distorcao (t, u, v, ...)

    theta = (X0, V0, c): posicao e velocidade em t0 e o arrasto do voo
    """

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
            theta = np.concatenate([a, (b - a) / T + np.array([0, 0, G * T / 2]), [C0]])
            voltas = 20
        self.theta, self.cov = _gauss_newton(cam, self.obs, self.t0, theta, voltas)
        self.res = np.hypot(*_residuos(cam, self.obs, self.t0, self.theta)[:-1].reshape(-1, 2).T)

    @property
    def inicio(self):
        return self.obs[0][0]

    @property
    def fim(self):
        return self.obs[-1][0]

    def em(self, t):
        return voo(self.theta[:3], self.theta[3:6], self.theta[6], t - self.t0)[0][0]

    def vz(self, t):
        return voo(self.theta[:3], self.theta[3:6], self.theta[6], t - self.t0)[1][0][2]

    def velocidade(self, t):
        return voo(self.theta[:3], self.theta[3:6], self.theta[6], t - self.t0)[1][0]

    def cov_em(self, t):
        _, J = _voo_jacobiano(self.theta[:3], self.theta[3:6], self.theta[6], np.array([t - self.t0]))
        return J[0] @ self.cov @ J[0].T

    def erro_px(self, t, px):
        return float(np.hypot(*(self.cam.projetar(self.em(t)) - px)))

    def distancia(self, t, px):
        """distancia de mahalanobis do ponto ao pixel previsto: a incerteza do arco (pela
        covariancia do ajuste) mais o ruido do ponto; arco jovem preve com mais folga"""
        X, J = _voo_jacobiano(self.theta[:3], self.theta[3:6], self.theta[6], np.array([t - self.t0]))
        uv, d = _projecao(self.cam.P, X)
        Jp = d[0] @ J[0]
        S = Jp @ self.cov @ Jp.T + SIGMA_PX ** 2 * np.eye(2)
        r = uv[0] - px
        return float(r @ np.linalg.solve(S, r))


def _projecao(P, X):
    """pixels de X (n x 3) e a derivada de cada pixel em X (n x 2 x 3)"""
    p = X @ P[:, :3].T + P[:, 3]
    uv = p[:, :2] / p[:, 2:3]
    d = (P[None, :2, :3] - uv[:, :, None] * P[None, 2:3, :3]) / p[:, 2, None, None]
    return uv, d


def _residuos(cam, obs, t0, theta, com_jacobiano=False):
    """erro em pixels de cada ponto (mais a referencia do arrasto) e, se pedido, o jacobiano"""
    obs = np.asarray([o[:3] for o in obs], float)
    X, Jv = _voo_jacobiano(theta[:3], theta[3:6], theta[6], obs[:, 0] - t0)
    uv, d = _projecao(cam.P, X)
    # referencia do arrasto como uma observacao a mais, na escala do ruido do ponto
    r = np.append((uv - obs[:, 1:3]).ravel(), (theta[6] - C0) / SIGMA_C * SIGMA_PX)
    if not com_jacobiano:
        return r
    J = np.einsum("nij,njk->nik", d, Jv).reshape(-1, 7)
    linha_c = np.zeros((1, 7))
    linha_c[0, 6] = SIGMA_PX / SIGMA_C
    return r, np.vstack([J, linha_c])


def _gauss_newton(cam, obs, t0, theta, voltas=20):
    """minimiza o erro em pixels (levenberg-marquardt), arrasto em [0, C_MAX]; theta e covariancia"""
    mu = 1e-3
    r, J = _residuos(cam, obs, t0, theta, True)
    for _ in range(voltas):
        JtJ = J.T @ J
        passo = np.linalg.lstsq(JtJ + mu * np.diag(np.diag(JtJ)) + 1e-12 * np.eye(7), -J.T @ r, rcond=None)[0]
        novo = theta + passo
        novo[6] = np.clip(novo[6], 0.0, C_MAX)
        r_novo, J_novo = _residuos(cam, obs, t0, novo, True)
        if r_novo @ r_novo < r @ r:
            theta, r, J, mu = novo, r_novo, J_novo, mu / 3
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
    taus = np.linspace(0.0, 3.0, 301)
    z = voo(a.theta[:3], a.theta[3:6], a.theta[6], taus)[0][:, 2]
    cruza = np.where((z[:-1] > 0) & (z[1:] <= 0))[0]
    if len(cruza) == 0:
        return None
    lo, hi = taus[cruza[0]], taus[cruza[0] + 1]
    for _ in range(30):                                   # bissecao no intervalo da troca de sinal
        meio = (lo + hi) / 2
        if voo(a.theta[:3], a.theta[3:6], a.theta[6], meio)[0][0, 2] > 0:
            lo = meio
        else:
            hi = meio
    return a.t0 + (lo + hi) / 2


def contato_conjunto(cam, a, b, no_chao=False):
    """os dois voos ajustados juntos, passando pelo mesmo ponto de contato no mesmo instante

    incognitas: ponto (x, y, z), instante, velocidade de chegada e de saida e o arrasto de cada
    voo (12). o ponto comum amarra a profundidade dos dois arcos, e a altura dele sai com a
    incerteza do ajuste. no_chao prende z = 0: depois de decidido que foi o chao, o ponto do
    quique sai preciso. devolve (t_c, X, cov 12x12 na ordem ponto, instante, v antes, v depois,
    arrasto antes e depois, v antes, v depois)
    """
    t_c, X, _, _ = contato(a, b)
    theta = np.concatenate([X, [t_c], a.velocidade(t_c), b.velocidade(t_c), [a.theta[6], b.theta[6]]])
    if no_chao:
        theta[2] = 0.0
    livres = [i for i in range(12) if not (no_chao and i == 2)]
    obs = np.array([o[:3] for o in a.obs] + [o[:3] for o in b.obs], float)
    depois = np.array([False] * len(a.obs) + [True] * len(b.obs))
    z = np.array([0, 0, 1.0])

    def residuos(th, com_jacobiano=False):
        X = np.zeros((len(obs), 3))
        J = np.zeros((len(obs), 3, 12))
        for lado, iv, ic in ((~depois, slice(4, 7), 10), (depois, slice(7, 10), 11)):
            tau = obs[lado, 0] - th[3]
            E1, E2, dE1, dE2 = _expoentes(th[ic], tau)
            v = th[iv]
            X[lado] = th[:3] + np.outer(E1, v) - np.outer(G * E2, z)
            J[lado, :, 0:3] = np.eye(3)
            J[lado, :, 3] = -(np.outer(np.exp(-th[ic] * tau), v) - np.outer(G * E1, z))
            J[lado, :, iv] = E1[:, None, None] * np.eye(3)
            J[lado, :, ic] = np.outer(dE1, v) - np.outer(G * dE2, z)
        uv, d = _projecao(cam.P, X)
        ref = (th[10:12] - C0) / SIGMA_C * SIGMA_PX       # referencia fraca do arrasto
        r = np.concatenate([(uv - obs[:, 1:3]).ravel(), ref])
        if not com_jacobiano:
            return r
        Jp = np.einsum("nij,njk->nik", d, J).reshape(-1, 12)
        linhas = np.zeros((2, 12))
        linhas[0, 10] = linhas[1, 11] = SIGMA_PX / SIGMA_C
        return r, np.vstack([Jp, linhas])[:, livres]

    mu = 1e-3
    r, J = residuos(theta, True)
    for _ in range(30):
        JtJ = J.T @ J
        passo = np.zeros(12)
        passo[livres] = np.linalg.lstsq(JtJ + mu * np.diag(np.diag(JtJ)) + 1e-12 * np.eye(len(livres)),
                                        -J.T @ r, rcond=None)[0]
        novo = theta + passo
        novo[10:12] = np.clip(novo[10:12], 0.0, C_MAX)
        r_novo, J_novo = residuos(novo, True)
        if r_novo @ r_novo < r @ r:
            theta, r, J, mu = novo, r_novo, J_novo, mu / 3
            if np.abs(passo).max() < 1e-7:
                break
        else:
            mu *= 5
    cov = np.zeros((12, 12))
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
            melhor = min(melhor, float(r @ np.linalg.lstsq(C, r, rcond=None)[0]))
    return melhor <= CHI2_3_95, melhor
