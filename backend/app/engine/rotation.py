"""PLAN §4.6 — Evaluación de rotación, modos, validación, métricas y año malo."""

from typing import Literal

import numpy as np

from app.config import (
    BAD_SEASON_I,
    DAYS_IN_YEAR,
    GAP_CROP_MAX_DAYS,
    LIMITING_THRESHOLD,
    MAX_OVERRUN_DAYS,
    N_BEFORE,
    P10_PERCENTILE,
    PERCENT_BASE,
    SLOT_FAIL,
    TOLERANCE_TIE,
    TURNAROUND_DAYS,
)
from app.data.crops import Crop, get_crop
from app.engine.calendar import (
    format_season_label,
    get_season_partitions,
    get_sow_offset,
    get_sowing_grid,
)
from app.engine.crop import get_sensitive_window
from app.engine.table import SlotTable
from app.schemas import (
    Rotation,
    RotationMetrics,
    SeasonOut,
    SlotOut,
    SoilScore,
)

LIMITING_PRIORITY: dict[str, int] = {
    "agua": 0,
    "calor": 1,
    "helada": 2,
    "temperatura": 3,
    "ninguno": 4,
}


def validate_rotation(
    rotation: Rotation,
    hemisphere: Literal["N", "S"],
) -> tuple[bool, str]:
    """PLAN §4.6 — Valida validez agronómica y temporal de una rotación.

    Criterios:
    1. Al menos un cultivo cosechable (cosechable == True).
    2. Para todo slot s: sow_offset + sum(crop.etapas_dias) <= 365 + MAX_OVERRUN_DAYS.
    3. Para todo slot s: gap(s) >= TURNAROUND_DAYS (cíclico sobre todos los años).
    """
    has_harvestable = False
    flat_slots: list[dict] = []

    for y_idx, year in enumerate(rotation.years):
        for s_idx, slot_in in enumerate(year.slots):
            try:
                crop = get_crop(slot_in.crop_id)
            except KeyError:
                return (False, f"Cultivo desconocido: '{slot_in.crop_id}'")

            if crop.cosechable:
                has_harvestable = True

            sow_off = get_sow_offset(slot_in.sow_date, hemisphere)
            harvest_off = sow_off + crop.ciclo

            if harvest_off > DAYS_IN_YEAR + MAX_OVERRUN_DAYS:
                return (
                    False,
                    f"El cultivo '{crop.id}' en fecha '{slot_in.sow_date}' excede el límite máximo de campaña "
                    f"({harvest_off} días > {DAYS_IN_YEAR + MAX_OVERRUN_DAYS} días)",
                )

            flat_slots.append(
                {
                    "year_idx": y_idx,
                    "slot_idx": s_idx,
                    "crop": crop,
                    "crop_id": slot_in.crop_id,
                    "sow_date": slot_in.sow_date,
                    "sow_offset": sow_off,
                    "harvest_offset": harvest_off,
                }
            )

    if not has_harvestable:
        return (False, "Debe existir al menos un cultivo cosechable")

    n_total = len(flat_slots)
    n_years = len(rotation.years)

    for idx in range(n_total):
        curr = flat_slots[idx]
        pred = flat_slots[(idx - 1) % n_total]

        if idx == 0:
            delta_years = n_years - pred["year_idx"] + curr["year_idx"]
        else:
            delta_years = curr["year_idx"] - pred["year_idx"]

        gap = delta_years * DAYS_IN_YEAR + curr["sow_offset"] - pred["harvest_offset"]

        if gap < TURNAROUND_DAYS:
            return (
                False,
                f"Tiempo entre cosecha de '{pred['crop_id']}' y siembra de '{curr['crop_id']}' "
                f"({gap} días) es menor al mínimo requerido de {TURNAROUND_DAYS} días",
            )

    return (True, "")


