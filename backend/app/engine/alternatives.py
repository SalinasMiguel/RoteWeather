"""PLAN §5 — Generación de alternativas y selección determinista de perfiles."""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.config import (
    ADAPT_MIN_PROD,
    BAD_SEASON_I,
    CANDIDATE_TOP_PERF,
    CANDIDATE_TOP_SOIL,
    DAYS_IN_YEAR,
    DIVERSIFIED_CYCLE_YEARS,
    DIVERSIFIED_MIN_CROPS,
    DIVERSIFIED_MIN_FAMILIES,
    GAP_CROP_MAX_DAYS,
    IMPROVE_PROD_RATIO,
    MAX_OVERRUN_DAYS,
    N_EVAL,
    PERCENT_BASE,
    REGEN_MAX_LOSS,
    REGEN_MAX_LOSS_RELAXED,
    REGEN_MIN_SOIL_GAIN,
    REGEN_MIN_SOIL_GAIN_RELAXED,
    TURNAROUND_DAYS,
    VIABLE_MIN,
    VIABLE_MIN_COVER,
)
from app.data.crops import get_crop, load_crops
from app.engine.calendar import (
    get_season_partitions,
    get_sow_offset,
    get_sowing_grid,
    get_valid_seasons,
)
from app.engine.rotation import (
    evaluate_rotation,
    validate_rotation,
)
from app.engine.soil import calc_soil_score
from app.engine.table import SlotTable
from app.schemas import (
    Rotation,
    RotationMetrics,
    RotationYear,
    SeasonOut,
    SlotIn,
    SlotOut,
    SoilScore,
)


def get_rotation_id(rotation: Rotation) -> str:
    """PLAN §5.3 — Genera string canónico del id de rotación."""
    return "|".join(
        "+".join(f"{slot.crop_id}@{slot.sow_date}" for slot in year.slots)
        for year in rotation.years
    )


def get_crop_multiset(rotation: Rotation) -> tuple[tuple[str, int], ...]:
    """Retorna multiconjunto inmutable y canónico de cultivos de la rotación."""
    counter = Counter(
        slot.crop_id for year in rotation.years for slot in year.slots
    )
    return tuple(sorted(counter.items()))


@dataclass(frozen=True)
class AnnualPlan:
    """PLAN §5.1 — Plan anual de 1 o 2 slots con fechas óptimas sobre tabla suavizada."""

    crop_ids: tuple[str, ...]
    grid_indices: tuple[int, ...]
    sow_dates: tuple[str, ...]
    rotation: Rotation
    id: str
    bad_seasons: int = 0
    mean_prod: float = 0.0


@dataclass
class CandidateRotation:
    """PLAN §5.2 — Rotación candidata (1 o 2 años) evaluada con tabla sin suavizar."""

    rotation: Rotation
    id: str
    metrics: RotationMetrics
    seasons_out: list[SeasonOut]
    slots_out: list[list[SlotOut]]
    crop_multiset: tuple[tuple[str, int], ...]
    n_years: int
    n_families: int
    n_harvestable_crops: int


@dataclass
class SelectedProfile:
    """PLAN §5.3 — Perfil de rotación seleccionado con trazabilidad de relajaciones."""

    profile: Literal["actual", "adaptada", "regenerativa", "diversificada"]
    rotation: Rotation
    id: str
    metrics: RotationMetrics
    seasons_out: list[SeasonOut]
    slots_out: list[list[SlotOut]]
    relaxed_constraints: list[str]
    improves_on_current: bool


