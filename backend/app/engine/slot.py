"""PLAN §4.4, §4.5 — Balance hídrico, factores térmicos y simulación de slot."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

import numpy as np
import pandas as pd

from app.config import (
    AWC_MM_PER_M,
    CN,
    DR0_FRAC,
    F_FROST_SENS,
    F_FROST_VEG,
    FROST_VEG_OFFSET,
    KC_FALLOW,
    KC_PRE_CROP,
    P_MAX,
    P_MIN,
    PRE_CROP_DAYS,
    SMALL_RAIN_FRAC,
    SPINUP_DAYS,
)
from app.data.crops import Crop
from app.engine.calendar import get_hemisphere, get_valid_seasons, parse_sow_date
from app.engine.crop import get_kc_curve, get_sensitive_window
from app.engine.et0 import add_et0


def calc_runoff(prec: float | np.ndarray, cn: float) -> float | np.ndarray:
    """PLAN §4.4 — Escorrentía superficial SCS-CN en mm/día."""
    is_scalar = np.ndim(prec) == 0
    prec_arr = np.asarray(prec, dtype=float)

    s = 25400.0 / cn - 254.0
    ia = 0.2 * s

    ro = np.where(prec_arr > ia, ((prec_arr - ia) ** 2) / (prec_arr + 0.8 * s), 0.0)

    if is_scalar:
        return float(ro.item())
    return ro


def wb_step(
    dr: float | np.ndarray,
    prec: float | np.ndarray,
    et0: float | np.ndarray,
    kc: float | np.ndarray,
    p_tab: float | np.ndarray,
    taw: float | np.ndarray,
    cn: float | np.ndarray,
) -> tuple[float | np.ndarray, ...]:
    """PLAN §4.4 — Paso diario del balance hídrico (FAO-56 y SCS-CN)."""
    is_scalar = (
        np.ndim(dr) == 0
        and np.ndim(prec) == 0
        and np.ndim(et0) == 0
        and np.ndim(kc) == 0
    )

    dr_arr = np.asarray(dr, dtype=float)
    prec_arr = np.asarray(prec, dtype=float)
    et0_arr = np.asarray(et0, dtype=float)
    kc_arr = np.asarray(kc, dtype=float)
    p_tab_arr = np.asarray(p_tab, dtype=float)
    taw_arr = np.asarray(taw, dtype=float)
    cn_arr = np.asarray(cn, dtype=float)

    s = 25400.0 / cn_arr - 254.0
    ia = 0.2 * s
    ro = np.where(prec_arr > ia, ((prec_arr - ia) ** 2) / (prec_arr + 0.8 * s), 0.0)

    # Lluvia efectiva con corte de lluvia pequeña (FAO-56 cap. 8)
    pe = np.where(prec_arr < SMALL_RAIN_FRAC * et0_arr, 0.0, np.maximum(prec_arr - ro, 0.0))

    # Balance de agua: lluvia entra ANTES de evaluar estrés
    d = dr_arr - pe
    dp = np.maximum(0.0, -d)
    d = np.maximum(0.0, d)

    etc = kc_arr * et0_arr
    p = np.clip(p_tab_arr + 0.04 * (5.0 - etc), P_MIN, P_MAX)
    raw = p * taw_arr

    denom_ks = np.maximum(taw_arr - raw, 1e-6)
    ks = np.where(d <= raw, 1.0, np.clip((taw_arr - d) / denom_ks, 0.0, 1.0))
    eta = ks * etc
    dr_new = np.minimum(taw_arr, d + eta)

    if is_scalar:
        return (
            float(dr_new.item()),
            float(eta.item()),
            float(etc.item()),
            float(pe.item()),
            float(ro.item()),
            float(dp.item()),
            float(ks.item()),
        )
    return (dr_new, eta, etc, pe, ro, dp, ks)


def calc_trapezoid(
    x: float | np.ndarray, a: float, b: float, c: float, d: float
) -> float | np.ndarray:
    """PLAN §4.5 — Función de respuesta térmica trapezoidal."""
    is_scalar = np.ndim(x) == 0
    arr = np.asarray(x, dtype=float)

    res = np.zeros_like(arr, dtype=float)

    # a < x < b
    m_up = (arr > a) & (arr < b)
    if b > a:
        res[m_up] = (arr[m_up] - a) / (b - a)

    # b <= x <= c
    m_opt = (arr >= b) & (arr <= c)
    res[m_opt] = 1.0

    # c < x < d
    m_down = (arr > c) & (arr < d)
    if d > c:
        res[m_down] = (d - arr[m_down]) / (d - c)

    if is_scalar:
        return float(res.item())
    return res


def calc_temp_factor(
    tmean_cycle: np.ndarray, t_ecocrop: list[float]
) -> float | np.ndarray:
    """PLAN §4.5 — Factor de aptitud térmica general f_temp."""
    a, b, c, d = t_ecocrop
    trap = calc_trapezoid(tmean_cycle, a, b, c, d)
    if np.ndim(trap) == 1:
        return float(np.mean(trap))
    return np.mean(trap, axis=0)


def calc_heat_factor(
    tmax_sens: np.ndarray, tcrit: float, tlim: float
) -> float | np.ndarray:
    """PLAN §4.5 — Factor de penalización por golpe de calor en floración f_calor."""
    if len(tmax_sens) == 0:
        return 1.0 if np.ndim(tmax_sens) <= 1 else np.ones(tmax_sens.shape[1], dtype=float)

    denom = max(tlim - tcrit, 1e-6)
    h_t = np.clip((tmax_sens - tcrit) / denom, 0.0, 1.0)
    if np.ndim(h_t) == 1:
        return float(1.0 - np.mean(h_t))
    return 1.0 - np.mean(h_t, axis=0)


def calc_frost_factor(
    tmin_sens: np.ndarray, tmin_cycle: np.ndarray, t_helada: float
) -> float | np.ndarray:
    """PLAN §4.5 — Factor de penalización por heladas f_helada."""
    if np.ndim(tmin_cycle) == 1:
        helada_s = bool(np.any(tmin_sens < t_helada)) if len(tmin_sens) > 0 else False
        helada_v = bool(np.any(tmin_cycle < (t_helada - FROST_VEG_OFFSET)))
        if helada_s:
            return float(F_FROST_SENS)
        if helada_v:
            return float(F_FROST_VEG)
        return 1.0

    m = tmin_cycle.shape[1]
    if len(tmin_sens) > 0:
        helada_s = np.any(tmin_sens < t_helada, axis=0)
    else:
        helada_s = np.zeros(m, dtype=bool)

    helada_v = np.any(tmin_cycle < (t_helada - FROST_VEG_OFFSET), axis=0)
    return np.where(helada_s, F_FROST_SENS, np.where(helada_v, F_FROST_VEG, 1.0))


@dataclass
class SlotSimulationResult:
    """PLAN §4.5 — Resultados de simulación de un slot sobre M campañas."""

    y_rel: np.ndarray  # shape (M,)
    f_agua: np.ndarray  # shape (M,)
    f_calor: np.ndarray  # shape (M,)
    f_helada: np.ndarray  # shape (M,)
    f_temp: np.ndarray  # shape (M,)
    sum_eta: np.ndarray  # shape (M,)
    sum_etc: np.ndarray  # shape (M,)
    limiting: list[str]  # length M: 'agua', 'calor', 'helada', 'temperatura', 'ninguno'


def simulate_slot(
    crop: Crop,
    sow_date_str: str,
    prev_mode: Literal["crop", "fallow"] | str,
    soil_texture: str,
    weather_df: pd.DataFrame,
    lat: float,
    seasons: list[int] | None = None,
) -> SlotSimulationResult:
    """PLAN §4.4, §4.5 — Simulación completa de un slot vectorizada sobre campañas."""
    if soil_texture not in AWC_MM_PER_M:
        raise ValueError(
            f"Textura de suelo desconocida: '{soil_texture}'. Válidas: {list(AWC_MM_PER_M.keys())}"
        )
    if prev_mode not in ("crop", "fallow"):
        raise ValueError(f"Modo previo desconocido: '{prev_mode}'. Válidos: ('crop', 'fallow')")

    hemisphere = get_hemisphere(lat)
    if seasons is None:
        seasons = get_valid_seasons(hemisphere)

    m_campaigns = len(seasons)
    if m_campaigns == 0:
        return SlotSimulationResult(
            y_rel=np.zeros(0, dtype=float),
            f_agua=np.zeros(0, dtype=float),
            f_calor=np.zeros(0, dtype=float),
            f_helada=np.zeros(0, dtype=float),
            f_temp=np.zeros(0, dtype=float),
            sum_eta=np.zeros(0, dtype=float),
            sum_etc=np.zeros(0, dtype=float),
            limiting=[],
        )

    # Parámetros del suelo y cultivo
    taw = float(AWC_MM_PER_M[soil_texture] * crop.zr_max_m)
    cn_val = float(CN[soil_texture])

    # Asegurar índice DatetimeIndex y presencia de et0
    w_df = weather_df
    if not isinstance(w_df.index, pd.DatetimeIndex):
        w_df = w_df.copy()
        w_df.index = pd.to_datetime(w_df.index)

    if "et0" not in w_df.columns:
        w_df = add_et0(w_df, lat, 0.0)

    n_cycle = crop.ciclo
    t_total = SPINUP_DAYS + n_cycle

    prec_mat = np.zeros((t_total, m_campaigns), dtype=float)
    et0_mat = np.zeros((t_total, m_campaigns), dtype=float)
    tmax_mat = np.zeros((n_cycle, m_campaigns), dtype=float)
    tmin_mat = np.zeros((n_cycle, m_campaigns), dtype=float)
    campaign_has_nan = np.zeros(m_campaigns, dtype=bool)

    # Extracción de datos climáticos para cada campaña
    for m, y in enumerate(seasons):
        sow_date = parse_sow_date(sow_date_str, y, hemisphere)
        start_date = sow_date - timedelta(days=SPINUP_DAYS)
        end_date = sow_date + timedelta(days=n_cycle - 1)
        camp_dates = pd.date_range(start_date, end_date, freq="D")

        camp_slice = w_df.reindex(camp_dates)

        # PLAN §4.4: Si prec, tmax o tmin tienen NaN en la ventana, resultado es NaN
        if (
            camp_slice["prec"].isna().any()
            or camp_slice["tmax"].isna().any()
            or camp_slice["tmin"].isna().any()
            or camp_slice["et0"].isna().any()
        ):
            campaign_has_nan[m] = True
            prec_mat[:, m] = camp_slice["prec"].fillna(0.0).to_numpy()
            et0_mat[:, m] = camp_slice["et0"].fillna(0.0).to_numpy()
            tmax_mat[:, m] = camp_slice["tmax"].iloc[SPINUP_DAYS:].fillna(0.0).to_numpy()
            tmin_mat[:, m] = camp_slice["tmin"].iloc[SPINUP_DAYS:].fillna(0.0).to_numpy()
        else:
            prec_mat[:, m] = camp_slice["prec"].to_numpy(dtype=float)
            et0_mat[:, m] = camp_slice["et0"].to_numpy(dtype=float)
            tmax_mat[:, m] = camp_slice["tmax"].iloc[SPINUP_DAYS:].to_numpy(dtype=float)
            tmin_mat[:, m] = camp_slice["tmin"].iloc[SPINUP_DAYS:].to_numpy(dtype=float)

    # 1. Spin-up de 180 días (t = -SPINUP_DAYS .. -1)
    dr = np.full(m_campaigns, DR0_FRAC * taw, dtype=float)
    sum_eta = np.zeros(m_campaigns, dtype=float)
    sum_etc = np.zeros(m_campaigns, dtype=float)

    for idx in range(SPINUP_DAYS):
        t = idx - SPINUP_DAYS
        kc_val = KC_PRE_CROP if (prev_mode == "crop" and t >= -PRE_CROP_DAYS) else KC_FALLOW
        p_tab_val = 0.5
        prec_t = prec_mat[idx, :]
        et0_t = et0_mat[idx, :]

        dr, _, _, _, _, _, _ = wb_step(
            dr=dr,
            prec=prec_t,
            et0=et0_t,
            kc=kc_val,
            p_tab=p_tab_val,
            taw=taw,
            cn=cn_val,
        )

    # 2. Ciclo del cultivo (t = 0 .. N-1)
    kc_curve = get_kc_curve(crop)
    p_tab_val = crop.p

    for t in range(n_cycle):
        idx = SPINUP_DAYS + t
        kc_val = kc_curve[t]
        prec_t = prec_mat[idx, :]
        et0_t = et0_mat[idx, :]

        dr, eta, etc, _, _, _, _ = wb_step(
            dr=dr,
            prec=prec_t,
            et0=et0_t,
            kc=kc_val,
            p_tab=p_tab_val,
            taw=taw,
            cn=cn_val,
        )
        sum_eta += eta
        sum_etc += etc

    # 3. Factor hídrico f_agua (FAO-56 ec. 90: ratio de sumas)
    ratio = np.where(sum_etc > 0.0, sum_eta / sum_etc, 1.0)
    f_agua = np.clip(1.0 - crop.ky * (1.0 - ratio), 0.0, 1.0)

    # 4. Factores térmicos
    # f_temp: aptitud térmica general
    tmean_cycle = (tmax_mat + tmin_mat) / 2.0
    f_temp = calc_temp_factor(tmean_cycle, crop.t_ecocrop)
    if np.ndim(f_temp) == 0:
        f_temp = np.full(m_campaigns, float(f_temp), dtype=float)

    # f_calor: golpe de calor en floración
    start_sens, end_sens = get_sensitive_window(crop)
    tmax_sens = tmax_mat[start_sens:end_sens, :]
    f_calor = calc_heat_factor(tmax_sens, crop.t_calor[0], crop.t_calor[1])
    if np.ndim(f_calor) == 0:
        f_calor = np.full(m_campaigns, float(f_calor), dtype=float)

    # f_helada: heladas en floración y ciclo vegetativo
    tmin_sens = tmin_mat[start_sens:end_sens, :]
    f_helada = calc_frost_factor(tmin_sens, tmin_mat, crop.t_helada)
    if np.ndim(f_helada) == 0:
        f_helada = np.full(m_campaigns, float(f_helada), dtype=float)

    # 5. Rendimiento relativo Y_rel
    y_rel = np.clip(f_agua * f_calor * f_helada * f_temp, 0.0, 1.0)

    # 6. Factor limitante con orden de desempate (§4.5: agua, calor, helada, temperatura)
    limiting: list[str] = []
    order = ["agua", "calor", "helada", "temperatura"]

    for m in range(m_campaigns):
        if campaign_has_nan[m]:
            limiting.append("ninguno")
            continue

        f_vals = [float(f_agua[m]), float(f_calor[m]), float(f_helada[m]), float(f_temp[m])]
        min_val = min(f_vals)
        if min_val < 0.95:
            chosen = "ninguno"
            for name, val in zip(order, f_vals):
                if abs(val - min_val) < 1e-9:
                    chosen = name
                    break
            limiting.append(chosen)
        else:
            limiting.append("ninguno")

    # 7. Asignar NaN a campañas con datos incompletos
    if np.any(campaign_has_nan):
        y_rel = np.where(campaign_has_nan, np.nan, y_rel)
        f_agua = np.where(campaign_has_nan, np.nan, f_agua)
        f_calor = np.where(campaign_has_nan, np.nan, f_calor)
        f_helada = np.where(campaign_has_nan, np.nan, f_helada)
        f_temp = np.where(campaign_has_nan, np.nan, f_temp)
        sum_eta = np.where(campaign_has_nan, np.nan, sum_eta)
        sum_etc = np.where(campaign_has_nan, np.nan, sum_etc)

    return SlotSimulationResult(
        y_rel=y_rel,
        f_agua=f_agua,
        f_calor=f_calor,
        f_helada=f_helada,
        f_temp=f_temp,
        sum_eta=sum_eta,
        sum_etc=sum_etc,
        limiting=limiting,
    )
