"""PLAN §6 — Tests unitarios para selección de perfiles con relajación (A4–A6)."""

from pathlib import Path
from unittest.mock import MagicMock
import json
import numpy as np
import pytest

from app.config import (
    ADAPT_MIN_PROD,
    IMPROVE_PROD_RATIO,
    REGEN_MAX_LOSS,
    REGEN_MAX_LOSS_RELAXED,
    REGEN_MIN_SOIL_GAIN,
)
from app.engine.alternatives import (
    CandidateRotation,
    enumerate_annual_plans,
    enumerate_candidate_rotations,
    get_crop_multiset,
    get_rotation_id,
    select_profiles,
)
from app.engine.table import SlotTable
from app.nasa.power import parse_power_response
from app.schemas import (
    Rotation,
    RotationMetrics,
    RotationYear,
    SlotIn,
    SoilScore,
)


@pytest.fixture(scope="module")
def shared_slot_table():
    fixture_path = (
        Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pdata = parse_power_response(data)
    return SlotTable(
        weather_df=pdata.df,
        lat=-17.30,
        soil_texture="franco",
        seasons=list(range(1991, 2025)),
    )


@pytest.fixture(scope="module")
def baseline_rotation():
    return Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="05-01"),
                ]
            )
        ]
    )


def test_a4_distinct_multisets(shared_slot_table, baseline_rotation):
    """PLAN §6 A4 — Los multiconjuntos de cultivos de actual/regenerativa/adaptada cumplen distinción."""
    annual_plans = enumerate_annual_plans(shared_slot_table, hemisphere="S")
    candidates = enumerate_candidate_rotations(
        annual_plans, shared_slot_table, hemisphere="S"
    )

    profiles = select_profiles(
        current_rotation=baseline_rotation,
        candidate_rotations=candidates,
        slot_table=shared_slot_table,
        hemisphere="S",
        annual_plans=annual_plans,
    )

    assert "actual" in profiles
    assert "adaptada" in profiles
    assert "regenerativa" in profiles

    ms_actual = get_crop_multiset(profiles["actual"].rotation)
    ms_adaptada = get_crop_multiset(profiles["adaptada"].rotation)
    ms_regen = get_crop_multiset(profiles["regenerativa"].rotation)

    # REGENERATIVA debe tener multiconjunto distinto de actual y de adaptada
    assert ms_regen != ms_actual
    assert ms_regen != ms_adaptada


def test_a5_relaxation_ladder_synthetic():
    """PLAN §6 A5 — Con candidatas sintéticas se verifican los pasos 1, 2 y 3 de la relajación."""
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
    b_metrics = RotationMetrics(
        mean_index=0.75,
        p10_index=0.60,
        mean_productivity=1.0,
        productivity_vs_current=100.0,
        bad_seasons=4,
        n_seasons=20,
        bad_before=3,
        bad_recent=4,
        n_period=15,
        soil=SoilScore(
            total=40.0,
            nitrogen=40.0,
            diversity=40.0,
            erosion=40.0,
            organic_matter=40.0,
        ),
    )

    # Helper para construir CandidateRotation sintética
    def make_candidate(
        rot_id: str,
        crops: list[str],
        soil_total: float,
        mean_prod: float,
        bad_seasons: int,
    ) -> CandidateRotation:
        slots = [SlotIn(crop_id=c, sow_date="11-16") for c in crops]
        rot = Rotation(years=[RotationYear(slots=slots)])
        metrics = RotationMetrics(
            mean_index=0.8,
            p10_index=0.65,
            mean_productivity=mean_prod,
            productivity_vs_current=mean_prod * 100.0,
            bad_seasons=bad_seasons,
            n_seasons=20,
            bad_before=bad_seasons,
            bad_recent=bad_seasons,
            n_period=15,
            soil=SoilScore(
                total=soil_total,
                nitrogen=soil_total,
                diversity=soil_total,
                erosion=soil_total,
                organic_matter=soil_total,
            ),
        )
        return CandidateRotation(
            rotation=rot,
            id=rot_id,
            metrics=metrics,
            seasons_out=[],
            slots_out=[],
            crop_multiset=get_crop_multiset(rot),
            n_years=1,
            n_families=len(crops),
            n_harvestable_crops=len(crops),
        )

    # Caso 1: Pérdida del 25% (entre 20% y 30%), suelo +15 (>=10), bad=3 (<=4) -> Dispara Paso 1
    cand_step1 = make_candidate("maiz@11-16", ["maiz"], 55.0, 0.75, 3)
    res1 = select_profiles(
        current_rotation=rot_b,
        candidate_rotations=[cand_step1],
        current_metrics=b_metrics,
        annual_plans=[],
        hemisphere="S",
    )
    assert "regenerativa" in res1
    assert any(
        "Pérdida máxima" in r
        for r in res1["regenerativa"].relaxed_constraints
    )

    # Caso 2: Pérdida 25%, suelo +15 (>=10), pero bad=6 (>4) -> Falla Paso 1, dispara Paso 2
    cand_step2 = make_candidate("sorgo@11-16", ["sorgo"], 55.0, 0.75, 6)
    res2 = select_profiles(
        current_rotation=rot_b,
        candidate_rotations=[cand_step2],
        current_metrics=b_metrics,
        annual_plans=[],
        hemisphere="S",
    )
    assert "regenerativa" in res2
    assert any(
        "campañas malas" in r
        for r in res2["regenerativa"].relaxed_constraints
    )

    # Caso 3: Pérdida 25%, bad=6 (>4), suelo +5 (<10 pero >=1) -> Falla Paso 2, dispara Paso 3
    cand_step3 = make_candidate("girasol@11-16", ["girasol"], 45.0, 0.75, 6)
    res3 = select_profiles(
        current_rotation=rot_b,
        candidate_rotations=[cand_step3],
        current_metrics=b_metrics,
        annual_plans=[],
        hemisphere="S",
    )
    assert "regenerativa" in res3
    assert any(
        "puntaje de suelo" in r
        for r in res3["regenerativa"].relaxed_constraints
    )


def test_a6_adaptada_differs_in_at_most_one_crop(
    shared_slot_table, baseline_rotation
):
    """PLAN §6 A6 — ADAPTADA difiere de la actual B en a lo sumo 1 cultivo por posición."""
    annual_plans = enumerate_annual_plans(shared_slot_table, hemisphere="S")
    candidates = enumerate_candidate_rotations(
        annual_plans, shared_slot_table, hemisphere="S"
    )

    profiles = select_profiles(
        current_rotation=baseline_rotation,
        candidate_rotations=candidates,
        slot_table=shared_slot_table,
        hemisphere="S",
        annual_plans=annual_plans,
    )

    adaptada = profiles["adaptada"]
    rot_a = adaptada.rotation
    rot_b = baseline_rotation

    assert len(rot_a.years) == len(rot_b.years)
    for ya, yb in zip(rot_a.years, rot_b.years):
        assert len(ya.slots) == len(yb.slots)

    # Contar cuántas posiciones de cultivo cambiaron respecto a B
    crop_diffs = sum(
        1
        for ya, yb in zip(rot_a.years, rot_b.years)
        for sa, sb in zip(ya.slots, yb.slots)
        if sa.crop_id != sb.crop_id
    )
    assert crop_diffs <= 1
    assert adaptada.id != get_rotation_id(rot_b)
