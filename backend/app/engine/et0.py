"""PLAN §4.2 — ET0 (mm/día): Penman-Monteith, Hargreaves y radiación extraterrestre."""

import numpy as np
import pandas as pd


def calc_ra(lat_rad: float, day_of_year: int | np.ndarray) -> float | np.ndarray:
    """PLAN §4.2 — Radiación extraterrestre Ra (FAO-56 ec. 21-25) en MJ/m²/día."""
    is_scalar = np.ndim(day_of_year) == 0
    j = np.asarray(day_of_year, dtype=float)

    dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * j / 365.0)
    delta = 0.409 * np.sin(2.0 * np.pi * j / 365.0 - 1.39)
    x = -np.tan(lat_rad) * np.tan(delta)
    omega_s = np.arccos(np.clip(x, -1.0, 1.0))

    ra = (24.0 * 60.0 / np.pi) * 0.0820 * dr * (
        omega_s * np.sin(lat_rad) * np.sin(delta) + np.cos(lat_rad) * np.cos(delta) * np.sin(omega_s)
    )

    if is_scalar:
        return float(ra)
    return ra


def calc_et0_penman_monteith(
    tmax: float | np.ndarray,
    tmin: float | np.ndarray,
    rh: float | np.ndarray,
    rs: float | np.ndarray,
    ws: float | np.ndarray,
    ps: float | np.ndarray,
    lat_rad: float,
    elevation_m: float,
    day_of_year: int | np.ndarray,
) -> float | np.ndarray:
    """PLAN §4.2 — Penman-Monteith (FAO-56 ec. 6) en mm/día. Usa T = (tmax+tmin)/2."""
    is_scalar = (
        np.ndim(tmax) == 0
        and np.ndim(tmin) == 0
        and np.ndim(rh) == 0
        and np.ndim(rs) == 0
        and np.ndim(ws) == 0
    )

    tmax_arr = np.asarray(tmax, dtype=float)
    tmin_arr = np.asarray(tmin, dtype=float)
    rh_arr = np.asarray(rh, dtype=float)
    rs_arr = np.asarray(rs, dtype=float)
    ws_arr = np.asarray(ws, dtype=float)
    ps_arr = np.asarray(ps, dtype=float)
    j_arr = np.asarray(day_of_year, dtype=float)

    # 1. Temperatura media T = (tmax + tmin) / 2 (REGLA AGENTS.md: NO usar t2m)
    t_mean = (tmax_arr + tmin_arr) / 2.0

    # 2. Presión de vapor de saturación es y actual ea (FAO-56 ec. 11, 12, 19)
    e0_tmax = 0.6108 * np.exp(17.27 * tmax_arr / (tmax_arr + 237.3))
    e0_tmin = 0.6108 * np.exp(17.27 * tmin_arr / (tmin_arr + 237.3))
    es = (e0_tmax + e0_tmin) / 2.0
    ea = es * rh_arr / 100.0

    # 3. Pendiente de la curva de presión de vapor Delta (FAO-56 ec. 13)
    e0_tmean = 0.6108 * np.exp(17.27 * t_mean / (t_mean + 237.3))
    delta = 4098.0 * e0_tmean / ((t_mean + 237.3) ** 2)

    # 4. Presión atmosférica P y constante psicrométrica gamma (FAO-56 ec. 7, 8)
    p_std = 101.3 * (((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26)
    p_val = np.where(np.isnan(ps_arr), p_std, ps_arr)
    gamma = 0.000665 * p_val

    # 5. Radiación solar neta y de onda larga (FAO-56 ec. 37, 38, 39)
    ra = calc_ra(lat_rad, j_arr)
    rso = (0.75 + 2e-5 * elevation_m) * ra
    rns = 0.77 * rs_arr

    # Factor de nubosidad / cielo despejado
    safe_rso = np.where(rso <= 0.0, 1e-6, rso)
    f_cd = 1.35 * np.clip(rs_arr / safe_rso, 0.3, 1.0) - 0.35

    # Radiación neta de onda larga Rnl (FAO-56 ec. 39)
    tmax_k4 = (tmax_arr + 273.16) ** 4
    tmin_k4 = (tmin_arr + 273.16) ** 4
    ea_safe = np.maximum(ea, 0.0)
    rnl = 4.903e-9 * ((tmax_k4 + tmin_k4) / 2.0) * (0.34 - 0.14 * np.sqrt(ea_safe)) * f_cd

    rn = rns - rnl

    # 6. Ecuación combinada FAO-56 ec. 6
    num = 0.408 * delta * rn + gamma * (900.0 / (t_mean + 273.0)) * ws_arr * (es - ea)
    den = delta + gamma * (1.0 + 0.34 * ws_arr)
    et0_pm = num / den

    if is_scalar:
        return float(et0_pm)
    return et0_pm


def calc_et0_hargreaves(
    tmax: float | np.ndarray,
    tmin: float | np.ndarray,
    ra: float | np.ndarray,
) -> float | np.ndarray:
    """PLAN §4.2 — Hargreaves (FAO-56 ec. 52) en mm/día con factor 0.408."""
    is_scalar = np.ndim(tmax) == 0 and np.ndim(tmin) == 0 and np.ndim(ra) == 0

    tmax_arr = np.asarray(tmax, dtype=float)
    tmin_arr = np.asarray(tmin, dtype=float)
    ra_arr = np.asarray(ra, dtype=float)

    t_mean = (tmax_arr + tmin_arr) / 2.0
    tdiff = np.maximum(tmax_arr - tmin_arr, 0.0)

    # Factor 0.408 para convertir de MJ/m²/día a mm/día
    et0_hg = 0.0023 * (t_mean + 17.8) * np.sqrt(tdiff) * ra_arr * 0.408

    if is_scalar:
        return float(et0_hg)
    return et0_hg


def add_et0(df: pd.DataFrame, lat: float, elevation_m: float) -> pd.DataFrame:
    """PLAN §4.2 — Añade columnas 'et0' y 'et0_method' ('pm' o 'hg') decidiendo por día."""
    out_df = df.copy()

    # Latitud en radianes para fórmulas de radiación (AGENTS.md: latitud en radianes)
    lat_rad = float(np.radians(lat))

    # Día del año J desde el índice temporal
    dt_idx = pd.to_datetime(out_df.index)
    if hasattr(dt_idx, "day_of_year"):
        doy = dt_idx.day_of_year.to_numpy()
    else:
        doy = dt_idx.dayofyear.to_numpy()

    tmax = out_df["tmax"].to_numpy(dtype=float)
    tmin = out_df["tmin"].to_numpy(dtype=float)
    rh = out_df["rh"].to_numpy(dtype=float) if "rh" in out_df.columns else np.full_like(tmax, np.nan)
    rs = out_df["rs"].to_numpy(dtype=float) if "rs" in out_df.columns else np.full_like(tmax, np.nan)
    ws = out_df["ws"].to_numpy(dtype=float) if "ws" in out_df.columns else np.full_like(tmax, np.nan)
    ps = out_df["ps"].to_numpy(dtype=float) if "ps" in out_df.columns else np.full_like(tmax, np.nan)

    # Radiación extraterrestre
    ra = calc_ra(lat_rad, doy)

    # Cálculos diarios para Penman-Monteith y Hargreaves
    et0_pm = calc_et0_penman_monteith(tmax, tmin, rh, rs, ws, ps, lat_rad, elevation_m, doy)
    et0_hg = calc_et0_hargreaves(tmax, tmin, ra)

    # Regla PLAN §4.2: ET0_pm si rh, rs y ws no son NaN; si no ET0_hg
    pm_mask = ~np.isnan(rh) & ~np.isnan(rs) & ~np.isnan(ws) & ~np.isnan(et0_pm)

    et0 = np.where(pm_mask, et0_pm, et0_hg)
    et0 = np.maximum(et0, 0.0)

    method = np.where(pm_mask, "pm", "hg")

    out_df["et0"] = et0
    out_df["et0_method"] = method
    return out_df
