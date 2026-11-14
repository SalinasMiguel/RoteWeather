"""PLAN §6 — Tests unitarios para enumeración de planes anuales y rotaciones candidatas (A1–A3)."""

from pathlib import Path
import json
import pytest

from app.config import DAYS_IN_YEAR, TURNAROUND_DAYS
from app.engine.alternatives import (
    enumerate_annual_plans,
    enumerate_candidate_rotations,
)
from app.engine.calendar import get_sow_offset, get_sowing_grid
from app.engine.rotation import validate_rotation
from app.engine.table import SlotTable
from app.nasa.power import parse_power_response


@pytest.fixture(scope="module")
def shared_slot_table():
    fixture_path = (
        Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pdata = parse_power_response(data)
    # Evaluamos con las campañas estándar del hemisferio sur
    return SlotTable(
        weather_df=pdata.df,
        lat=-17.30,
        soil_texture="franco",
        seasons=list(range(1991, 2025)),
    )


def test_a1_turnaround_constraint(shared_slot_table):
    """PLAN §6 A1 — Ningún plan anual ni rotación candidata viola TURNAROUND_DAYS."""
    plans = enumerate_annual_plans(shared_slot_table, hemisphere="S")
    assert len(plans) > 0

    # 1. Verificar cada plan anual
    for plan in plans:
        is_valid, msg = validate_rotation(plan.rotation, hemisphere="S")
        assert is_valid, f"Plan anual {plan.id} inválido: {msg}"

    # 2. Generar candidatas y verificar cada una
    candidates = enumerate_candidate_rotations(
        plans, shared_slot_table, hemisphere="S"
    )
    assert len(candidates) >= len(plans)

    for cand in candidates:
        is_valid, msg = validate_rotation(cand.rotation, hemisphere="S")
        assert is_valid, f"Candidata {cand.id} inválida: {msg}"


def test_a2_determinism(shared_slot_table):
    """PLAN §6 A2 — Determinismo: dos corridas producen exactamente los mismos IDs."""
    plans_run1 = enumerate_annual_plans(shared_slot_table, hemisphere="S")
    plans_run2 = enumerate_annual_plans(shared_slot_table, hemisphere="S")

    ids1 = [p.id for p in plans_run1]
    ids2 = [p.id for p in plans_run2]
    assert ids1 == ids2

    cands_run1 = enumerate_candidate_rotations(
        plans_run1, shared_slot_table, hemisphere="S"
    )
    cands_run2 = enumerate_candidate_rotations(
        plans_run2, shared_slot_table, hemisphere="S"
    )

    c_ids1 = [c.id for c in cands_run1]
    c_ids2 = [c.id for c in cands_run2]
    assert c_ids1 == c_ids2


def test_a3_single_date_combo_per_crop_tuple(shared_slot_table):
    """PLAN §6 A3 — Una sola combinación de fechas por tupla de cultivos (<= 12 + 13*13)."""
    plans = enumerate_annual_plans(shared_slot_table, hemisphere="S")
    crop_tuples = [p.crop_ids for p in plans]

    # No hay duplicados de tuplas de cultivos
    assert len(crop_tuples) == len(set(crop_tuples))

    # Cota superior según PLAN §5.1: como mucho 12 simples + 13*13 dobles
    assert len(plans) <= 12 + 13 * 13