def enumerate_annual_plans(
    slot_table: SlotTable,
    hemisphere: Literal["N", "S"],
    seasons: list[int] | None = None,
) -> list[AnnualPlan]:
    """PLAN §5.1 — Genera planes anuales viables con fechas optimizadas en tabla suavizada."""
    crops = load_crops()
    grid = get_sowing_grid(hemisphere)
    if seasons is None:
        seasons = slot_table.seasons

    partitions = get_season_partitions(seasons)
    eval_seasons = partitions["eval"]
    eval_indices = [i for i, s in enumerate(seasons) if s in eval_seasons]

    # Matriz de viabilidad: viable(c, g)
    viable: dict[tuple[str, int], bool] = {}
    for crop_id, crop in crops.items():
        threshold = VIABLE_MIN if crop.cosechable else VIABLE_MIN_COVER
        for g in range(len(grid)):
            smoothed_y = slot_table.get_smoothed_y_rel(crop_id, g, "fallow")
            eval_y = smoothed_y[eval_indices]
            mean_eval_y = float(np.mean(eval_y))
            viable[(crop_id, g)] = mean_eval_y >= threshold

    plans: list[AnnualPlan] = []

    # 1. Planes simples (c)
    for crop_id, crop in sorted(crops.items(), key=lambda x: x[0]):
        if not crop.cosechable:
            continue

        best_cand = None
        best_key = None

        for g in range(len(grid)):
            if not viable[(crop_id, g)]:
                continue

            smoothed_y = slot_table.get_smoothed_y_rel(crop_id, g, "fallow")
            y_eval = smoothed_y[eval_indices]
            p_eval = crop.value_weight * y_eval
            i_eval = y_eval

            bad_seasons = int(np.sum(i_eval < BAD_SEASON_I))
            mean_prod = float(np.mean(p_eval))

            cand_key = (bad_seasons, -mean_prod, g)
            if best_key is None or cand_key < best_key:
                best_key = cand_key
                best_cand = (g, bad_seasons, mean_prod)

        if best_cand is not None:
            best_g, bad_seasons, mean_prod = best_cand
            sow_date = grid[best_g]
            rot = Rotation(
                years=[
                    RotationYear(
                        slots=[SlotIn(crop_id=crop_id, sow_date=sow_date)]
                    )
                ]
            )
            plan = AnnualPlan(
                crop_ids=(crop_id,),
                grid_indices=(best_g,),
                sow_dates=(sow_date,),
                rotation=rot,
                id=f"{crop_id}@{sow_date}",
                bad_seasons=bad_seasons,
                mean_prod=mean_prod,
            )
            plans.append(plan)

    # 2. Planes dobles (cA, cB)
    for cA_id, cA in sorted(crops.items(), key=lambda x: x[0]):
        for cB_id, cB in sorted(crops.items(), key=lambda x: x[0]):
            if not (cA.cosechable or cB.cosechable):
                continue

            best_cand = None
            best_key = None

            for gA in range(len(grid)):
                if not viable[(cA_id, gA)]:
                    continue
                sow_A = get_sow_offset(grid[gA], hemisphere)
                harvest_A = sow_A + cA.ciclo

                for gB in range(gA + 1, len(grid)):
                    if not viable[(cB_id, gB)]:
                        continue
                    sow_B = get_sow_offset(grid[gB], hemisphere)
                    harvest_B = sow_B + cB.ciclo

                    # Restricciones temporales y de descarte
                    if sow_B < harvest_A + TURNAROUND_DAYS:
                        continue
                    if harvest_B > DAYS_IN_YEAR + MAX_OVERRUN_DAYS:
                        continue
                    if harvest_B + TURNAROUND_DAYS > DAYS_IN_YEAR + sow_A:
                        continue

                    gap_B = sow_B - harvest_A
                    mode_B = (
                        "crop" if gap_B <= GAP_CROP_MAX_DAYS else "fallow"
                    )

                    gap_A = (DAYS_IN_YEAR + sow_A) - harvest_B
                    mode_A = (
                        "crop" if gap_A <= GAP_CROP_MAX_DAYS else "fallow"
                    )

                    yA_eval = slot_table.get_smoothed_y_rel(
                        cA_id, gA, mode_A
                    )[eval_indices]
                    yB_eval = slot_table.get_smoothed_y_rel(
                        cB_id, gB, mode_B
                    )[eval_indices]

                    wA = cA.value_weight if cA.cosechable else 0.0
                    wB = cB.value_weight if cB.cosechable else 0.0
                    pot = wA + wB
                    if pot <= 0:
                        continue

                    p_eval = wA * yA_eval + wB * yB_eval
                    i_eval = p_eval / pot

                    bad_seasons = int(np.sum(i_eval < BAD_SEASON_I))
                    mean_prod = float(np.mean(p_eval))

                    cand_key = (bad_seasons, -mean_prod, gA, gB)
                    if best_key is None or cand_key < best_key:
                        best_key = cand_key
                        best_cand = (gA, gB, bad_seasons, mean_prod)

            if best_cand is not None:
                best_gA, best_gB, bad_seasons, mean_prod = best_cand
                sow_date_A = grid[best_gA]
                sow_date_B = grid[best_gB]
                rot = Rotation(
                    years=[
                        RotationYear(
                            slots=[
                                SlotIn(crop_id=cA_id, sow_date=sow_date_A),
                                SlotIn(crop_id=cB_id, sow_date=sow_date_B),
                            ]
                        )
                    ]
                )
                plan = AnnualPlan(
                    crop_ids=(cA_id, cB_id),
                    grid_indices=(best_gA, best_gB),
                    sow_dates=(sow_date_A, sow_date_B),
                    rotation=rot,
                    id=f"{cA_id}@{sow_date_A}+{cB_id}@{sow_date_B}",
                    bad_seasons=bad_seasons,
                    mean_prod=mean_prod,
                )
                plans.append(plan)

    plans.sort(key=lambda p: p.id)
    return plans


