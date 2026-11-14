"""PLAN §2.5 y §4.9 — Generación determinista de fichas de rotación (RotationCard).

Invariantes estrictos:
- F1: Todo número en Claim.text coincide con algún evidence[].value con el mismo redondeo.
- F2: >= 1 claim en why, >= 1 en benefits (o fallback), >= 2 en risks (incluyendo advertencia de resolución).
- F3: Source.parameters es subconjunto de parámetros canónicos POWER o vacío para Regla agronómica.
"""

from collections import Counter
from typing import Any, Literal
import re

from app.config import (
    CARD_BAD_SEASON_THRESHOLD_PERCENT,
    CARD_BENEFIT_PROD_MIN,
    CARD_EROSION_DIFF_MIN,
    CARD_MAX_WORST_SEASONS,
    CARD_REGEN_LOSS_INITIAL_PERCENT,
    CARD_REGEN_LOSS_RELAXED_PERCENT,
    CARD_RESOLUTION_KM,
    CARD_RISK_PROD_MAX,
    MAX_SCORE_POINTS,
    N_BEFORE,
    N_RECENT,
)
from app.data.crops import get_crop
from app.schemas import (
    Claim,
    ClimateMetric,
    Evidence,
    Rotation,
    RotationCard,
    RotationMetrics,
    SeasonOut,
    SlotOut,
    Source,
)

POWER_DATASET: str = "NASA POWER (MERRA-2 / CERES SYN1deg)"
AGRONOMIC_RULE_DATASET: str = "Regla agronómica"

POWER_CANONICAL_PARAMS: set[str] = {
    "PRECTOTCORR",
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "RH2M",
    "ALLSKY_SFC_SW_DWN",
    "WS2M",
    "GWETTOP",
    "GWETROOT",
    "PS",
}

WATER_PARAMS: list[str] = [
    "PRECTOTCORR",
    "T2M_MAX",
    "T2M_MIN",
    "RH2M",
    "WS2M",
    "ALLSKY_SFC_SW_DWN",
    "PS",
]

MONTH_NAMES_ES: dict[int, str] = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def format_sow_date_human(sow_date_str: str) -> tuple[str, int]:
    """Formatea '11-16' como ('16 de noviembre', 16)."""
    parts = sow_date_str.split("-")
    m, d = int(parts[0]), int(parts[1])
    return f"{d} de {MONTH_NAMES_ES[m]}", d


def _make_source(
    parameters: list[str], period: str, is_rule: bool = False
) -> Source:
    if is_rule:
        return Source(
            dataset=AGRONOMIC_RULE_DATASET,
            parameters=[],
            period="constante",
        )
    return Source(
        dataset=POWER_DATASET,
        parameters=parameters,
        period=period,
    )


