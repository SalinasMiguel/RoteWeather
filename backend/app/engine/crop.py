"""PLAN §4.3 — Coeficiente de cultivo Kc y ventana sensible."""

import numpy as np

from app.config import SENS_AFTER, SENS_BEFORE
from app.data.crops import Crop


def get_kc_curve(crop: Crop) -> np.ndarray:
    """PLAN §4.3 — Curva Kc lineal de 4 etapas para t = 0..N-1."""
    n = crop.ciclo
    if n <= 0:
        return np.zeros(0, dtype=float)

    l_ini = crop.L_ini
    l_dev = crop.L_dev
    l_mid = crop.L_mid
    l_late = crop.L_late

    kc_ini = crop.kc_ini
    kc_mid = crop.kc_mid
    kc_end = crop.kc_end

    t = np.arange(n)
    kc = np.zeros(n, dtype=float)

    # 1. Etapa inicial: t < L_ini
    m1 = t < l_ini
    kc[m1] = kc_ini

    # 2. Etapa de desarrollo: L_ini <= t < L_ini + L_dev
    t_dev_start = l_ini
    t_dev_end = l_ini + l_dev
    m2 = (t >= t_dev_start) & (t < t_dev_end)
    if l_dev > 0:
        kc[m2] = kc_ini + (kc_mid - kc_ini) * (t[m2] - t_dev_start) / l_dev
    else:
        kc[m2] = kc_mid

    # 3. Etapa de mediados de temporada: L_ini + L_dev <= t < L_ini + L_dev + L_mid
    t_mid_end = t_dev_end + l_mid
    m3 = (t >= t_dev_end) & (t < t_mid_end)
    kc[m3] = kc_mid

    # 4. Etapa final: resto
    m4 = t >= t_mid_end
    if l_late > 0:
        kc[m4] = kc_mid + (kc_end - kc_mid) * (t[m4] - (n - l_late)) / l_late
    else:
        kc[m4] = kc_end

    return kc


def get_sensitive_window(crop: Crop) -> tuple[int, int]:
    """PLAN §4.3 — Ventana sensible [inicio, fin) en días desde siembra."""
    t_mid = crop.L_ini + crop.L_dev
    start_sens = max(0, t_mid - SENS_BEFORE)
    end_sens = min(crop.ciclo, t_mid + SENS_AFTER)
    return (start_sens, end_sens)
