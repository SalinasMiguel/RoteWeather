"""PLAN §4.8 — Perfil climático por campaña y análisis de cambio histórico (before vs recent)."""

import calendar
from datetime import date, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats

from app.config import (
    CESS_MIN_AFTER_ONSET,
    CESS_MM,
    CESS_WINDOW,
    DAYS_IN_YEAR,
    DRY_DAY_MM,
    DRY_SPELL_DAYS,
    FORTNIGHTS_IN_YEAR,
    GDD_BASE,
    HOT_DAY_C,
    MIN_OBS_MANNWHITNEY,
    MONTHS_IN_YEAR,
    N_BEFORE,
    N_RECENT,
    ONSET_LOOKAHEAD,
    ONSET_MM,
    ONSET_SEARCH_START,
    ONSET_WINDOW,
    Q1_END,
    Q2_END,
    Q3_END,
    SIGNIFICANCE_ALPHA,
)
from app.engine.calendar import (
    format_season_label,
    get_season_start_date,
)
from app.schemas import ClimateMetric, Climatology, Source

# Metadatos canónicos de las 14 métricas climáticas (PLAN §4.8)
CLIMATE_METRICS_INFO: list[dict[str, Any]] = [
    {
        "id": "rain_total",
        "label": "Lluvia total",
        "unit": "mm",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "rain_q1",
        "label": "Lluvia Q1 (días 0-90)",
        "unit": "mm",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "rain_q2",
        "label": "Lluvia Q2 (días 91-181)",
        "unit": "mm",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "rain_q3",
        "label": "Lluvia Q3 (días 182-272)",
        "unit": "mm",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "rain_q4",
        "label": "Lluvia Q4 (días 273-fin)",
        "unit": "mm",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "onset",
        "label": "Inicio de lluvias (onset)",
        "unit": "días",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "cessation",
        "label": "Fin de lluvias (cessation)",
        "unit": "días",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "season_length",
        "label": "Duración de estación lluviosa",
        "unit": "días",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "hot_days",
        "label": "Días con calor extremo (>35 °C)",
        "unit": "días",
        "parameters": ["T2M_MAX"],
    },
    {
        "id": "dry_spells",
        "label": "Rachas secas (≥10 días)",
        "unit": "rachas",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "max_dry_spell",
        "label": "Racha seca más larga",
        "unit": "días",
        "parameters": ["PRECTOTCORR"],
    },
    {
        "id": "gdd",
        "label": "Grados día acumulados (GDD base 10)",
        "unit": "°C·día",
        "parameters": ["T2M_MAX", "T2M_MIN"],
    },
    {
        "id": "et0_total",
        "label": "Evapotranspiración de referencia (ET0)",
        "unit": "mm",
        "parameters": ["T2M_MAX", "T2M_MIN", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN", "PS"],
    },
    {
        "id": "water_deficit",
        "label": "Déficit hídrico mensual acumulado",
        "unit": "mm",
        "parameters": ["PRECTOTCORR", "T2M_MAX", "T2M_MIN", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN", "PS"],
    },
]

POWER_DATASET_NAME: str = "NASA POWER (MERRA-2 / CERES SYN1deg)"


def calc_campaign_metrics(
    weather_df: pd.DataFrame,
    season: int,
    hemisphere: Literal["N", "S"],
) -> dict[str, float]:
    """PLAN §4.8 — Calcula las métricas agroclimáticas de una única campaña."""
    start_d = get_season_start_date(season, hemisphere)
    next_start_d = get_season_start_date(season + 1, hemisphere)
    end_d = next_start_d - timedelta(days=1)

    w_df = weather_df
    if isinstance(w_df.index, pd.DatetimeIndex):
        camp_dates = pd.date_range(start_d, end_d, freq="D")
        camp_df = w_df.reindex(camp_dates)
    elif "date" in w_df.columns:
        w_copy = w_df.copy()
        w_copy.index = pd.to_datetime(w_copy["date"])
        camp_dates = pd.date_range(start_d, end_d, freq="D")
        camp_df = w_copy.reindex(camp_dates)
    else:
        camp_df = w_df

    prec = camp_df["prec"].to_numpy(dtype=float) if "prec" in camp_df.columns else np.zeros(DAYS_IN_YEAR)
    tmax = camp_df["tmax"].to_numpy(dtype=float) if "tmax" in camp_df.columns else np.zeros(len(prec))
    tmin = camp_df["tmin"].to_numpy(dtype=float) if "tmin" in camp_df.columns else np.zeros(len(prec))
    et0 = camp_df["et0"].to_numpy(dtype=float) if "et0" in camp_df.columns else np.zeros(len(prec))

    n_days = len(prec)

    # 1. Totales y trimestres de precipitación
    rain_total = float(np.nansum(prec))
    rain_q1 = float(np.nansum(prec[0:Q1_END]))
    rain_q2 = float(np.nansum(prec[Q1_END:Q2_END]))
    rain_q3 = float(np.nansum(prec[Q2_END:Q3_END]))
    rain_q4 = float(np.nansum(prec[Q3_END:]))

    # 2. Inicio de lluvias (onset)
    onset_val = np.nan
    for o in range(ONSET_SEARCH_START, n_days):
        if o + ONSET_WINDOW > n_days:
            break
        sum_window = np.sum(prec[o : o + ONSET_WINDOW])
        if sum_window < ONSET_MM:
            continue

        end_look = min(o + ONSET_LOOKAHEAD, n_days)
        look_prec = prec[o:end_look]

        has_dry_spell = False
        dry_run = 0
        for p in look_prec:
            if p < DRY_DAY_MM:
                dry_run += 1
                if dry_run >= DRY_SPELL_DAYS:
                    has_dry_spell = True
                    break
            else:
                dry_run = 0

        if not has_dry_spell:
            onset_val = float(o)
            break

    # 3. Fin de lluvias (cessation)
    cess_val = np.nan
    if not np.isnan(onset_val):
        start_c = int(onset_val) + CESS_MIN_AFTER_ONSET
        for c in range(start_c, n_days):
            if c + CESS_WINDOW > n_days:
                break
            sum_cess = np.sum(prec[c : c + CESS_WINDOW])
            if sum_cess < CESS_MM:
                cess_val = float(c)
                break

    # 4. Duración de la estación
    if not np.isnan(onset_val) and not np.isnan(cess_val):
        season_length_val = float(cess_val - onset_val)
    else:
        season_length_val = np.nan

    # 5. Días con calor extremo (>35 °C)
    hot_days_val = float(np.sum(tmax > HOT_DAY_C))

    # 6. Rachas secas dentro de [onset, cessation)
    if np.isnan(onset_val):
        dry_spells_val = np.nan
        max_dry_spell_val = np.nan
    else:
        start_off = int(onset_val)
        end_off = int(cess_val) if not np.isnan(cess_val) else n_days
        prec_window = prec[start_off:end_off]

        spell_count = 0
        max_run = 0
        current_run = 0
        for p in prec_window:
            if p < DRY_DAY_MM:
                current_run += 1
                if current_run > max_run:
                    max_run = current_run
            else:
                if current_run >= DRY_SPELL_DAYS:
                    spell_count += 1
                current_run = 0
        if current_run >= DRY_SPELL_DAYS:
            spell_count += 1

        dry_spells_val = float(spell_count)
        max_dry_spell_val = float(max_run)

    # 7. Grados día acumulados (GDD base 10)
    gdd_arr = np.maximum(0.0, (tmax + tmin) / 2.0 - GDD_BASE)
    gdd_val = float(np.nansum(gdd_arr))

    # 8. ET0 total
    et0_total_val = float(np.nansum(et0))

    # 9. Déficit hídrico mensual acumulado
    if isinstance(camp_df.index, pd.DatetimeIndex):
        monthly_p = camp_df["prec"].groupby(camp_df.index.to_period("M")).sum()
        if "et0" in camp_df.columns:
            monthly_e = camp_df["et0"].groupby(camp_df.index.to_period("M")).sum()
        else:
            monthly_e = pd.Series(0.0, index=monthly_p.index)
        water_def_val = float(np.sum(np.maximum(0.0, monthly_e - monthly_p)))
    else:
        month_lengths = [31, 31, 30, 31, 30, 31, 31, 28, 31, 30, 31, 30]
        idx = 0
        water_def_val = 0.0
        for ml in month_lengths:
            sub_p = prec[idx : idx + ml]
            sub_e = et0[idx : idx + ml]
            idx += ml
            water_def_val += max(0.0, float(np.sum(sub_e) - np.sum(sub_p)))

    return {
        "rain_total": rain_total,
        "rain_q1": rain_q1,
        "rain_q2": rain_q2,
        "rain_q3": rain_q3,
        "rain_q4": rain_q4,
        "onset": onset_val,
        "cessation": cess_val,
        "season_length": season_length_val,
        "hot_days": hot_days_val,
        "dry_spells": dry_spells_val,
        "max_dry_spell": max_dry_spell_val,
        "gdd": gdd_val,
        "et0_total": et0_total_val,
        "water_deficit": water_def_val,
    }


def _calc_period_climatology(
    weather_df: pd.DataFrame,
    period_seasons: list[int],
    hemisphere: Literal["N", "S"],
) -> Climatology:
    """PLAN §4.8 — Climatología quincenal (24 bins desde inicio de campaña)."""
    if hemisphere == "S":
        month_order = [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6]
    else:
        month_order = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    w_df = weather_df
    has_datetime = isinstance(w_df.index, pd.DatetimeIndex)

    rain_bins: list[list[float]] = [[] for _ in range(FORTNIGHTS_IN_YEAR)]
    et0_bins: list[list[float]] = [[] for _ in range(FORTNIGHTS_IN_YEAR)]
    tmax_bins: list[list[float]] = [[] for _ in range(FORTNIGHTS_IN_YEAR)]
    tmin_bins: list[list[float]] = [[] for _ in range(FORTNIGHTS_IN_YEAR)]

    for season in period_seasons:
        if has_datetime:
            for i, m in enumerate(month_order):
                if hemisphere == "N":
                    y = season
                else:
                    y = season if m >= 7 else season + 1

                last_day = calendar.monthrange(y, m)[1]
                dates_q1 = pd.date_range(date(y, m, 1), date(y, m, 15), freq="D")
                dates_q2 = pd.date_range(date(y, m, 16), date(y, m, last_day), freq="D")

                for b_idx, d_range in [(2 * i, dates_q1), (2 * i + 1, dates_q2)]:
                    s = w_df.reindex(d_range)
                    rain_bins[b_idx].append(float(np.nansum(s["prec"])))
                    et0_bins[b_idx].append(
                        float(np.nansum(s["et0"])) if "et0" in s.columns else 0.0
                    )
                    tmax_bins[b_idx].append(
                        float(np.nanmean(s["tmax"])) if "tmax" in s.columns else 0.0
                    )
                    tmin_bins[b_idx].append(
                        float(np.nanmean(s["tmin"])) if "tmin" in s.columns else 0.0
                    )
        else:
            # Fallback para DataFrames sintéticos sin fechas explícitas
            splits = np.array_split(np.arange(len(w_df)), FORTNIGHTS_IN_YEAR)
            prec = w_df["prec"].to_numpy(dtype=float) if "prec" in w_df.columns else np.zeros(len(w_df))
            et0 = w_df["et0"].to_numpy(dtype=float) if "et0" in w_df.columns else np.zeros(len(w_df))
            tmax = w_df["tmax"].to_numpy(dtype=float) if "tmax" in w_df.columns else np.zeros(len(w_df))
            tmin = w_df["tmin"].to_numpy(dtype=float) if "tmin" in w_df.columns else np.zeros(len(w_df))

            for b_idx, idxs in enumerate(splits):
                rain_bins[b_idx].append(float(np.nansum(prec[idxs])))
                et0_bins[b_idx].append(float(np.nansum(et0[idxs])))
                tmax_bins[b_idx].append(float(np.nanmean(tmax[idxs])))
                tmin_bins[b_idx].append(float(np.nanmean(tmin[idxs])))

    rain_mm = [round(float(np.nanmean(b)), 2) if b else 0.0 for b in rain_bins]
    et0_mm = [round(float(np.nanmean(b)), 2) if b else 0.0 for b in et0_bins]
    tmax_c = [round(float(np.nanmean(b)), 2) if b else 0.0 for b in tmax_bins]
    tmin_c = [round(float(np.nanmean(b)), 2) if b else 0.0 for b in tmin_bins]

    return Climatology(
        rain_mm=rain_mm,
        et0_mm=et0_mm,
        tmax_c=tmax_c,
        tmin_c=tmin_c,
    )


def calc_climate_profile(
    weather_df: pd.DataFrame,
    seasons: list[int],
    hemisphere: Literal["N", "S"],
) -> tuple[list[ClimateMetric], Climatology, Climatology]:
    """PLAN §4.8 — Perfil climático comparando before vs recent y climatología quincenal."""
    seasons_before = seasons[:N_BEFORE]
    seasons_recent = seasons[-N_RECENT:]

    # 1. Calcular métricas anuales para cada campaña
    campaign_metrics: dict[int, dict[str, float]] = {}
    for s in seasons:
        campaign_metrics[s] = calc_campaign_metrics(weather_df, s, hemisphere)

    period_str = (
        f"campañas {format_season_label(seasons[0], hemisphere)}–{format_season_label(seasons[-1], hemisphere)}"
    )

    metrics_out: list[ClimateMetric] = []
    for info in CLIMATE_METRICS_INFO:
        m_id = info["id"]

        series: list[tuple[int, float | None]] = []
        for s in seasons:
            v = campaign_metrics[s][m_id]
            series.append((s, None if np.isnan(v) else round(float(v), 2)))

        vals_before = [campaign_metrics[s][m_id] for s in seasons_before]
        vals_recent = [campaign_metrics[s][m_id] for s in seasons_recent]

        valid_before = [v for v in vals_before if not np.isnan(v)]
        valid_recent = [v for v in vals_recent if not np.isnan(v)]

        val_before = float(np.nanmean(vals_before)) if valid_before else 0.0
        val_recent = float(np.nanmean(vals_recent)) if valid_recent else 0.0
        delta = float(val_recent - val_before)

        p_value: float | None = None
        significant: bool = False

        if (
            len(valid_before) >= MIN_OBS_MANNWHITNEY
            and len(valid_recent) >= MIN_OBS_MANNWHITNEY
        ):
            if np.array_equal(valid_before, valid_recent):
                p_value = 1.0
                significant = False
            else:
                try:
                    res = stats.mannwhitneyu(
                        valid_before, valid_recent, alternative="two-sided"
                    )
                    if not np.isnan(res.pvalue):
                        p_value = float(res.pvalue)
                        significant = p_value < SIGNIFICANCE_ALPHA
                    else:
                        p_value = None
                        significant = False
                except Exception:
                    p_value = None
                    significant = False

        source = Source(
            dataset=POWER_DATASET_NAME,
            parameters=info["parameters"],
            period=period_str,
        )

        metric = ClimateMetric(
            id=m_id,
            label=info["label"],
            unit=info["unit"],
            before=round(val_before, 2),
            recent=round(val_recent, 2),
            delta=round(delta, 2),
            p_value=round(p_value, 4) if p_value is not None else None,
            significant=significant,
            series=series,
            source=source,
        )
        metrics_out.append(metric)

    # 2. Climatología quincenal
    climatology_before = _calc_period_climatology(weather_df, seasons_before, hemisphere)
    climatology_recent = _calc_period_climatology(weather_df, seasons_recent, hemisphere)

    return (metrics_out, climatology_before, climatology_recent)
