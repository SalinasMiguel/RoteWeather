"""PLAN §4.7 — Puntaje de salud de suelo (0–100, reglas agronómicas y erosión)."""

from typing import Literal

import numpy as np
import pandas as pd

from app.config import (
    CN,
    COMPONENT_WEIGHT,
    COVER_CROP_BONUS,
    COVER_FULL,
    DAYS_IN_YEAR,
    DIVERSITY_BASE,
    N_BASE,
    N_POINTS,
    N_SCALE,
    OM_MAX_PTS,
    REPEAT_PENALTY,
    RESIDUE_COVER,
    RESIDUE_POINTS,
    SCORE_MAX,
    SCORE_MIN,
)
from app.data.crops import get_crop
from app.engine.calendar import (
    get_season_partitions,
    get_season_start_date,
    get_sow_offset,
    get_valid_seasons,
)
from app.engine.slot import calc_runoff
from app.schemas import Rotation, SoilScore


def calc_soil_score(
    rotation: Rotation,
    hemisphere: Literal["N", "S"],
    weather_df: pd.DataFrame | None = None,
    soil_texture: str = "franco",
    eval_seasons: list[int] | None = None,
    w_runoff: np.ndarray | None = None,
) -> SoilScore:
    """PLAN §4.7 — Calcula el puntaje de suelo compuesto (0–100)."""
    # 1. Secuencia cíclica de todos los slots
    seq = []
    for year in rotation.years:
        for slot in year.slots:
            seq.append(slot)

    n_slots = len(seq)
    l_years = len(rotation.years)
    seq_crops = [get_crop(slot.crop_id) for slot in seq]

    # --------------------------------------------------------------------------
    # Componente 1: Nitrógeno
    # N_año = (1/L)·Σ_s N_POINTS[clase_n(s)]
    # nitrogen = clip(60 + 20·N_año, 0, 100)
    # --------------------------------------------------------------------------
    n_ano = (1.0 / l_years) * sum(N_POINTS[crop.clase_n] for crop in seq_crops)
    nitrogen = float(np.clip(N_BASE + N_SCALE * n_ano, SCORE_MIN, SCORE_MAX))

    # --------------------------------------------------------------------------
    # Componente 2: Diversidad
    # n_fam = nº de familias distintas en seq
    # repite = (nº de pares cíclicos adyacentes con la misma familia)/len(seq) (1 slot -> 1.0)
    # diversity = DIVERSITY_BASE.get(n_fam, 100)·(1 − 0.5·repite)
    # --------------------------------------------------------------------------
    families = [crop.familia for crop in seq_crops]
    n_fam = len(set(families))

    if n_slots == 1:
        repite = 1.0
    else:
        same_adjacent_count = sum(
            1 for i in range(n_slots) if families[i] == families[(i + 1) % n_slots]
        )
        repite = same_adjacent_count / n_slots

    base_div = float(DIVERSITY_BASE.get(n_fam, SCORE_MAX))
    diversity = float(base_div * (1.0 - REPEAT_PENALTY * repite))

    # --------------------------------------------------------------------------
    # Componente 3: Materia orgánica
    # pts(s) = RESIDUE_POINTS[clase_rastrojo(s)] + (COVER_CROP_BONUS si no cosechable)
    # organic_matter = clip(100·((1/L)·Σ_s pts(s))/6, 0, 100)
    # --------------------------------------------------------------------------
    pts_total = sum(
        RESIDUE_POINTS[crop.clase_rastrojo] + (COVER_CROP_BONUS if not crop.cosechable else 0)
        for crop in seq_crops
    )
    om_val = (SCORE_MAX * ((1.0 / l_years) * pts_total)) / OM_MAX_PTS
    organic_matter = float(np.clip(om_val, SCORE_MIN, SCORE_MAX))

    # --------------------------------------------------------------------------
    # Componente 4: Erosión (ponderada por escorrentía)
    # --------------------------------------------------------------------------
    if w_runoff is not None:
        w_arr = np.asarray(w_runoff, dtype=float)
    elif weather_df is not None:
        cn_val = float(CN.get(soil_texture, CN["franco"]))
        w_df = weather_df
        if not isinstance(w_df.index, pd.DatetimeIndex) and "date" in w_df.columns:
            w_df = w_df.copy()
            w_df.index = pd.to_datetime(w_df["date"])

        if eval_seasons is not None:
            seasons_to_use = eval_seasons
        else:
            all_valid = get_valid_seasons(hemisphere)
            seasons_to_use = get_season_partitions(all_valid)["eval"]

        runoff_campaigns = []
        for y in seasons_to_use:
            start_d = get_season_start_date(y, hemisphere)
            camp_dates = pd.date_range(start_d, periods=DAYS_IN_YEAR, freq="D")
            camp_slice = w_df.reindex(camp_dates)
            prec_y = camp_slice["prec"].fillna(0.0).to_numpy(dtype=float)
            ro_y = calc_runoff(prec_y, cn_val)
            runoff_campaigns.append(ro_y)

        if runoff_campaigns:
            w_arr = np.mean(runoff_campaigns, axis=0)
        else:
            w_arr = np.zeros(DAYS_IN_YEAR, dtype=float)
    else:
        w_arr = np.zeros(DAYS_IN_YEAR, dtype=float)

    sum_w = float(np.sum(w_arr))
    if sum_w == 0.0 or np.isnan(sum_w):
        erosion = SCORE_MAX
    else:
        erosion_by_year = []
        for k, year in enumerate(rotation.years):
            cover_k = np.zeros(DAYS_IN_YEAR, dtype=float)

            # Predecesor cíclico del año k: último slot del año anterior (k - 1) % L
            prev_year_idx = (k - 1) % l_years
            last_slot_prev = rotation.years[prev_year_idx].slots[-1]
            last_crop_prev = get_crop(last_slot_prev.crop_id)
            prev_residue_cover = RESIDUE_COVER[last_crop_prev.clase_rastrojo]

            # Inicializar hasta la primera siembra con el rastrojo del cultivo previo
            cover_k[:] = prev_residue_cover

            # Información de slots en año k
            curr_pred_crop = last_crop_prev
            for slot in year.slots:
                sow_off = get_sow_offset(slot.sow_date, hemisphere)
                crop = get_crop(slot.crop_id)
                n_cycle = crop.ciclo
                l_ini = crop.L_ini
                l_dev = crop.L_dev
                r = RESIDUE_COVER[curr_pred_crop.clase_rastrojo]

                # Durante el cultivo: t = 0..n_cycle-1
                for t in range(n_cycle):
                    o = sow_off + t
                    if o >= DAYS_IN_YEAR:
                        break
                    if t < l_ini:
                        c_val = r
                    elif t < l_ini + l_dev:
                        c_val = max(r, (t - l_ini) / l_dev) if l_dev > 0 else COVER_FULL
                    else:
                        c_val = COVER_FULL
                    cover_k[o] = c_val

                # Tras cosecha y hasta siguiente siembra: rastrojo de este cultivo cosechado
                harvest_off = sow_off + n_cycle
                if harvest_off < DAYS_IN_YEAR:
                    cover_k[harvest_off:] = RESIDUE_COVER[crop.clase_rastrojo]

                curr_pred_crop = crop

            erosion_k = float(np.sum(w_arr * cover_k) / sum_w)
            erosion_by_year.append(erosion_k)

        erosion = float(SCORE_MAX * np.mean(erosion_by_year))

    total = float(COMPONENT_WEIGHT * (nitrogen + diversity + erosion + organic_matter))

    return SoilScore(
        total=round(total, 2),
        nitrogen=round(nitrogen, 2),
        diversity=round(diversity, 2),
        erosion=round(erosion, 2),
        organic_matter=round(organic_matter, 2),
    )