def generate_card(
    profile: Literal["actual", "adaptada", "regenerativa", "diversificada"],
    rotation: Rotation,
    metrics: RotationMetrics,
    current_metrics: RotationMetrics,
    seasons_out: list[SeasonOut],
    current_seasons_out: list[SeasonOut] | None = None,
    slots_out: list[list[SlotOut]] | None = None,
    current_slots_out: list[list[SlotOut]] | None = None,
    climate_metrics: list[ClimateMetric] | None = None,
    relaxed_constraints: list[str] | None = None,
    improves_on_current: bool = False,
    hemisphere: Literal["N", "S"] = "S",
    changes_vs_current: list[str] | None = None,
    current_rotation: Rotation | None = None,
    **kwargs: Any,
) -> RotationCard:
    """PLAN §2.5 y §4.9 — Genera la ficha de rotación con evidencia estricta F1, F2, F3."""
    if relaxed_constraints is None:
        relaxed_constraints = []

    # Determinar periodo de evaluación para etiquetas de fuente
    eval_seasons_out = (
        seasons_out[-metrics.n_seasons :]
        if len(seasons_out) >= metrics.n_seasons
        else seasons_out
    )
    if eval_seasons_out:
        eval_start = eval_seasons_out[0].season
        eval_end = eval_seasons_out[-1].season
        eval_period = f"campañas {eval_start} a {eval_end}"
    else:
        eval_period = f"últimas {metrics.n_seasons} campañas"

    why_claims: list[Claim] = []
    benefits_claims: list[Claim] = []
    risks_claims: list[Claim] = []

    # ----------------------------------------------------
    # 1. SECCIÓN WHY (Por qué)
    # ----------------------------------------------------
    if profile == "actual":
        # Template 1: Línea base siempre presente
        why_claims.append(
            Claim(
                text="Es la rotación que usás hoy: línea base de la comparación.",
                evidence=[
                    Evidence(
                        label="Campañas malas evaluadas",
                        value=metrics.bad_seasons,
                        unit=f"de {metrics.n_seasons}",
                        source=_make_source(WATER_PARAMS, eval_period),
                    )
                ],
            )
        )
        # Template 2: Cambio climático histórico
        if (
            metrics.bad_recent != metrics.bad_before
            and len(seasons_out) >= (N_BEFORE + N_RECENT)
        ):
            before_seasons = seasons_out[: metrics.n_period]
            recent_seasons = seasons_out[-metrics.n_period :]
            b_start, b_end = before_seasons[0].season, before_seasons[-1].season
            r_start, r_end = recent_seasons[0].season, recent_seasons[-1].season
            n = metrics.n_period

            text = (
                f"Con el clima de {b_start} a {b_end} tuvo {metrics.bad_before} campañas malas de {n}; "
                f"con el de {r_start} a {r_end}, {metrics.bad_recent} de {n}."
            )
            evs = [
                Evidence(
                    label="Inicio periodo anterior",
                    value=b_start,
                    unit="año",
                    source=_make_source(
                        WATER_PARAMS, f"campañas {b_start} a {b_end}"
                    ),
                ),
                Evidence(
                    label="Fin periodo anterior",
                    value=b_end,
                    unit="año",
                    source=_make_source(
                        WATER_PARAMS, f"campañas {b_start} a {b_end}"
                    ),
                ),
                Evidence(
                    label="Campañas malas en periodo anterior",
                    value=metrics.bad_before,
                    unit=f"de {n}",
                    source=_make_source(
                        WATER_PARAMS, f"campañas {b_start} a {b_end}"
                    ),
                ),
                Evidence(
                    label="Total campañas por periodo",
                    value=n,
                    unit="campañas",
                    source=_make_source(WATER_PARAMS, "constante", is_rule=True),
                ),
                Evidence(
                    label="Inicio periodo reciente",
                    value=r_start,
                    unit="año",
                    source=_make_source(
                        WATER_PARAMS, f"campañas {r_start} a {r_end}"
                    ),
                ),
                Evidence(
                    label="Fin periodo reciente",
                    value=r_end,
                    unit="año",
                    source=_make_source(
                        WATER_PARAMS, f"campañas {r_start} a {r_end}"
                    ),
                ),
                Evidence(
                    label="Campañas malas en periodo reciente",
                    value=metrics.bad_recent,
                    unit=f"de {n}",
                    source=_make_source(
                        WATER_PARAMS, f"campañas {r_start} a {r_end}"
                    ),
                ),
            ]
            why_claims.append(Claim(text=text, evidence=evs))

    else:
        # Perfiles adaptada / regenerativa / diversificada
        # Detectar cambios de fecha y sustituciones de cultivo
        sowing_date_changed = False
        onset_metric = None
        if climate_metrics:
            for cm in climate_metrics:
                if cm.id == "onset":
                    onset_metric = cm
                    break

        if (
            current_rotation is not None
            and len(rotation.years) == len(current_rotation.years)
        ):
            for y_idx in range(len(rotation.years)):
                y_new = rotation.years[y_idx]
                y_cur = current_rotation.years[y_idx]
                if len(y_new.slots) == len(y_cur.slots):
                    for s_idx in range(len(y_new.slots)):
                        s_new = y_new.slots[s_idx]
                        s_cur = y_cur.slots[s_idx]

                        # Template 3 & 4: Cambio de fecha de siembra con reducción de riesgo
                        if (
                            s_new.crop_id == s_cur.crop_id
                            and s_new.sow_date != s_cur.sow_date
                            and metrics.bad_seasons < current_metrics.bad_seasons
                            and not sowing_date_changed
                        ):
                            sowing_date_changed = True
                            c_name = get_crop(s_new.crop_id).nombre
                            fecha_str, day_new = format_sow_date_human(
                                s_new.sow_date
                            )
                            x = current_metrics.bad_seasons
                            y = metrics.bad_seasons
                            n = metrics.n_seasons

                            if onset_metric and onset_metric.significant:
                                a = int(round(onset_metric.before))
                                b = int(round(onset_metric.recent))
                                text = (
                                    f"El inicio de lluvias pasó del día {a} al día {b} de la campaña; "
                                    f"sembrar {c_name} el {fecha_str} baja las campañas malas de {x} a {y} de {n}."
                                )
                                evs = [
                                    Evidence(
                                        label="Inicio de lluvias periodo anterior",
                                        value=a,
                                        unit="día de campaña",
                                        source=_make_source(
                                            ["PRECTOTCORR"], "periodo anterior"
                                        ),
                                    ),
                                    Evidence(
                                        label="Inicio de lluvias periodo reciente",
                                        value=b,
                                        unit="día de campaña",
                                        source=_make_source(
                                            ["PRECTOTCORR"], "periodo reciente"
                                        ),
                                    ),
                                    Evidence(
                                        label="Día de siembra propuesto",
                                        value=day_new,
                                        unit="de mes",
                                        source=_make_source(
                                            [], "constante", is_rule=True
                                        ),
                                    ),
                                    Evidence(
                                        label="Campañas malas actuales",
                                        value=x,
                                        unit=f"de {n}",
                                        source=_make_source(
                                            ["PRECTOTCORR"], eval_period
                                        ),
                                    ),
                                    Evidence(
                                        label="Campañas malas propuestas",
                                        value=y,
                                        unit=f"de {n}",
                                        source=_make_source(
                                            ["PRECTOTCORR"], eval_period
                                        ),
                                    ),
                                    Evidence(
                                        label="Total campañas analizadas",
                                        value=n,
                                        unit="campañas",
                                        source=_make_source(
                                            ["PRECTOTCORR"], eval_period
                                        ),
                                    ),
                                ]
                                why_claims.append(Claim(text=text, evidence=evs))
                            else:
                                fecha0_str, day_cur = format_sow_date_human(
                                    s_cur.sow_date
                                )
                                text = (
                                    f"Sembrar {c_name} el {fecha_str} en vez del {fecha0_str} "
                                    f"baja las campañas malas de {x} a {y} de {n}."
                                )
                                evs = [
                                    Evidence(
                                        label="Día de siembra propuesto",
                                        value=day_new,
                                        unit="de mes",
                                        source=_make_source(
                                            [], "constante", is_rule=True
                                        ),
                                    ),
                                    Evidence(
                                        label="Día de siembra actual",
                                        value=day_cur,
                                        unit="de mes",
                                        source=_make_source(
                                            [], "constante", is_rule=True
                                        ),
                                    ),
                                    Evidence(
                                        label="Campañas malas actuales",
                                        value=x,
                                        unit=f"de {n}",
                                        source=_make_source(
                                            WATER_PARAMS, eval_period
                                        ),
                                    ),
                                    Evidence(
                                        label="Campañas malas propuestas",
                                        value=y,
                                        unit=f"de {n}",
                                        source=_make_source(
                                            WATER_PARAMS, eval_period
                                        ),
                                    ),
                                    Evidence(
                                        label="Total campañas analizadas",
                                        value=n,
                                        unit="campañas",
                                        source=_make_source(
                                            WATER_PARAMS, eval_period
                                        ),
                                    ),
                                ]
                                why_claims.append(Claim(text=text, evidence=evs))

                        # Template 5: Sustitución de cultivo
                        elif (
                            s_new.crop_id != s_cur.crop_id
                            and slots_out
                            and current_slots_out
                            and len(slots_out) > y_idx
                            and len(current_slots_out) > y_idx
                            and len(slots_out[y_idx]) > s_idx
                            and len(current_slots_out[y_idx]) > s_idx
                        ):
                            k0 = current_slots_out[y_idx][s_idx].failures
                            k1 = slots_out[y_idx][s_idx].failures
                            n = metrics.n_seasons
                            nuevo_nom = get_crop(s_new.crop_id).nombre
                            viejo_nom = get_crop(s_cur.crop_id).nombre

                            text = (
                                f"{nuevo_nom} reemplaza a {viejo_nom}: {viejo_nom} perdió más de la mitad "
                                f"del rendimiento en {k0} de {n} campañas; {nuevo_nom} en {k1}."
                            )
                            evs = [
                                Evidence(
                                    label=f"Campañas con falla de {viejo_nom}",
                                    value=k0,
                                    unit=f"de {n}",
                                    source=_make_source(
                                        WATER_PARAMS, eval_period
                                    ),
                                ),
                                Evidence(
                                    label="Total campañas evaluadas",
                                    value=n,
                                    unit="campañas",
                                    source=_make_source(
                                        WATER_PARAMS, eval_period
                                    ),
                                ),
                                Evidence(
                                    label=f"Campañas con falla de {nuevo_nom}",
                                    value=k1,
                                    unit=f"de {n}",
                                    source=_make_source(
                                        WATER_PARAMS, eval_period
                                    ),
                                ),
                            ]
                            why_claims.append(Claim(text=text, evidence=evs))

        # Template 6: Regenerativa puntaje de suelo
        if profile == "regenerativa":
            s0 = int(round(current_metrics.soil.total))
            s1 = int(round(metrics.soil.total))
            text = f"Sube el puntaje de suelo de {s0} a {s1} sobre 100."
            evs = [
                Evidence(
                    label="Puntaje de suelo actual",
                    value=s0,
                    unit="sobre 100",
                    source=_make_source(["PRECTOTCORR"], eval_period),
                ),
                Evidence(
                    label="Puntaje de suelo propuesto",
                    value=s1,
                    unit="sobre 100",
                    source=_make_source(["PRECTOTCORR"], eval_period),
                ),
                Evidence(
                    label="Puntaje máximo de escala",
                    value=MAX_SCORE_POINTS,
                    unit="puntos",
                    source=_make_source([], "constante", is_rule=True),
                ),
            ]
            why_claims.append(Claim(text=text, evidence=evs))

        # Fallback why si quedó vacío
        if not why_claims:
            why_claims.append(
                Claim(
                    text="Rotación optimizada para reducir riesgo climático y consumo hídrico.",
                    evidence=[
                        Evidence(
                            label="Campañas malas evaluadas",
                            value=metrics.bad_seasons,
                            unit=f"de {metrics.n_seasons}",
                            source=_make_source(WATER_PARAMS, eval_period),
                        )
                    ],
                )
            )

    # ----------------------------------------------------
    # 2. SECCIÓN BENEFITS (Beneficios)
    # ----------------------------------------------------
    if profile != "actual":
        # Benefit 1: Reducción de campañas malas
        if metrics.bad_seasons < current_metrics.bad_seasons:
            d = current_metrics.bad_seasons - metrics.bad_seasons
            n = metrics.n_seasons
            text = f"{d} campañas malas menos de {n}."
            evs = [
                Evidence(
                    label="Reducción de campañas malas",
                    value=d,
                    unit="campañas",
                    source=_make_source(WATER_PARAMS, eval_period),
                ),
                Evidence(
                    label="Total campañas evaluadas",
                    value=n,
                    unit="campañas",
                    source=_make_source(WATER_PARAMS, eval_period),
                ),
            ]
            benefits_claims.append(Claim(text=text, evidence=evs))

        # Benefit 2: Productividad > 102%
        if metrics.productivity_vs_current > CARD_BENEFIT_PROD_MIN:
            v = int(round(metrics.productivity_vs_current))
            text = f"Productividad {v}% respecto de la actual."
            evs = [
                Evidence(
                    label="Productividad relativa",
                    value=v,
                    unit="%",
                    source=_make_source(WATER_PARAMS, eval_period),
                )
            ]
            benefits_claims.append(Claim(text=text, evidence=evs))

        # Benefit 3: Erosión sube >= 5
        if (
            metrics.soil.erosion - current_metrics.soil.erosion
            >= CARD_EROSION_DIFF_MIN
        ):
            e = int(round(metrics.soil.erosion))
            e0 = int(round(current_metrics.soil.erosion))
            text = (
                f"El {e}% de la escorrentía de lluvias intensas cae con el suelo cubierto "
                f"(antes {e0}%)."
            )
            evs = [
                Evidence(
                    label="Protección contra erosión propuesta",
                    value=e,
                    unit="%",
                    source=_make_source(["PRECTOTCORR"], eval_period),
                ),
                Evidence(
                    label="Protección contra erosión actual",
                    value=e0,
                    unit="%",
                    source=_make_source(["PRECTOTCORR"], eval_period),
                ),
            ]
            benefits_claims.append(Claim(text=text, evidence=evs))

        # Benefit 4: Diversidad botánica sube
        cand_fams = {
            get_crop(slot.crop_id).familia
            for y in rotation.years
            for slot in y.slots
        }
        if current_rotation is not None:
            cur_fams = {
                get_crop(slot.crop_id).familia
                for y in current_rotation.years
                for slot in y.slots
            }
        else:
            cur_fams = set()

        if len(cand_fams) > len(cur_fams) and len(cur_fams) > 0:
            f = len(cand_fams)
            f0 = len(cur_fams)
            text = f"{f} familias botánicas en el ciclo (antes {f0})."
            evs = [
                Evidence(
                    label="Familias botánicas en rotación propuesta",
                    value=f,
                    unit="familias",
                    source=_make_source([], "constante", is_rule=True),
                ),
                Evidence(
                    label="Familias botánicas en rotación actual",
                    value=f0,
                    unit="familias",
                    source=_make_source([], "constante", is_rule=True),
                ),
            ]
            benefits_claims.append(Claim(text=text, evidence=evs))

    # Fallback beneficios si quedó vacío (garantiza F2: >= 1 claim)
    if not benefits_claims:
        if profile == "actual":
            benefits_claims.append(
                Claim(
                    text="Línea base sin cambios agronómicos.",
                    evidence=[
                        Evidence(
                            label="Productividad base",
                            value=MAX_SCORE_POINTS,
                            unit="%",
                            source=_make_source([], "constante", is_rule=True),
                        )
                    ],
                )
            )
        else:
            benefits_claims.append(
                Claim(
                    text="Sin beneficios medibles respecto de la rotación actual.",
                    evidence=[
                        Evidence(
                            label="Productividad relativa",
                            value=int(round(metrics.productivity_vs_current)),
                            unit="%",
                            source=_make_source(WATER_PARAMS, eval_period),
                        )
                    ],
                )
            )

    # ----------------------------------------------------
    # 3. SECCIÓN RISKS (Riesgos)
    # ----------------------------------------------------
    # Risk 1: Campaña mala y peores campañas (Mandatorio, siempre presente)
    threshold_bad = CARD_BAD_SEASON_THRESHOLD_PERCENT
    bad_count = metrics.bad_seasons
    n_total = metrics.n_seasons

    bad_seasons_eval = [s for s in eval_seasons_out if s.bad]
    bad_seasons_eval.sort(key=lambda s: (s.index, s.season))
    worst_seasons = bad_seasons_eval[:CARD_MAX_WORST_SEASONS]
    worst_years = [s.season for s in worst_seasons]

    if bad_count == 0 or not worst_years:
        risk1_text = (
            f"Campaña mala (menos del {threshold_bad}% del potencial) en 0 de {n_total}: ninguna registrada."
        )
        risk1_evs = [
            Evidence(
                label="Umbral de campaña mala",
                value=threshold_bad,
                unit="%",
                source=_make_source([], "constante", is_rule=True),
            ),
            Evidence(
                label="Campañas malas",
                value=0,
                unit=f"de {n_total}",
                source=_make_source(WATER_PARAMS, eval_period),
            ),
            Evidence(
                label="Total campañas evaluadas",
                value=n_total,
                unit="campañas",
                source=_make_source(WATER_PARAMS, eval_period),
            ),
        ]
    else:
        worst_str = ", ".join(str(yr) for yr in worst_years)
        risk1_text = (
            f"Campaña mala (menos del {threshold_bad}% del potencial) en {bad_count} de {n_total}: {worst_str}."
        )
        risk1_evs = [
            Evidence(
                label="Umbral de campaña mala",
                value=threshold_bad,
                unit="%",
                source=_make_source([], "constante", is_rule=True),
            ),
            Evidence(
                label="Campañas malas",
                value=bad_count,
                unit=f"de {n_total}",
                source=_make_source(WATER_PARAMS, eval_period),
            ),
            Evidence(
                label="Total campañas evaluadas",
                value=n_total,
                unit="campañas",
                source=_make_source(WATER_PARAMS, eval_period),
            ),
        ]
        for yr in worst_years:
            risk1_evs.append(
                Evidence(
                    label=f"Peor campaña registrada ({yr})",
                    value=yr,
                    unit="año",
                    source=_make_source(WATER_PARAMS, str(yr)),
                )
            )
    risks_claims.append(Claim(text=risk1_text, evidence=risk1_evs))

    # Risk 2: Factor limitante dominante
    factor_counts = Counter(
        s.limiting for s in eval_seasons_out if s.limiting != "ninguno"
    )
    if factor_counts:
        dominant_factor, k_count = factor_counts.most_common(1)[0]
        n_eval_count = len(eval_seasons_out)

        if dominant_factor == "calor":
            f_params = ["T2M_MAX"]
        elif dominant_factor == "helada":
            f_params = ["T2M_MIN"]
        elif dominant_factor == "temperatura":
            f_params = ["T2M_MAX", "T2M_MIN"]
        else:
            f_params = WATER_PARAMS

        text = (
            f"Factor limitante más frecuente: {dominant_factor} "
            f"({k_count} de {n_eval_count} campañas)."
        )
        evs = [
            Evidence(
                label=f"Frecuencia factor {dominant_factor}",
                value=k_count,
                unit=f"de {n_eval_count}",
                source=_make_source(f_params, eval_period),
            ),
            Evidence(
                label="Total campañas evaluadas",
                value=n_eval_count,
                unit="campañas",
                source=_make_source(f_params, eval_period),
            ),
        ]
        risks_claims.append(Claim(text=text, evidence=evs))

    # Risk 3: Pérdida de productividad (< 98%)
    if metrics.productivity_vs_current < CARD_RISK_PROD_MAX:
        v = int(round(metrics.productivity_vs_current))
        text = f"Produce {v}% de lo que rinde la actual."
        evs = [
            Evidence(
                label="Productividad relativa",
                value=v,
                unit="%",
                source=_make_source(WATER_PARAMS, eval_period),
            )
        ]
        risks_claims.append(Claim(text=text, evidence=evs))

    # Risk 4: Repetición de familias botánicas
    cycle_slots = [s for y in rotation.years for s in y.slots]
    m_slots = len(cycle_slots)
    if m_slots == 1:
        repeat_count = 1
    else:
        repeat_count = sum(
            1
            for idx in range(m_slots)
            if get_crop(cycle_slots[idx].crop_id).familia
            == get_crop(cycle_slots[(idx + 1) % m_slots].crop_id).familia
        )

    if repeat_count > 0:
        text = (
            f"Repite familia botánica en {repeat_count} de {m_slots} transiciones."
        )
        evs = [
            Evidence(
                label="Transiciones con misma familia",
                value=repeat_count,
                unit=f"de {m_slots}",
                source=_make_source([], "constante", is_rule=True),
            ),
            Evidence(
                label="Total transiciones del ciclo",
                value=m_slots,
                unit="transiciones",
                source=_make_source([], "constante", is_rule=True),
            ),
        ]
        risks_claims.append(Claim(text=text, evidence=evs))

    # Risk 5: Restricciones relajadas (si hubo relajación de pérdida)
    if any("Pérdida máxima" in r for r in relaxed_constraints):
        x = CARD_REGEN_LOSS_INITIAL_PERCENT
        y = CARD_REGEN_LOSS_RELAXED_PERCENT
        text = (
            f"No hubo alternativa dentro del límite de pérdida del {x}%; "
            f"se aceptó hasta {y}%."
        )
        evs = [
            Evidence(
                label="Límite inicial de pérdida",
                value=x,
                unit="%",
                source=_make_source([], "constante", is_rule=True),
            ),
            Evidence(
                label="Límite relajado de pérdida",
                value=y,
                unit="%",
                source=_make_source([], "constante", is_rule=True),
            ),
        ]
        risks_claims.append(Claim(text=text, evidence=evs))

    # Risk 6: No mejora respecto a la actual
    if profile != "actual" and not improves_on_current:
        text = (
            "Con cambios mínimos no encontramos una opción mejor que tu rotación actual."
        )
        evs = [
            Evidence(
                label="Campañas malas evaluadas",
                value=metrics.bad_seasons,
                unit=f"de {metrics.n_seasons}",
                source=_make_source(WATER_PARAMS, eval_period),
            )
        ]
        risks_claims.append(Claim(text=text, evidence=evs))

    # Risk 7: Advertencia de resolución regional (Mandatorio, 1 por ficha)
    risks_claims.append(
        Claim(
            text=f"Resolución ≈{CARD_RESOLUTION_KM} km: es el clima regional, no el de tu parcela.",
            evidence=[
                Evidence(
                    label="Resolución espacial del reanálisis",
                    value=CARD_RESOLUTION_KM,
                    unit="km",
                    source=_make_source(["PRECTOTCORR"], "constante"),
                )
            ],
        )
    )

    # Título según perfil
    titles = {
        "actual": "Rotación actual (línea base)",
        "adaptada": "Rotación adaptada (cambio mínimo)",
        "regenerativa": "Rotación regenerativa (salud de suelo)",
        "diversificada": "Rotación diversificada",
    }
    title = titles.get(profile, f"Rotación {profile}")

    # Changes vs current
    if changes_vs_current is None:
        if profile == "actual":
            changes_vs_current = ["Sin cambios respecto de tu rotación actual."]
        else:
            changes_vs_current = []
            if current_rotation is not None:
                for y_idx in range(
                    min(len(rotation.years), len(current_rotation.years))
                ):
                    y_new = rotation.years[y_idx]
                    y_cur = current_rotation.years[y_idx]
                    for s_idx in range(min(len(y_new.slots), len(y_cur.slots))):
                        s_new = y_new.slots[s_idx]
                        s_cur = y_cur.slots[s_idx]
                        c_name_new = get_crop(s_new.crop_id).nombre
                        c_name_cur = get_crop(s_cur.crop_id).nombre
                        if s_new.crop_id != s_cur.crop_id:
                            changes_vs_current.append(
                                f"Reemplazo de {c_name_cur} por {c_name_new} en año {y_idx + 1}."
                            )
                        elif s_new.sow_date != s_cur.sow_date:
                            f_human, _ = format_sow_date_human(s_new.sow_date)
                            changes_vs_current.append(
                                f"Ajuste de fecha de siembra de {c_name_new} al {f_human} en año {y_idx + 1}."
                            )
            if not changes_vs_current:
                changes_vs_current.append(
                    f"Configuración optimizada según perfil {profile}."
                )

    return RotationCard(
        profile=profile,
        title=title,
        why=why_claims,
        benefits=benefits_claims,
        risks=risks_claims,
        changes_vs_current=changes_vs_current,
        relaxed_constraints=relaxed_constraints,
        improves_on_current=improves_on_current,
    )
