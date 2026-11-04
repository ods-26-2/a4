"""cena de teste: camera com pose conhecida e voos da bola projetados nela

a camera fica atras da lateral, alta, olhando o meio da quadra, como numa transmissao; a
calibracao sai no formato de ods.i3.calibration, e os pontos sao o pe da bola com ruido de 1 px
"""
import numpy as np

G = 9.81
FPS = 30.0
K = np.array([[1000.0, 0, 640], [0, 1000.0, 360], [0, 0, 1]])
CENTRO = np.array([9.0, -14.0, 7.0])


def _pose():
    alvo = np.array([9.0, 4.5, 0.0])
    z = (alvo - CENTRO) / np.linalg.norm(alvo - CENTRO)          # eixo optico
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    return R, -R @ CENTRO


R, T = _pose()
P = K @ np.column_stack([R, T])


def envelope(source_id="cam0", versao="cal-cam0-1"):
    H_m2px = K @ np.column_stack([R[:, 0], R[:, 1], T])
    return {"source_id": source_id, "artifact_version": versao, "payload": {
        "image_width": 1280, "image_height": 720, "reference_frame": {"space_id": "quadra-1"},
        "intrinsics": {"fx": 1000, "fy": 1000, "cx": 640, "cy": 360},
        "distortion": [0, 0, 0, 0, 0], "reprojection_rms_cm": 2.0,
        "homography_px_to_m": (np.linalg.inv(H_m2px) / np.linalg.inv(H_m2px)[2, 2]).tolist()}}


def pixel(X):
    p = P @ np.append(X, 1.0)
    return p[:2] / p[2]


def voo(X0, V0, t0, t1, t_ini=0.0):
    """posicoes do pe da bola num voo, de t0 a t1 (s depois do inicio do voo, em t_ini)"""
    saida = []
    for n in range(int(np.ceil(t0 * FPS)), int(t1 * FPS) + 1):
        dt = n / FPS - 0.0
        X = np.array(X0) + np.array(V0) * (dt) + np.array([0, 0, -G * dt * dt / 2])
        saida.append((t_ini + n / FPS, X))
    return saida


def quique(chao, v_chegada, e=0.7, antes_s=0.6, depois_s=0.5, t_quique=1.0):
    """bola chegando ao chao em `chao` (x, y) no instante t_quique com velocidade v_chegada,
    voltando com restituicao e no vertical; devolve [(t, X)] dos dois voos"""
    vx, vy, vz = v_chegada
    pts = []
    for n in range(int((t_quique - antes_s) * FPS), int((t_quique + depois_s) * FPS) + 1):
        t = n / FPS
        dt = t - t_quique
        if dt <= 0:   # antes: o voo que termina no chao em t_quique
            X = np.array([chao[0] + vx * dt, chao[1] + vy * dt, vz * dt - G * dt * dt / 2])
        else:         # depois: sobe com -e vz
            X = np.array([chao[0] + vx * dt, chao[1] + vy * dt, -e * vz * dt - G * dt * dt / 2])
        pts.append((t, X))
    return pts


def toque(ponto, v_chegada, v_saida, antes_s=0.6, depois_s=0.5, t_toque=1.0):
    """bola tocada no ar em `ponto` (x, y, z): chega com v_chegada e sai com v_saida"""
    pts = []
    for n in range(int((t_toque - antes_s) * FPS), int((t_toque + depois_s) * FPS) + 1):
        t = n / FPS
        dt = t - t_toque
        v = np.array(v_chegada if dt <= 0 else v_saida)
        pts.append((t, np.array(ponto) + v * dt + np.array([0, 0, -G * dt * dt / 2])))
    return pts


def pixels(pts, ruido=1.0, semente=0):
    rng = np.random.default_rng(semente)
    return [(t, tuple(pixel(X) + rng.normal(0, ruido, 2))) for t, X in pts]