# Alias para interoperabilidad
generate_annual_plans = enumerate_annual_plans


def enumerate_candidate_rotations(
    annual_plans: list[AnnualPlan],
    slot_table: SlotTable,
    hemisphere: Literal["N", "S"],
    seasons: list[int] | None = None,
    soil_texture: str = "franco",
    w_runoff: np.ndarray | None = None,
) -> list[CandidateRotation]:
    """PLAN §5.2 — Evalúa planes de 1 año y genera rotaciones de 2 años con tabla sin suavizar."""
    if seasons is None:
        seasons = slot_table.seasons

    partitions = get_season_partitions(seasons)
    eval_seasons = partitions["eval"]

    candidates_1yr: list[CandidateRotation] = []

    # 1. Candidatas de 1 año
    for plan in annual_plans:
        soil = calc_soil_score(
            plan.rotation,
            hemisphere,
            soil_texture=soil_texture,
            eval_seasons=eval_seasons,
            w_runoff=w_runoff,
        )
        metrics, seasons_out, slots_out = evaluate_rotation(
            plan.rotation, slot_table, seasons, hemisphere, soil_score=soil
        )
        c_multiset = get_crop_multiset(plan.rotation)
        families = {get_crop(cid).familia for cid in plan.crop_ids}
        n_harvestable = sum(
            1 for cid in plan.crop_ids if get_crop(cid).cosechable
        )

        cand = CandidateRotation(
            rotation=plan.rotation,
            id=plan.id,
            metrics=metrics,
            seasons_out=seasons_out,
            slots_out=slots_out,
            crop_multiset=c_multiset,
            n_years=1,
            n_families=len(families),
            n_harvestable_crops=n_harvestable,
        )
        candidates_1yr.append(cand)

    # 2. Pool para ciclo de 2 años: top30 (bad asc, mean_P desc) ∪ top10 (soil desc)
    top30 = sorted(
        candidates_1yr,
        key=lambda c: (
            c.metrics.bad_seasons,
            -c.metrics.mean_productivity,
            c.id,
        ),
    )[:CANDIDATE_TOP_PERF]

    top10 = sorted(
        candidates_1yr,
        key=lambda c: (-c.metrics.soil.total, -c.metrics.mean_productivity, c.id),
    )[:CANDIDATE_TOP_SOIL]

    pool_dict = {c.id: c for c in top30}
    for c in top10:
        pool_dict[c.id] = c
    pool = sorted(pool_dict.values(), key=lambda c: c.id)

    candidates_2yr: list[CandidateRotation] = []

    # 3. Pares no ordenados {p, q} con multiconjunto de cultivos distinto
    for i in range(len(pool)):
        p_cand = pool[i]
        for j in range(i + 1, len(pool)):
            q_cand = pool[j]

            if p_cand.crop_multiset == q_cand.crop_multiset:
                continue

            rot_2yr = Rotation(
                years=[p_cand.rotation.years[0], q_cand.rotation.years[0]]
            )
            is_valid, _ = validate_rotation(rot_2yr, hemisphere)
            if not is_valid:
                continue

            soil_2yr = calc_soil_score(
                rot_2yr,
                hemisphere,
                soil_texture=soil_texture,
                eval_seasons=eval_seasons,
                w_runoff=w_runoff,
            )
            metrics_2yr, seasons_2yr, slots_2yr = evaluate_rotation(
                rot_2yr,
                slot_table,
                seasons,
                hemisphere,
                soil_score=soil_2yr,
            )

            families = {
                get_crop(slot.crop_id).familia
                for year in rot_2yr.years
                for slot in year.slots
            }
            n_harvestable = len(
                {
                    slot.crop_id
                    for year in rot_2yr.years
                    for slot in year.slots
                    if get_crop(slot.crop_id).cosechable
                }
            )

            cand_2yr = CandidateRotation(
                rotation=rot_2yr,
                id=get_rotation_id(rot_2yr),
                metrics=metrics_2yr,
                seasons_out=seasons_2yr,
                slots_out=slots_2yr,
                crop_multiset=get_crop_multiset(rot_2yr),
                n_years=2,
                n_families=len(families),
                n_harvestable_crops=n_harvestable,
            )
            candidates_2yr.append(cand_2yr)

    all_candidates = candidates_1yr + candidates_2yr
    all_candidates.sort(key=lambda c: c.id)
    return all_candidates


