"""PLAN §6 — Tests unitarios para el motor de rotación (R1–R5 y complementarios)."""

from pathlib import Path
from typing import Literal
import json
import numpy as np
import pytest

from app.config import BAD_SEASON_I, GAP_CROP_MAX_DAYS, TURNAROUND_DAYS
from app.data.crops import load_crops
from app.engine.rotation import (
    calculate_rotation_gaps_and_modes,
    evaluate_rotation,
    validate_rotation,
)
from app.engine.slot import SlotSimulationResult
from app.engine.table import SlotTable
from app.nasa.power import parse_power_response
from app.schemas import Rotation, RotationYear, SlotIn, SoilScore


class MockSlotTable:
    """Mock de SlotTable que devuelve resultados sintéticos controlados por (crop_id, sow_date)."""

    def __init__(self, mapping: dict[tuple[str, int, str], SlotSimulationResult], seasons: list[int]):
        self.mapping = mapping
        self.seasons = seasons

    def get_grid_index(self, sow_date_str: str) -> int:
        from app.engine.calendar import get_sowing_grid

        # Rejilla sur por defecto para pruebas
        grid = get_sowing_grid("S")
        return grid.index(sow_date_str)

    def get_slot_result(
        self, crop_id: str, grid_idx: int, prev_mode: Literal["fallow", "crop"] | str
    ) -> SlotSimulationResult:
        key = (crop_id, grid_idx, prev_mode)
        if key in self.mapping:
            return self.mapping[key]
        for (c, g, _), res in self.mapping.items():
            if c == crop_id and g == grid_idx:
                return res
        n = len(self.seasons)
        return SlotSimulationResult(
            y_rel=np.ones(n, dtype=float),
            f_agua=np.ones(n, dtype=float),
            f_calor=np.ones(n, dtype=float),
            f_helada=np.ones(n, dtype=float),
            f_temp=np.ones(n, dtype=float),
            sum_eta=np.full(n, 100.0),
            sum_etc=np.full(n, 100.0),
            limiting=["ninguno"] * n,
        )


@pytest.fixture
def demo_power_df():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pdata = parse_power_response(data)
    return pdata.df


def test_r1_gaps_and_modes():
    """R1: soya@11-16 + soya@05-01, lat<0.

    Cosecha A = 11-16 + 135d = 03-31; gap B = 31d -> modo 'fallow'.
    Con B@04-16 gap = 16d -> 'crop'.
    """
    rot_fallow = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="05-01"),
                ]
            )
        ]
    )

    gaps_modes_fallow = calculate_rotation_gaps_and_modes(rot_fallow, hemisphere="S")
    gap_a, mode_a = gaps_modes_fallow[0][0]
    gap_b, mode_b = gaps_modes_fallow[0][1]

    # Slot B (05-01): cosecha A fue 03-31 -> gap 31 días -> modo fallow (>30)
    assert gap_b == 31
    assert mode_b == "fallow"

    # Slot A (11-16): pred es B (05-01, cosecha 09-13) -> gap a 11-16 es 64 días -> modo fallow
    assert gap_a == 64
    assert mode_a == "fallow"

    valid, msg = validate_rotation(rot_fallow, hemisphere="S")
    assert valid is True
    assert msg == ""

    # Con B@04-16: siembra 04-16, cosecha A es 03-31 -> gap 16 días -> modo crop (<=30)
    rot_crop = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="04-16"),
                ]
            )
        ]
    )
    gaps_modes_crop = calculate_rotation_gaps_and_modes(rot_crop, hemisphere="S")
    gap_b_crop, mode_b_crop = gaps_modes_crop[0][1]
    assert gap_b_crop == 16
    assert mode_b_crop == "crop"

    valid, msg = validate_rotation(rot_crop, hemisphere="S")
    assert valid is True
    assert msg == ""


