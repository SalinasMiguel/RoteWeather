"""PLAN §6 — Tests unitarios para SlotTable (memoización y suavizado circular)."""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest

from app.engine.slot import SlotSimulationResult
from app.engine.table import SlotTable
from app.nasa.power import parse_power_response


@pytest.fixture
def sample_weather():
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")
    return pd.DataFrame(
        {
            "prec": 10.0,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )


@pytest.fixture
def demo_power_df():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pdata = parse_power_response(data)
    return pdata.df


def test_slot_table_memoization(sample_weather):
    """PLAN §4.6, §6 — Verifica que la 2ª lectura no recalcula (contador de simulaciones)."""
    table = SlotTable(
        weather_df=sample_weather,
        lat=-17.78,
        soil_texture="franco",
        seasons=[2015],
    )

    assert table.simulation_count == 0

    # Primera llamada: cálculo y memoización
    res1 = table.get_slot_result("soya", 0, "fallow")
    assert table.simulation_count == 1
    assert len(res1.y_rel) == 1

    # Segunda llamada con idénticos parámetros: debe recuperar de caché sin recalcular
    res2 = table.get_slot_result("soya", 0, "fallow")
    assert table.simulation_count == 1
    assert res1 is res2

    # Llamada con diferente modo previo: debe simular y memoizar
    res3 = table.get_slot_result("soya", 0, "crop")
    assert table.simulation_count == 2
    assert res3 is not res1

    # Llamada con diferente grid_idx: debe simular y memoizar
    res4 = table.get_slot_result("soya", 1, "fallow")
    assert table.simulation_count == 3


def test_slot_table_circular_smoothing(sample_weather):
    """PLAN §4.6, §6 — Verifica el suavizado circular de ventana 3 en bordes 0 y 23."""
    table = SlotTable(
        weather_df=sample_weather,
        lat=-17.78,
        soil_texture="franco",
        seasons=[2015],
    )

    def make_mock_result(val: float) -> SlotSimulationResult:
        return SlotSimulationResult(
            y_rel=np.array([val], dtype=float),
            f_agua=np.array([val], dtype=float),
            f_calor=np.array([val], dtype=float),
            f_helada=np.array([val], dtype=float),
            f_temp=np.array([val], dtype=float),
            sum_eta=np.array([100.0], dtype=float),
            sum_etc=np.array([100.0], dtype=float),
            limiting=["ninguno"],
        )

    values_by_idx = {
        22: 0.40,
        23: 0.70,
        0: 0.85,
        1: 0.55,
        2: 0.25,
    }

    original_get_slot = table.get_slot_result

    def mock_get_slot(crop_id, grid_idx, prev_mode):
        norm_idx = grid_idx % 24
        if norm_idx in values_by_idx:
            return make_mock_result(values_by_idx[norm_idx])
        return original_get_slot(crop_id, grid_idx, prev_mode)

    table.get_slot_result = mock_get_slot  # type: ignore

    # Test para grid_idx = 0: debe promediar (23, 0, 1) = (0.70 + 0.85 + 0.55) / 3 = 2.10 / 3 = 0.70
    smoothed_0 = table.get_smoothed_y_rel("soya", 0, "fallow")
    expected_0 = (0.70 + 0.85 + 0.55) / 3.0
    assert smoothed_0[0] == pytest.approx(expected_0, abs=1e-9)

    # Test para grid_idx = 23: debe promediar (22, 23, 0) = (0.40 + 0.70 + 0.85) / 3 = 1.95 / 3 = 0.65
    smoothed_23 = table.get_smoothed_y_rel("soya", 23, "fallow")
    expected_23 = (0.40 + 0.70 + 0.85) / 3.0
    assert smoothed_23[0] == pytest.approx(expected_23, abs=1e-9)

    # Test para grid_idx = 1: debe promediar (0, 1, 2) = (0.85 + 0.55 + 0.25) / 3 = 1.65 / 3 = 0.55
    smoothed_1 = table.get_smoothed_y_rel("soya", 1, "fallow")
    expected_1 = (0.85 + 0.55 + 0.25) / 3.0
    assert smoothed_1[0] == pytest.approx(expected_1, abs=1e-9)


def test_slot_table_grid_index_resolution(sample_weather):
    """PLAN §4.1 — get_grid_index resuelve correctamente las fechas de la rejilla."""
    table = SlotTable(
        weather_df=sample_weather,
        lat=-17.78,
        soil_texture="franco",
        seasons=[2015],
    )
    # Hemisferio sur empieza en 07-01 (índice 0)
    assert table.get_grid_index("07-01") == 0
    assert table.get_grid_index("07-16") == 1
    assert table.get_grid_index("11-16") == 9
    assert table.get_grid_index("06-16") == 23


def test_slot_table_modulo_indices(sample_weather):
    """PLAN §4.6 — get_slot_result normaliza índices fuera del rango 0..23 cíclicamente."""
    table = SlotTable(
        weather_df=sample_weather,
        lat=-17.78,
        soil_texture="franco",
        seasons=[2015],
    )

    r_0 = table.get_slot_result("soya", 0, "fallow")
    r_24 = table.get_slot_result("soya", 24, "fallow")
    assert r_0 is r_24

    r_23 = table.get_slot_result("soya", 23, "fallow")
    r_neg1 = table.get_slot_result("soya", -1, "fallow")
    assert r_23 is r_neg1


def test_slot_table_with_demo_power_fixture(demo_power_df):
    """PLAN §4.6 — Integración de SlotTable con dataset real POWER Santa Cruz."""
    table = SlotTable(
        weather_df=demo_power_df,
        lat=-17.78,
        soil_texture="franco",
    )
    assert len(table.seasons) == 34
    res = table.get_slot_result("soya", 9, "fallow")  # 11-16
    assert len(res.y_rel) == 34
    assert np.all(res.y_rel >= 0.0)
    assert np.all(res.y_rel <= 1.0)
    assert table.simulation_count == 1