# Alias para interoperabilidad
generate_candidate_rotations = enumerate_candidate_rotations


def select_profiles(
    current_rotation: Rotation,
    candidate_rotations: list[CandidateRotation] | None = None,
    slot_table: SlotTable | None = None,
    seasons: list[int] | None = None,
    hemisphere: Literal["N", "S"] | None = None,
    soil_texture: str = "franco",
    include_diversified: bool = False,
    w_runoff: np.ndarray | None = None,
    annual_plans: list[AnnualPlan] | None = None,
    current_metrics: RotationMetrics | None = None,
) -> dict[str, SelectedProfile]:
    """PLAN §5.3 — Selección determinista de perfiles (actual, adaptada, regenerativa[, diversificada])."""
    if hemisphere is None:
        if slot_table is not None:
            hemisphere = "S" if slot_table.lat < 0 else "N"
        else:
            hemisphere = "S"

    if seasons is None:
        if slot_table is not None:
            seasons = slot_table.seasons
        else:
            seasons = get_valid_seasons(hemisphere)

    partitions = get_season_partitions(seasons)
    eval_seasons = partitions["eval"]

    # 1. Asegurar planes anuales y candidatas
    if annual_plans is None:
        if slot_table is not None:
            annual_plans = enumerate_annual_plans(slot_table, hemisphere, seasons)
        else:
            annual_plans = []

    if candidate_rotations is None:
        if slot_table is not None:
            candidate_rotations = enumerate_candidate_rotations(
                annual_plans,
                slot_table,
                hemisphere,
                seasons,
                soil_texture=soil_texture,
                w_runoff=w_runoff,
            )
        else:
            candidate_rotations = []

    candidates_by_id = {c.id: c for c in candidate_rotations}
    plans_by_crops = {p.crop_ids: p for p in annual_plans}

    # 2. Perfil ACTUAL (Línea Base)
    actual_id = get_rotation_id(current_rotation)
    if current_metrics is None or slot_table is not None:
        actual_soil = calc_soil_score(
            current_rotation,
            hemisphere,
            soil_texture=soil_texture,
            eval_seasons=eval_seasons,
            w_runoff=w_runoff,
        )
        if slot_table is not None:
            (
                actual_metrics,
                actual_seasons_out,
                actual_slots_out,
            ) = evaluate_rotation(
                current_rotation,
                slot_table,
                seasons,
                hemisphere,
                soil_score=actual_soil,
            )
        else:
            actual_metrics = current_metrics
            actual_seasons_out = []
            actual_slots_out = []
    else:
        actual_metrics = current_metrics
        actual_seasons_out = []
        actual_slots_out = []

    actual_metrics.productivity_vs_current = PERCENT_BASE
    selected_actual = SelectedProfile(
        profile="actual",
        rotation=current_rotation,
        id=actual_id,
        metrics=actual_metrics,
        seasons_out=actual_seasons_out,
        slots_out=actual_slots_out,
        relaxed_constraints=[],
        improves_on_current=False,
    )

    b_multiset = get_crop_multiset(current_rotation)
    catalog = load_crops()

    # 3. Perfil ADAPTADA (Cambio Mínimo)
    # Generar rotaciones candidatas de ADAPTADA:
    # mismo nº de años y slots por año que B, difieren en <= 1 cultivo (por posición),
    # fechas reoptimizadas según §5.1, y distintas de B (rot.id != B.id).
    n_years_b = len(current_rotation.years)
    slots_per_year_b = [len(y.slots) for y in current_rotation.years]

    b_crop_tuples = [
        tuple(slot.crop_id for slot in y.slots) for y in current_rotation.years
    ]

    adaptada_pool: list[tuple[CandidateRotation, int, int]] = []
    # Tupla: (candidate, n_crop_changes, n_date_changes)

    def evaluate_or_get_candidate(rot: Rotation) -> CandidateRotation:
        rot_id = get_rotation_id(rot)
        if rot_id in candidates_by_id:
            return candidates_by_id[rot_id]
        soil = calc_soil_score(
            rot,
            hemisphere,
            soil_texture=soil_texture,
            eval_seasons=eval_seasons,
            w_runoff=w_runoff,
        )
        metrics, s_out, sl_out = evaluate_rotation(
            rot, slot_table, seasons, hemisphere, soil_score=soil
        )
        families = {
            get_crop(slot.crop_id).familia
            for year in rot.years
            for slot in year.slots
        }
        n_harvestable = len(
            {
                slot.crop_id
                for year in rot.years
                for slot in year.slots
                if get_crop(slot.crop_id).cosechable
            }
        )
        cand = CandidateRotation(
            rotation=rot,
            id=rot_id,
            metrics=metrics,
            seasons_out=s_out,
            slots_out=sl_out,
            crop_multiset=get_crop_multiset(rot),
            n_years=len(rot.years),
            n_families=len(families),
            n_harvestable_crops=n_harvestable,
        )
        candidates_by_id[rot_id] = cand
        return cand

    # Generación exhaustiva de combinaciones para C_A:
    # Paso A: 0 cambios de cultivo (solo cambio de fechas reoptimizadas)
    if all(ct in plans_by_crops for ct in b_crop_tuples):
        rot_same_crops = Rotation(
            years=[plans_by_crops[ct].rotation.years[0] for ct in b_crop_tuples]
        )
        if get_rotation_id(rot_same_crops) != actual_id:
            valid, _ = validate_rotation(rot_same_crops, hemisphere)
            if valid and slot_table is not None:
                cand = evaluate_or_get_candidate(rot_same_crops)
                n_date_changes = sum(
                    1
                    for y_idx in range(n_years_b)
                    for s_idx in range(slots_per_year_b[y_idx])
                    if rot_same_crops.years[y_idx].slots[s_idx].sow_date
                    != current_rotation.years[y_idx].slots[s_idx].sow_date
                )
                adaptada_pool.append((cand, 0, n_date_changes))

    # Paso B: exactamente 1 cambio de cultivo en alguna posición (target_y, target_s)
    for target_y in range(n_years_b):
        for target_s in range(slots_per_year_b[target_y]):
            original_crop = b_crop_tuples[target_y][target_s]
            for new_crop in sorted(catalog.keys()):
                if new_crop == original_crop:
                    continue

                new_year_tuple = list(b_crop_tuples[target_y])
                new_year_tuple[target_s] = new_crop
                new_year_tuple = tuple(new_year_tuple)

                target_crop_tuples = list(b_crop_tuples)
                target_crop_tuples[target_y] = new_year_tuple

                if not all(ct in plans_by_crops for ct in target_crop_tuples):
                    continue

                rot_1change = Rotation(
                    years=[
                        plans_by_crops[ct].rotation.years[0]
                        for ct in target_crop_tuples
                    ]
                )
                valid, _ = validate_rotation(rot_1change, hemisphere)
                if not valid or slot_table is None:
                    continue

                cand = evaluate_or_get_candidate(rot_1change)
                n_date_changes = sum(
                    1
                    for y_idx in range(n_years_b)
                    for s_idx in range(slots_per_year_b[y_idx])
                    if rot_1change.years[y_idx].slots[s_idx].sow_date
                    != current_rotation.years[y_idx].slots[s_idx].sow_date
                )
                adaptada_pool.append((cand, 1, n_date_changes))

    # Deduplicar adaptada_pool por candidate.id
    adaptada_pool_dedup: dict[str, tuple[CandidateRotation, int, int]] = {}
    for cand, n_crop, n_date in adaptada_pool:
        if cand.id not in adaptada_pool_dedup:
            adaptada_pool_dedup[cand.id] = (cand, n_crop, n_date)

    # Filtrado y selección de ADAPTADA
    filtered_adaptada: list[tuple[CandidateRotation, int, int]] = [
        item
        for item in adaptada_pool_dedup.values()
        if item[0].metrics.mean_productivity
        >= ADAPT_MIN_PROD * actual_metrics.mean_productivity
    ]

    adaptada_relaxed: list[str] = []
    if not filtered_adaptada:
        adaptada_candidates = list(adaptada_pool_dedup.values())
        if adaptada_candidates:
            adaptada_relaxed.append(
                "Se eliminó la restricción de productividad mínima (95% de la actual)."
            )
    else:
        adaptada_candidates = filtered_adaptada

    # Ranking de ADAPTADA: (bad_seasons asc, p10_index desc, mean_P desc, n_cambios asc, id asc)
    adaptada_candidates.sort(
        key=lambda item: (
            item[0].metrics.bad_seasons,
            -item[0].metrics.p10_index,
            -item[0].metrics.mean_productivity,
            item[1] + item[2],  # n_cambios
            item[0].id,
        )
    )

    selected_adaptada: SelectedProfile | None = None
    adaptada_multiset: tuple[tuple[str, int], ...] | None = None

    if adaptada_candidates:
        best_adapt_cand, _, _ = adaptada_candidates[0]
        improves_adapt = (
            best_adapt_cand.metrics.bad_seasons < actual_metrics.bad_seasons
        ) or (
            best_adapt_cand.metrics.mean_productivity
            > IMPROVE_PROD_RATIO * actual_metrics.mean_productivity
        )
        best_adapt_cand.metrics.productivity_vs_current = (
            PERCENT_BASE
            * best_adapt_cand.metrics.mean_productivity
            / actual_metrics.mean_productivity
        )
        selected_adaptada = SelectedProfile(
            profile="adaptada",
            rotation=best_adapt_cand.rotation,
            id=best_adapt_cand.id,
            metrics=best_adapt_cand.metrics,
            seasons_out=best_adapt_cand.seasons_out,
            slots_out=best_adapt_cand.slots_out,
            relaxed_constraints=adaptada_relaxed,
            improves_on_current=improves_adapt,
        )
        adaptada_multiset = best_adapt_cand.crop_multiset

    # 4. Perfil REGENERATIVA (Mejor suelo con pérdida acotada)
    c_r_pool = [
        c
        for c in candidate_rotations
        if c.crop_multiset != b_multiset
        and (adaptada_multiset is None or c.crop_multiset != adaptada_multiset)
    ]

    selected_regen: SelectedProfile | None = None
    regen_relaxed: list[str] = []

    # Escalera de relajación:
    # Paso 0: pérdida <= 20%, ganancia suelo >= 10, bad <= bad(B)
    step0 = [
        c
        for c in c_r_pool
        if c.metrics.soil.total
        >= actual_metrics.soil.total + REGEN_MIN_SOIL_GAIN
        and c.metrics.mean_productivity
        >= (1.0 - REGEN_MAX_LOSS) * actual_metrics.mean_productivity
        and c.metrics.bad_seasons <= actual_metrics.bad_seasons
    ]

    target_pool = step0
    if not target_pool:
        # Paso 1: pérdida <= 30%, ganancia suelo >= 10, bad <= bad(B)
        step1 = [
            c
            for c in c_r_pool
            if c.metrics.soil.total
            >= actual_metrics.soil.total + REGEN_MIN_SOIL_GAIN
            and c.metrics.mean_productivity
            >= (1.0 - REGEN_MAX_LOSS_RELAXED)
            * actual_metrics.mean_productivity
            and c.metrics.bad_seasons <= actual_metrics.bad_seasons
        ]
        if step1:
            target_pool = step1
            regen_relaxed.append(
                "Pérdida máxima de productividad aumentada de 20% a 30%"
            )
        else:
            # Paso 2: pérdida <= 30%, ganancia suelo >= 10, quitar bad <= bad(B)
            step2 = [
                c
                for c in c_r_pool
                if c.metrics.soil.total
                >= actual_metrics.soil.total + REGEN_MIN_SOIL_GAIN
                and c.metrics.mean_productivity
                >= (1.0 - REGEN_MAX_LOSS_RELAXED)
                * actual_metrics.mean_productivity
            ]
            if step2:
                target_pool = step2
                regen_relaxed.extend(
                    [
                        "Pérdida máxima de productividad aumentada de 20% a 30%",
                        "Se eliminó la restricción de campañas malas (<= actual).",
                    ]
                )
            else:
                # Paso 3: pérdida <= 30%, ganancia suelo >= 1, quitar bad <= bad(B)
                step3 = [
                    c
                    for c in c_r_pool
                    if c.metrics.soil.total
                    >= actual_metrics.soil.total + REGEN_MIN_SOIL_GAIN_RELAXED
                    and c.metrics.mean_productivity
                    >= (1.0 - REGEN_MAX_LOSS_RELAXED)
                    * actual_metrics.mean_productivity
                ]
                if step3:
                    target_pool = step3
                    regen_relaxed.extend(
                        [
                            "Pérdida máxima de productividad aumentada de 20% a 30%",
                            "Se eliminó la restricción de campañas malas (<= actual).",
                            "Ganancia mínima de puntaje de suelo reducida de 10 a 1 punto.",
                        ]
                    )

    if target_pool:
        # Elegir: (soil.total desc, mean_P desc, id asc)
        target_pool.sort(
            key=lambda c: (
                -c.metrics.soil.total,
                -c.metrics.mean_productivity,
                c.id,
            )
        )
        best_regen = target_pool[0]
        improves_regen = (
            best_regen.metrics.bad_seasons < actual_metrics.bad_seasons
        ) or (
            best_regen.metrics.mean_productivity
            > IMPROVE_PROD_RATIO * actual_metrics.mean_productivity
        )
        best_regen.metrics.productivity_vs_current = (
            PERCENT_BASE
            * best_regen.metrics.mean_productivity
            / actual_metrics.mean_productivity
        )
        selected_regen = SelectedProfile(
            profile="regenerativa",
            rotation=best_regen.rotation,
            id=best_regen.id,
            metrics=best_regen.metrics,
            seasons_out=best_regen.seasons_out,
            slots_out=best_regen.slots_out,
            relaxed_constraints=regen_relaxed,
            improves_on_current=improves_regen,
        )

    # Fallback si regenerativa quedó vacía y hay una 2ª mejor en adaptada
    if selected_regen is None and len(adaptada_candidates) > 1:
        second_adapt = adaptada_candidates[1][0]
        improves_second = (
            second_adapt.metrics.bad_seasons < actual_metrics.bad_seasons
        ) or (
            second_adapt.metrics.mean_productivity
            > IMPROVE_PROD_RATIO * actual_metrics.mean_productivity
        )
        second_adapt.metrics.productivity_vs_current = (
            PERCENT_BASE
            * second_adapt.metrics.mean_productivity
            / actual_metrics.mean_productivity
        )
        selected_regen = SelectedProfile(
            profile="regenerativa",
            rotation=second_adapt.rotation,
            id=second_adapt.id,
            metrics=second_adapt.metrics,
            seasons_out=second_adapt.seasons_out,
            slots_out=second_adapt.slots_out,
            relaxed_constraints=[
                "Se completó con la segunda mejor alternativa adaptada disponible."
            ],
            improves_on_current=improves_second,
        )

    # 5. Perfil DIVERSIFICADA (Opcional)
    selected_div: SelectedProfile | None = None
    if include_diversified:
        regen_multiset = (
            selected_regen.rotation if selected_regen is not None else None
        )
        regen_ms = (
            get_crop_multiset(selected_regen.rotation)
            if selected_regen is not None
            else None
        )

        c_d_pool = [
            c
            for c in candidate_rotations
            if c.n_years == DIVERSIFIED_CYCLE_YEARS
            and c.n_families >= DIVERSIFIED_MIN_FAMILIES
            and c.n_harvestable_crops >= DIVERSIFIED_MIN_CROPS
            and c.metrics.soil.total >= actual_metrics.soil.total
            and c.crop_multiset != b_multiset
            and (adaptada_multiset is None or c.crop_multiset != adaptada_multiset)
            and (regen_ms is None or c.crop_multiset != regen_ms)
        ]

        if c_d_pool:
            good_bad = [
                c
                for c in c_d_pool
                if c.metrics.bad_seasons <= actual_metrics.bad_seasons
            ]
            if good_bad:
                good_bad.sort(
                    key=lambda c: (
                        -c.metrics.mean_productivity,
                        c.metrics.bad_seasons,
                        c.id,
                    )
                )
                best_div = good_bad[0]
            else:
                c_d_pool.sort(
                    key=lambda c: (
                        c.metrics.bad_seasons,
                        -c.metrics.mean_productivity,
                        c.id,
                    )
                )
                best_div = c_d_pool[0]

            improves_div = (
                best_div.metrics.bad_seasons < actual_metrics.bad_seasons
            ) or (
                best_div.metrics.mean_productivity
                > IMPROVE_PROD_RATIO * actual_metrics.mean_productivity
            )
            best_div.metrics.productivity_vs_current = (
                PERCENT_BASE
                * best_div.metrics.mean_productivity
                / actual_metrics.mean_productivity
            )
            selected_div = SelectedProfile(
                profile="diversificada",
                rotation=best_div.rotation,
                id=best_div.id,
                metrics=best_div.metrics,
                seasons_out=best_div.seasons_out,
                slots_out=best_div.slots_out,
                relaxed_constraints=[],
                improves_on_current=improves_div,
            )

    result: dict[str, SelectedProfile] = {"actual": selected_actual}
    if selected_adaptada is not None:
        result["adaptada"] = selected_adaptada
    if selected_regen is not None:
        result["regenerativa"] = selected_regen
    if selected_div is not None:
        result["diversificada"] = selected_div

    return result