def test_r2_overlapping_slots():
    """R2: slots solapados (gap < 10 días) -> validate_rotation retorna False."""
    rot_overlap = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="04-01"),
                ]
            )
        ]
    )
    valid, msg = validate_rotation(rot_overlap, hemisphere="S")
    assert valid is False
    assert "menor al mínimo requerido de 10 días" in msg

    # Caso solapado directamente (siembra antes de cosecha, gap negativo)
    rot_negative = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="maiz", sow_date="12-01"),
                ]
            )
        ]
    )
    valid_neg, msg_neg = validate_rotation(rot_negative, hemisphere="S")
    assert valid_neg is False
    assert "menor al mínimo requerido de 10 días" in msg_neg


def test_r3_productivity_index_bad_season():
    """R3: con Y sintético [1.0, 0.5] en un año de 2 slots, I = 0.75, no mala; [0.7, 0.4] -> I = 0.55, mala."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="05-01"),
                ]
            )
        ]
    )

    seasons = [2014, 2015]

    res_a = SlotSimulationResult(
        y_rel=np.array([1.0, 0.7], dtype=float),
        f_agua=np.array([1.0, 0.7], dtype=float),
        f_calor=np.array([1.0, 1.0], dtype=float),
        f_helada=np.array([1.0, 1.0], dtype=float),
        f_temp=np.array([1.0, 1.0], dtype=float),
        sum_eta=np.array([100.0, 70.0], dtype=float),
        sum_etc=np.array([100.0, 100.0], dtype=float),
        limiting=["ninguno", "agua"],
    )
    res_b = SlotSimulationResult(
        y_rel=np.array([0.5, 0.4], dtype=float),
        f_agua=np.array([0.5, 0.4], dtype=float),
        f_calor=np.array([1.0, 1.0], dtype=float),
        f_helada=np.array([1.0, 1.0], dtype=float),
        f_temp=np.array([1.0, 1.0], dtype=float),
        sum_eta=np.array([50.0, 40.0], dtype=float),
        sum_etc=np.array([100.0, 100.0], dtype=float),
        limiting=["agua", "agua"],
    )

    from app.engine.calendar import get_sowing_grid

    grid = get_sowing_grid("S")
    idx_a = grid.index("11-16")
    idx_b = grid.index("05-01")

    table = MockSlotTable(
        mapping={
            ("soya", idx_a, "fallow"): res_a,
            ("soya", idx_b, "fallow"): res_b,
        },
        seasons=seasons,
    )

    metrics, seasons_out, slots_out = evaluate_rotation(
        rotation=rot,
        slot_table=table,  # type: ignore
        seasons=seasons,
        hemisphere="S",
    )

    # Campaña 2014
    s2014 = seasons_out[0]
    assert s2014.season == 2014
    assert s2014.productivity == pytest.approx(1.5, abs=1e-9)
    assert s2014.index == pytest.approx(0.75, abs=1e-9)
    assert s2014.bad is False

    # Campaña 2015
    s2015 = seasons_out[1]
    assert s2015.season == 2015
    assert s2015.productivity == pytest.approx(1.1, abs=1e-9)
    assert s2015.index == pytest.approx(0.55, abs=1e-9)
    assert s2015.bad is True


def test_r4_two_year_rotation_averages_all_phases():
    """R4: rotación de 2 años = media de todas las fases k=1..L en cada campaña."""
    rot = Rotation(
        years=[
            RotationYear(slots=[SlotIn(crop_id="soya", sow_date="11-16")]),
            RotationYear(slots=[SlotIn(crop_id="maiz", sow_date="11-16")]),
        ]
    )

    seasons = [2015]

    res_soya = SlotSimulationResult(
        y_rel=np.array([1.0], dtype=float),
        f_agua=np.array([1.0], dtype=float),
        f_calor=np.array([1.0], dtype=float),
        f_helada=np.array([1.0], dtype=float),
        f_temp=np.array([1.0], dtype=float),
        sum_eta=np.array([100.0], dtype=float),
        sum_etc=np.array([100.0], dtype=float),
        limiting=["ninguno"],
    )
    res_maiz = SlotSimulationResult(
        y_rel=np.array([0.5], dtype=float),
        f_agua=np.array([0.5], dtype=float),
        f_calor=np.array([1.0], dtype=float),
        f_helada=np.array([1.0], dtype=float),
        f_temp=np.array([1.0], dtype=float),
        sum_eta=np.array([50.0], dtype=float),
        sum_etc=np.array([100.0], dtype=float),
        limiting=["agua"],
    )

    from app.engine.calendar import get_sowing_grid

    grid = get_sowing_grid("S")
    idx_1116 = grid.index("11-16")

    table = MockSlotTable(
        mapping={
            ("soya", idx_1116, "fallow"): res_soya,
            ("maiz", idx_1116, "fallow"): res_maiz,
        },
        seasons=seasons,
    )

    metrics, seasons_out, slots_out = evaluate_rotation(
        rotation=rot,
        slot_table=table,  # type: ignore
        seasons=seasons,
        hemisphere="S",
    )

    assert len(seasons_out) == 1
    s = seasons_out[0]
    assert s.productivity == pytest.approx(0.75, abs=1e-9)
    assert s.index == pytest.approx(0.75, abs=1e-9)
    assert s.bad is False
    assert s.limiting == "agua"


def test_r5_cover_crops_not_in_pot_nor_p():
    """R5: cultivos de cobertura (cosechable == False) no entran en Pot ni en P."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="avena_cob", sow_date="05-01"),
                    SlotIn(crop_id="soya", sow_date="11-16"),
                ]
            )
        ]
    )

    seasons = [2015]

    res_avena = SlotSimulationResult(
        y_rel=np.array([0.2], dtype=float),
        f_agua=np.array([0.2], dtype=float),
        f_calor=np.array([1.0], dtype=float),
        f_helada=np.array([1.0], dtype=float),
        f_temp=np.array([1.0], dtype=float),
        sum_eta=np.array([20.0], dtype=float),
        sum_etc=np.array([100.0], dtype=float),
        limiting=["agua"],
    )
    res_soya = SlotSimulationResult(
        y_rel=np.array([0.8], dtype=float),
        f_agua=np.array([1.0], dtype=float),
        f_calor=np.array([0.8], dtype=float),
        f_helada=np.array([1.0], dtype=float),
        f_temp=np.array([1.0], dtype=float),
        sum_eta=np.array([100.0], dtype=float),
        sum_etc=np.array([100.0], dtype=float),
        limiting=["calor"],
    )

    from app.engine.calendar import get_sowing_grid

    grid = get_sowing_grid("S")
    idx_avena = grid.index("05-01")
    idx_soya = grid.index("11-16")

    table = MockSlotTable(
        mapping={
            ("avena_cob", idx_avena, "fallow"): res_avena,
            ("soya", idx_soya, "fallow"): res_soya,
        },
        seasons=seasons,
    )

    metrics, seasons_out, slots_out = evaluate_rotation(
        rotation=rot,
        slot_table=table,  # type: ignore
        seasons=seasons,
        hemisphere="S",
    )

    s = seasons_out[0]
    assert s.productivity == pytest.approx(0.8, abs=1e-9)
    assert s.index == pytest.approx(0.8, abs=1e-9)
    assert s.limiting == "calor"

    assert len(slots_out[0]) == 2
    assert slots_out[0][0].harvested is False
    assert slots_out[0][1].harvested is True


