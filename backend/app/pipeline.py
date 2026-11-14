"""PLAN §2.1, §2.2, §3 T4.4, §4.10 — Pipeline de simulación completa (analyze)."""

import hashlib
import json
from typing import Literal

import numpy as np
import pandas as pd

from app.config import (
    ASSUMPTIONS,
    CN,
    DATA_END,
    DATA_START,
    DAYS_IN_YEAR,
    PERCENT_BASE,
    RESOLUTION_NOTE,
)
from app.engine.alternatives import (
    enumerate_annual_plans,
    enumerate_candidate_rotations,
    select_profiles,
)
from app.engine.calendar import (
    get_season_partitions,
    get_season_start_date,
    get_valid_seasons,
)
from app.engine.cards import generate_card
from app.engine.climate import calc_climate_profile
from app.engine.et0 import add_et0
from app.engine.rotation import (
    evaluate_rotation,
    validate_rotation,
)
from app.engine.slot import calc_runoff
from app.engine.soil import calc_soil_score
from app.engine.table import SlotTable
from app.nasa.power import fetch_power
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    Meta,
    RotationResult,
)


class RotationValidationError(ValueError):
    """PLAN §2.1 — Error de validación en la rotación solicitada."""

    pass


# Caché en memoria para respuestas canónicas por hash SHA-256 del request
_ANALYZE_CACHE: dict[str, AnalyzeResponse] = {}


def clear_analyze_cache() -> None:
    """Limpia la caché en memoria del pipeline."""
    _ANALYZE_CACHE.clear()


