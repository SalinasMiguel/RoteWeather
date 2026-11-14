"""PLAN §6 — Tests unitarios para generación de fichas de rotación (F1–F3)."""

from pathlib import Path
import json
import re
import pytest

from app.engine.cards import (
    POWER_CANONICAL_PARAMS,
    generate_card,
)
from app.engine.slot import SlotSimulationResult
from app.schemas import (
    Claim,
    ClimateMetric,
    Evidence,
    Rotation,
    RotationCard,
    RotationMetrics,
    RotationYear,
    SeasonOut,
    SlotIn,
    SlotOut,
    SoilScore,
    Source,
)


@pytest.fixture
def baseline_data():
    rot_b = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="05-01"),
                ]
            )
        ]
    )
    b_soil = SoilScore(
        total=40.0,
        nitrogen=80.0,
        diversity=15.0,
        erosion=32.0,
        organic_matter=33.3,
    )
    b_metrics = RotationMetrics(
        mean_index=0.72,
        p10_index=0.55,
        mean_productivity=1.44,
        productivity_vs_current=100.0,
        bad_seasons=6,
        n_seasons=20,
        bad_before=4,
        bad_recent=6,
        n_period=15,
        soil=b_soil,
    )
    seasons = [
        SeasonOut(
            season=yr,
            label=f"{yr}/{(yr+1)%100:02d}",
            index=0.75 if yr != 2016 and yr != 2023 else 0.50,
            productivity=1.5 if yr != 2016 and yr != 2023 else 1.0,
            bad=(yr in [2016, 2023, 2015, 2017, 2019, 2021]),
            limiting="agua",
        )
        for yr in range(1991, 2025)
    ]
    slots_out = [
        [
            SlotOut(
                crop_id="soya",
                crop_name="Soya",
                family="Fabaceae",
                harvested=True,
                sow_date="11-16",
                sow_offset=138,
                stage_ends=[20, 50, 110, 135],
                sens_window=(45, 75),
                prev_mode="fallow",
                mean_yield=0.85,
                failures=3,
            ),
            SlotOut(
                crop_id="soya",
                crop_name="Soya",
                family="Fabaceae",
                harvested=True,
                sow_date="05-01",
                sow_offset=304,
                stage_ends=[20, 50, 110, 135],
                sens_window=(45, 75),
                prev_mode="fallow",
                mean_yield=0.59,
                failures=8,
            ),
        ]
    ]
    return rot_b, b_metrics, seasons, slots_out


def check_invariants_f1_f2_f3(card: RotationCard, profile_name: str = ""):
    """Verifica formalmente Invariantes F1, F2 y F3 sobre una ficha."""
    # F2: Conteos mínimos de claims y advertencia de resolución regional
    assert (
        len(card.why) >= 1
    ), f"Perfil {profile_name}: len(why) < 1 ({len(card.why)})"
    assert (
        len(card.benefits) >= 1
    ), f"Perfil {profile_name}: len(benefits) < 1 ({len(card.benefits)})"
    assert (
        len(card.risks) >= 2
    ), f"Perfil {profile_name}: len(risks) < 2 ({len(card.risks)})"
    assert any(
        "Resolución ≈50 km" in r.text for r in card.risks
    ), f"Perfil {profile_name}: falta advertencia mandatoria de resolución regional"

    all_claims = card.why + card.benefits + card.risks
    for claim in all_claims:
        # F1: Todo número del texto coincide con algún evidence[].value
        nums_in_text = re.findall(r"-?\d+(?:[.,]\d+)?", claim.text)
        ev_values_str = [str(e.value).replace(",", ".") for e in claim.evidence]

        for num in nums_in_text:
            num_clean = num.replace(",", ".")
            matched = False
            for ev_str in ev_values_str:
                if num_clean == ev_str:
                    matched = True
                    break
                try:
                    if float(num_clean) == float(ev_str):
                        matched = True
                        break
                except ValueError:
                    pass
            assert matched, (
                f"F1 violado en perfil {profile_name}: número '{num}' en texto '{claim.text}' "
                f"no coincide con ningún valor de evidencia: {ev_values_str}"
            )

        # F3: Parámetros canónicos de POWER o regla agronómica
        for ev in claim.evidence:
            src = ev.source
            if src.dataset == "Regla agronómica":
                assert (
                    src.parameters == []
                ), f"Regla agronómica debe tener parameters=[] en '{claim.text}'"
            else:
                assert set(src.parameters).issubset(
                    POWER_CANONICAL_PARAMS
                ), f"Parámetros inválidos en {src.parameters} para '{claim.text}'"