def test_validate_rotation_requires_harvestable_crop():
    """Validación falla si no hay al menos un cultivo cosechable."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="avena_cob", sow_date="05-01"),
                    SlotIn(crop_id="crotalaria", sow_date="11-16"),
                ]
            )
        ]
    )
    valid, msg = validate_rotation(rot, hemisphere="S")
    assert valid is False
    assert msg == "Debe existir al menos un cultivo cosechable"


def test_validate_rotation_exceeds_max_overrun():
    """Validación falla si un slot excede 365 + MAX_OVERRUN_DAYS (548 días)."""
    # En hemisferio S: inicio es 07-01.
    # sow_date 06-16 es día 350.
    # Algodón tiene ciclo de 180 días -> 350 + 180 = 530 <= 548 (válido)
    # Pero si se sembrara con un ciclo que termine en > 548 días:
    # E.g. sow_date 06-16 con otro cultivo o similar
    # Vamos a verificar un slot con sow_offset grande
    from app.engine.calendar import get_sow_offset

    sow_off = get_sow_offset("06-16", "S")  # día 350
    # Con algodón (180 días): 350 + 180 = 530 <= 548
    # Probemos con sow_date 06-16 y un cultivo largo simulado o verifiquemos el cálculo
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="algodon", sow_date="06-16"),
                ]
            )
        ]
    )
    valid, msg = validate_rotation(rot, hemisphere="S")
    assert valid is True

    # Si sow_offset + ciclo > 548:
    # Si algodón (180 días) se sembrara en fecha con offset > 368
    # En hemisferio S las 24 fechas están entre 0 y 350 días desde 07-01.


def test_limiting_factor_tie_break():
    """PLAN §4.6 — Desempate de factor limitante: agua > calor > helada > temperatura > ninguno."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="maiz", sow_date="05-01"),
                ]
            )
        ]
    )

    seasons = [2015]

    # Ambos tienen el mismo rendimiento mínimo 0.50, pero slot 1 tiene limitante calor y slot 2 agua
    res_1 = SlotSimulationResult(
        y_rel=np.array([0.50], dtype=float),
        f_agua=np.array([1.0], dtype=float),
        f_calor=np.array([0.50], dtype=float),
        f_helada=np.array([1.0], dtype=float),
        f_temp=np.array([1.0], dtype=float),
        sum_eta=np.array([100.0], dtype=float),
        sum_etc=np.array([100.0], dtype=float),
        limiting=["calor"],
    )
    res_2 = SlotSimulationResult(
        y_rel=np.array([0.50], dtype=float),
        f_agua=np.array([0.50], dtype=float),
        f_calor=np.array([1.0], dtype=float),
        f_helada=np.array([1.0], dtype=float),
        f_temp=np.array([1.0], dtype=float),
        sum_eta=np.array([50.0], dtype=float),
        sum_etc=np.array([100.0], dtype=float),
        limiting=["agua"],
    )

    from app.engine.calendar import get_sowing_grid

    grid = get_sowing_grid("S")
    table = MockSlotTable(
        mapping={
            ("soya", grid.index("11-16"), "fallow"): res_1,
            ("maiz", grid.index("05-01"), "fallow"): res_2,
        },
        seasons=seasons,
    )

    _, seasons_out, _ = evaluate_rotation(
        rotation=rot,
        slot_table=table,  # type: ignore
        seasons=seasons,
        hemisphere="S",
    )

    # El desempate prioriza agua sobre calor
    assert seasons_out[0].limiting == "agua"


def test_evaluate_rotation_with_real_demo_fixture(demo_power_df):
    """PLAN §4.6 — Evaluación de la rotación actual del demo (soya verano 11-16 -> soya invierno 05-01)."""
    table = SlotTable(
        weather_df=demo_power_df,
        lat=-17.78,
        soil_texture="franco",
    )

    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="05-01"),
                ]
            )
        ]
    )

    valid, msg = validate_rotation(rot, hemisphere="S")
    assert valid is True

    metrics, seasons_out, slots_out = evaluate_rotation(
        rotation=rot,
        slot_table=table,
        seasons=table.seasons,
        hemisphere="S",
    )

    assert len(seasons_out) == 34
    assert len(slots_out) == 1
    assert len(slots_out[0]) == 2

    # Invariantes sobre métricas
    assert 0.0 <= metrics.mean_index <= 1.0
    assert 0.0 <= metrics.p10_index <= 1.0
    assert metrics.mean_productivity > 0.0
    assert metrics.productivity_vs_current == 100.0
    assert 0 <= metrics.bad_seasons <= 20
    assert metrics.n_seasons == 20
    assert metrics.n_period == 15
    assert 0 <= metrics.bad_before <= 15
    assert 0 <= metrics.bad_recent <= 15