def calculate_rotation_gaps_and_modes(
    rotation: Rotation,
    hemisphere: Literal["N", "S"],
) -> list[list[tuple[int, Literal["fallow", "crop"]]]]:
    """PLAN §4.6 — Calcula (gap, prev_mode) para cada slot en cada año de la rotación.

    gap(s) = siembra(s) - cosecha(pred(s)) en orden cíclico.
    prev_mode = 'crop' si gap <= GAP_CROP_MAX_DAYS else 'fallow'.
    """
    flat_slots: list[dict] = []
    for y_idx, year in enumerate(rotation.years):
        for s_idx, slot_in in enumerate(year.slots):
            crop = get_crop(slot_in.crop_id)
            sow_off = get_sow_offset(slot_in.sow_date, hemisphere)
            harvest_off = sow_off + crop.ciclo
            flat_slots.append(
                {
                    "year_idx": y_idx,
                    "slot_idx": s_idx,
                    "sow_offset": sow_off,
                    "harvest_offset": harvest_off,
                }
            )

    n_total = len(flat_slots)
    n_years = len(rotation.years)

    gaps_by_slot: list[tuple[int, Literal["fallow", "crop"]]] = []
    for idx in range(n_total):
        curr = flat_slots[idx]
        pred = flat_slots[(idx - 1) % n_total]

        if idx == 0:
            delta_years = n_years - pred["year_idx"] + curr["year_idx"]
        else:
            delta_years = curr["year_idx"] - pred["year_idx"]

        gap = delta_years * DAYS_IN_YEAR + curr["sow_offset"] - pred["harvest_offset"]
        mode: Literal["fallow", "crop"] = "crop" if gap <= GAP_CROP_MAX_DAYS else "fallow"
        gaps_by_slot.append((gap, mode))

    result: list[list[tuple[int, Literal["fallow", "crop"]]]] = []
    flat_idx = 0
    for year in rotation.years:
        year_list: list[tuple[int, Literal["fallow", "crop"]]] = []
        for _ in year.slots:
            year_list.append(gaps_by_slot[flat_idx])
            flat_idx += 1
        result.append(year_list)

    return result