def analyze(request: AnalyzeRequest, power_client=None) -> AnalyzeResponse:
    """PLAN §2.1, §2.2, §4.10 — Ejecuta el pipeline completo de análisis agronómico y climático."""
    # 1. Caché determinista en memoria por hash SHA-256 del JSON canónico del request
    req_json = request.model_dump_json()
    cache_key = hashlib.sha256(req_json.encode("utf-8")).hexdigest()
    if cache_key in _ANALYZE_CACHE:
        return _ANALYZE_CACHE[cache_key]

    # 2. Determinar hemisferio y validar rotación de entrada
    hemisphere: Literal["N", "S"] = "S" if request.lat < 0 else "N"
    is_valid, err_msg = validate_rotation(request.current_rotation, hemisphere)
    if not is_valid:
        raise RotationValidationError(err_msg)

    # 3. Datos de clima desde NASA POWER (con caché en disco y reintentos)
    power_data = fetch_power(
        lat=request.lat,
        lon=request.lon,
        start=DATA_START,
        end=DATA_END,
        client=power_client,
    )

    # 4. Cálculo de ET0 diario (Penman-Monteith con fallback Hargreaves)
    weather_df = add_et0(
        power_data.df, lat=request.lat, elevation_m=power_data.elevation_m
    )
    et0_hargreaves_share = float((weather_df["et0_method"] == "hg").mean())

    # 5. Calendario y particiones de campañas
    seasons = get_valid_seasons(hemisphere)
    partitions = get_season_partitions(seasons)
    eval_seasons = partitions["eval"]

    # 6. Perfil climático y climatología quincenal (before vs recent)
    climate_metrics, clim_before, clim_recent = calc_climate_profile(
        weather_df, seasons, hemisphere
    )

    # 7. Tabla memoizada de slots y pesos de escorrentía
    slot_table = SlotTable(
        weather_df, request.lat, request.soil_texture, seasons=seasons
    )

    cn_val = CN[request.soil_texture]
    ro_matrix = np.zeros((len(eval_seasons), DAYS_IN_YEAR), dtype=float)
    for idx, season in enumerate(eval_seasons):
        start_dt = pd.Timestamp(get_season_start_date(season, hemisphere))
        end_dt = start_dt + pd.Timedelta(days=DAYS_IN_YEAR - 1)
        season_slice = weather_df.loc[start_dt:end_dt]
        if len(season_slice) >= DAYS_IN_YEAR:
            prec_vals = season_slice["prec"].values[:DAYS_IN_YEAR]
            ro_matrix[idx, :] = calc_runoff(prec_vals, cn_val)
    w_runoff = np.mean(ro_matrix, axis=0)

    # 8. Evaluación de la rotación actual (línea base)
    current_soil = calc_soil_score(
        request.current_rotation,
        hemisphere,
        soil_texture=request.soil_texture,
        eval_seasons=eval_seasons,
        w_runoff=w_runoff,
    )
    (
        current_metrics,
        current_seasons_out,
        current_slots_out,
    ) = evaluate_rotation(
        request.current_rotation,
        slot_table,
        seasons,
        hemisphere,
        soil_score=current_soil,
    )
    current_metrics.productivity_vs_current = PERCENT_BASE

    # 9. Enumeración de alternativas y selección determinista de perfiles
    annual_plans = enumerate_annual_plans(slot_table, hemisphere, seasons=seasons)
    candidate_rotations = enumerate_candidate_rotations(
        annual_plans,
        slot_table,
        hemisphere,
        seasons=seasons,
        soil_texture=request.soil_texture,
        w_runoff=w_runoff,
    )
    selected_profiles = select_profiles(
        current_rotation=request.current_rotation,
        candidate_rotations=candidate_rotations,
        slot_table=slot_table,
        seasons=seasons,
        hemisphere=hemisphere,
        soil_texture=request.soil_texture,
        include_diversified=request.include_diversified,
        w_runoff=w_runoff,
        annual_plans=annual_plans,
        current_metrics=current_metrics,
    )

    # 10. Construcción de resultados de rotación con fichas por plantilla
    rotations_results: list[RotationResult] = []
    fixed_order: list[
        Literal["actual", "adaptada", "regenerativa", "diversificada"]
    ] = ["actual", "adaptada", "regenerativa"]
    if request.include_diversified:
        fixed_order.append("diversificada")

    for profile_key in fixed_order:
        if profile_key not in selected_profiles:
            continue
        sel = selected_profiles[profile_key]
        card = generate_card(
            profile=sel.profile,
            rotation=sel.rotation,
            metrics=sel.metrics,
            current_metrics=current_metrics,
            seasons_out=sel.seasons_out,
            current_seasons_out=current_seasons_out,
            slots_out=sel.slots_out,
            current_slots_out=current_slots_out,
            climate_metrics=climate_metrics,
            relaxed_constraints=sel.relaxed_constraints,
            improves_on_current=sel.improves_on_current,
            hemisphere=hemisphere,
            current_rotation=request.current_rotation,
        )
        res = RotationResult(
            profile=sel.profile,
            rotation=sel.rotation,
            slots=sel.slots_out,
            metrics=sel.metrics,
            seasons=sel.seasons_out,
            card=card,
        )
        rotations_results.append(res)

    # 11. Metadatos del análisis
    ag_year_start = "07-01" if hemisphere == "S" else "01-01"
    periods = {
        "before": (partitions["before"][0], partitions["before"][-1]),
        "recent": (partitions["recent"][0], partitions["recent"][-1]),
        "eval": (eval_seasons[0], eval_seasons[-1]),
    }
    meta = Meta(
        lat=request.lat,
        lon=request.lon,
        elevation_m=power_data.elevation_m,
        hemisphere=hemisphere,
        ag_year_start=ag_year_start,
        seasons=seasons,
        periods=periods,
        et0_hargreaves_share=et0_hargreaves_share,
        resolution_note=RESOLUTION_NOTE,
        assumptions=ASSUMPTIONS,
    )

    # 12. Ensamble de respuesta y actualización de caché
    response = AnalyzeResponse(
        meta=meta,
        climate=climate_metrics,
        climatology={"before": clim_before, "recent": clim_recent},
        rotations=rotations_results,
    )
    _ANALYZE_CACHE[cache_key] = response
    return response