def test_f1_f2_f3_actual_card(baseline_data):
    """PLAN §6 F1, F2, F3 — Verificación sobre ficha ACTUAL."""
    rot_b, b_metrics, seasons, slots_out = baseline_data
    card = generate_card(
        profile="actual",
        rotation=rot_b,
        metrics=b_metrics,
        current_metrics=b_metrics,
        seasons_out=seasons,
        slots_out=slots_out,
        current_rotation=rot_b,
    )
    check_invariants_f1_f2_f3(card, "actual")


def test_f1_f2_f3_adaptada_card(baseline_data):
    """PLAN §6 F1, F2, F3 — Verificación sobre ficha ADAPTADA con cambio de fecha."""
    rot_b, b_metrics, seasons, slots_out = baseline_data
    rot_adapt = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="05-16"),
                ]
            )
        ]
    )
    adapt_metrics = RotationMetrics(
        mean_index=0.78,
        p10_index=0.62,
        mean_productivity=1.56,
        productivity_vs_current=108.3,
        bad_seasons=3,
        n_seasons=20,
        bad_before=3,
        bad_recent=3,
        n_period=15,
        soil=b_metrics.soil,
    )
    onset_metric = ClimateMetric(
        id="onset",
        label="Inicio de estación lluviosa",
        unit="día de campaña",
        before=68.0,
        recent=82.0,
        delta=14.0,
        p_value=0.03,
        significant=True,
        series=[],
        source=Source(
            dataset="NASA POWER (MERRA-2 / CERES SYN1deg)",
            parameters=["PRECTOTCORR"],
            period="1991–2024",
        ),
    )

    card = generate_card(
        profile="adaptada",
        rotation=rot_adapt,
        metrics=adapt_metrics,
        current_metrics=b_metrics,
        seasons_out=seasons,
        slots_out=slots_out,
        current_rotation=rot_b,
        climate_metrics=[onset_metric],
        improves_on_current=True,
    )
    check_invariants_f1_f2_f3(card, "adaptada")


def test_f1_f2_f3_regenerativa_card(baseline_data):
    """PLAN §6 F1, F2, F3 — Verificación sobre ficha REGENERATIVA con aumento de suelo y pérdida acotada."""
    rot_b, b_metrics, seasons, slots_out = baseline_data
    rot_regen = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="maiz", sow_date="11-16"),
                    SlotIn(crop_id="crotalaria", sow_date="04-01"),
                ]
            )
        ]
    )
    regen_soil = SoilScore(
        total=65.0,
        nitrogen=90.0,
        diversity=65.0,
        erosion=48.0,
        organic_matter=58.0,
    )
    regen_metrics = RotationMetrics(
        mean_index=0.74,
        p10_index=0.58,
        mean_productivity=1.35,
        productivity_vs_current=93.75,
        bad_seasons=4,
        n_seasons=20,
        bad_before=3,
        bad_recent=4,
        n_period=15,
        soil=regen_soil,
    )

    card = generate_card(
        profile="regenerativa",
        rotation=rot_regen,
        metrics=regen_metrics,
        current_metrics=b_metrics,
        seasons_out=seasons,
        slots_out=slots_out,
        current_rotation=rot_b,
        relaxed_constraints=[
            "Pérdida máxima de productividad aumentada de 20% a 30%"
        ],
        improves_on_current=True,
    )
    check_invariants_f1_f2_f3(card, "regenerativa")


def test_f1_f2_f3_fallback_benefits(baseline_data):
    """PLAN §6 F2 — Fallback de beneficios cuando no hay mejoras medibles."""
    rot_b, b_metrics, seasons, slots_out = baseline_data
    # Alternativa sin mejoras medibles
    worse_metrics = RotationMetrics(
        mean_index=0.65,
        p10_index=0.45,
        mean_productivity=1.30,
        productivity_vs_current=90.0,
        bad_seasons=8,
        n_seasons=20,
        bad_before=6,
        bad_recent=8,
        n_period=15,
        soil=b_metrics.soil,
    )
    card = generate_card(
        profile="adaptada",
        rotation=rot_b,
        metrics=worse_metrics,
        current_metrics=b_metrics,
        seasons_out=seasons,
        slots_out=slots_out,
        current_rotation=rot_b,
        improves_on_current=False,
    )
    check_invariants_f1_f2_f3(card, "adaptada_sin_mejora")
    assert any(
        "Sin beneficios medibles" in b.text for b in card.benefits
    ), "Falta claim de fallback en benefits"