def evaluate_rotation(
    rotation: Rotation,
    slot_table: SlotTable,
    seasons: list[int],
    hemisphere: Literal["N", "S"],
    soil_score: SoilScore | None = None,
) -> tuple[RotationMetrics, list[SeasonOut], list[list[SlotOut]]]:
    """PLAN §4.6 — Evalúa la rotación sobre campañas históricas, promediando todas las fases.

    Retorna:
    - RotationMetrics sobre ventana eval (últimas 20 campañas).
    - list[SeasonOut] para todas las campañas válidas.
    - list[list[SlotOut]] con métricas por slot.
    """
    n_years = len(rotation.years)
    gaps_and_modes = calculate_rotation_gaps_and_modes(rotation, hemisphere)

    # 1. Resolver o alinear campañas entre slot_table y seasons solicitadas
    table_seasons = getattr(slot_table, "seasons", seasons)
    season_indices = [table_seasons.index(yr) for yr in seasons]

    grid = getattr(slot_table, "sowing_grid", get_sowing_grid(hemisphere))

    # 2. Recolectar resultados de simulación por año y slot
    crops_by_year: list[list[Crop]] = []
    results_by_year: list[list[object]] = []

    for y_idx, year in enumerate(rotation.years):
        crops_curr_year: list[Crop] = []
        results_curr_year: list[object] = []
        for s_idx, slot_in in enumerate(year.slots):
            crop = get_crop(slot_in.crop_id)
            crops_curr_year.append(crop)

            _, prev_mode = gaps_and_modes[y_idx][s_idx]
            if hasattr(slot_table, "get_grid_index"):
                grid_idx = slot_table.get_grid_index(slot_in.sow_date)
            else:
                grid_idx = grid.index(slot_in.sow_date)

            res = slot_table.get_slot_result(crop.id, grid_idx, prev_mode)
            results_curr_year.append(res)

        crops_by_year.append(crops_curr_year)
        results_by_year.append(results_curr_year)

    # 3. Evaluación campaña por campaña promediando las L fases (k = 1..L)
    seasons_out: list[SeasonOut] = []
    p_by_campaign: list[float] = []
    i_by_campaign: list[float] = []
    bad_by_campaign: list[bool] = []

    m_campaigns = len(seasons)
    for m in range(m_campaigns):
        y = seasons[m]
        s_idx_table = season_indices[m]

        harvestable_y_vals: list[float] = []
        harvestable_limitings: list[str] = []
        p_sum = 0.0
        pot_sum = 0.0

        for y_idx in range(n_years):
            for s_idx in range(len(rotation.years[y_idx].slots)):
                crop = crops_by_year[y_idx][s_idx]
                if crop.cosechable:
                    w_s = float(crop.value_weight)
                    res = results_by_year[y_idx][s_idx]
                    y_rel_val = float(res.y_rel[s_idx_table])
                    lim_val = str(res.limiting[s_idx_table])

                    p_sum += w_s * y_rel_val
                    pot_sum += w_s
                    harvestable_y_vals.append(y_rel_val)
                    harvestable_limitings.append(lim_val)

        p_y = p_sum / float(n_years)
        pot_y = pot_sum / float(n_years)
        i_y = (p_y / pot_y) if pot_y > 0.0 else 0.0
        mala_y = bool(i_y < BAD_SEASON_I)

        # Factor limitante del slot cosechable con menor Y_rel (desempate: agua > calor > helada > temperatura > ninguno)
        if len(harvestable_y_vals) == 0:
            limitante_y = "ninguno"
        else:
            min_y = min(harvestable_y_vals)
            if min_y >= LIMITING_THRESHOLD:
                limitante_y = "ninguno"
            else:
                candidate_limitings = [
                    lim
                    for y_v, lim in zip(harvestable_y_vals, harvestable_limitings)
                    if abs(y_v - min_y) < TOLERANCE_TIE
                ]
                limitante_y = min(
                    candidate_limitings,
                    key=lambda f: LIMITING_PRIORITY.get(f, 99),
                )

        p_by_campaign.append(p_y)
        i_by_campaign.append(i_y)
        bad_by_campaign.append(mala_y)

        seasons_out.append(
            SeasonOut(
                season=y,
                label=format_season_label(y, hemisphere),
                index=float(i_y),
                productivity=float(p_y),
                bad=mala_y,
                limiting=limitante_y,
            )
        )

    # 4. Generar SlotOut para cada slot de cada año
    partitions = get_season_partitions(seasons)
    eval_seasons = partitions["eval"]
    eval_indices = [seasons.index(yr) for yr in eval_seasons if yr in seasons]

    slots_out: list[list[SlotOut]] = []
    for y_idx, year in enumerate(rotation.years):
        year_slots_out: list[SlotOut] = []
        for s_idx, slot_in in enumerate(year.slots):
            crop = crops_by_year[y_idx][s_idx]
            res = results_by_year[y_idx][s_idx]
            _, prev_mode = gaps_and_modes[y_idx][s_idx]

            sow_off = get_sow_offset(slot_in.sow_date, hemisphere)
            stage_ends = [
                sow_off + crop.L_ini,
                sow_off + crop.L_ini + crop.L_dev,
                sow_off + crop.L_ini + crop.L_dev + crop.L_mid,
                sow_off + crop.ciclo,
            ]
            sens_start, sens_end = get_sensitive_window(crop)
            sens_window = (sow_off + sens_start, sow_off + sens_end)

            slot_y_all = res.y_rel[season_indices]
            slot_y_eval = slot_y_all[eval_indices] if len(eval_indices) > 0 else slot_y_all

            mean_yield = float(np.mean(slot_y_eval)) if len(slot_y_eval) > 0 else 0.0
            failures = int(np.sum(slot_y_eval < SLOT_FAIL))

            year_slots_out.append(
                SlotOut(
                    crop_id=crop.id,
                    crop_name=crop.nombre,
                    family=crop.familia,
                    harvested=crop.cosechable,
                    sow_date=slot_in.sow_date,
                    sow_offset=sow_off,
                    stage_ends=stage_ends,
                    sens_window=sens_window,
                    prev_mode=prev_mode,
                    mean_yield=mean_yield,
                    failures=failures,
                )
            )
        slots_out.append(year_slots_out)

    # 5. RotationMetrics sobre eval, before y recent
    i_arr = np.array(i_by_campaign, dtype=float)
    p_arr = np.array(p_by_campaign, dtype=float)
    mala_arr = np.array(bad_by_campaign, dtype=bool)

    before_seasons = partitions["before"]
    before_indices = [seasons.index(yr) for yr in before_seasons if yr in seasons]
    recent_seasons = partitions["recent"]
    recent_indices = [seasons.index(yr) for yr in recent_seasons if yr in seasons]

    i_eval = i_arr[eval_indices] if len(eval_indices) > 0 else i_arr
    p_eval = p_arr[eval_indices] if len(eval_indices) > 0 else p_arr
    mala_eval = mala_arr[eval_indices] if len(eval_indices) > 0 else mala_arr
    mala_before = mala_arr[before_indices] if len(before_indices) > 0 else mala_arr
    mala_recent = mala_arr[recent_indices] if len(recent_indices) > 0 else mala_arr

    mean_index = float(np.mean(i_eval)) if len(i_eval) > 0 else 0.0
    p10_index = (
        float(np.percentile(i_eval, P10_PERCENTILE, method="linear"))
        if len(i_eval) > 0
        else 0.0
    )
    mean_productivity = float(np.mean(p_eval)) if len(p_eval) > 0 else 0.0
    productivity_vs_current = PERCENT_BASE
    bad_seasons = int(np.sum(mala_eval))
    n_seasons = len(eval_indices) if len(eval_indices) > 0 else len(seasons)
    bad_before = int(np.sum(mala_before))
    bad_recent = int(np.sum(mala_recent))
    n_period = N_BEFORE

    soil = (
        soil_score
        if soil_score is not None
        else SoilScore(total=0.0, nitrogen=0.0, diversity=0.0, erosion=0.0, organic_matter=0.0)
    )

    metrics = RotationMetrics(
        mean_index=mean_index,
        p10_index=p10_index,
        mean_productivity=mean_productivity,
        productivity_vs_current=productivity_vs_current,
        bad_seasons=bad_seasons,
        n_seasons=n_seasons,
        bad_before=bad_before,
        bad_recent=bad_recent,
        n_period=n_period,
        soil=soil,
    )

    return (metrics, seasons_out, slots_out)
