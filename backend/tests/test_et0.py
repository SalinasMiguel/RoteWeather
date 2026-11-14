"""Tests para app.engine.et0 (PLAN §4.2, §6 E1–E5)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.engine.et0 import (
    add_et0,
    calc_et0_hargreaves,
    calc_et0_penman_monteith,
    calc_ra,
)
from app.nasa.power import parse_power_response


def test_e1_ra_fao56_example_8():
    """E1: Ra(lat −20°, J=246) = 32.2 ± 0.3 (FAO-56 ej. 8)."""
    lat_rad = float(np.radians(-20.0))
    ra = calc_ra(lat_rad, 246)
    assert isinstance(ra, float)
    assert ra == pytest.approx(32.2, abs=0.3)


def test_e2_ra_fao56_example_18():
    """E2: Ra(lat 50.8°, J=187) = 41.09 ± 0.3 (FAO-56 ej. 18)."""
    lat_rad = float(np.radians(50.8))
    ra = calc_ra(lat_rad, 187)
    assert isinstance(ra, float)
    assert ra == pytest.approx(41.09, abs=0.3)


def test_e3_pm_fao56_example_18():
    """E3: PM con tmax 21.5, tmin 12.3, rh 73.5, ws 2.078, rs 22.07, lat 50.8°, z 100, J 187, ps NaN → 3.6 ≤ ET0 ≤ 4.0."""
    lat_rad = float(np.radians(50.8))
    et0 = calc_et0_penman_monteith(
        tmax=21.5,
        tmin=12.3,
        rh=73.5,
        rs=22.07,
        ws=2.078,
        ps=np.nan,
        lat_rad=lat_rad,
        elevation_m=100.0,
        day_of_year=187,
    )
    assert isinstance(et0, float)
    assert 3.6 <= et0 <= 4.0
    assert et0 == pytest.approx(3.79, abs=0.1)


def test_e4_hargreaves_same_day():
    """E4: Hargreaves mismo día → 4.06 ± 0.15."""
    lat_rad = float(np.radians(50.8))
    ra = calc_ra(lat_rad, 187)
    et0_hg = calc_et0_hargreaves(tmax=21.5, tmin=12.3, ra=ra)
    assert isinstance(et0_hg, float)
    assert et0_hg == pytest.approx(4.06, abs=0.15)


def test_e5_add_et0_fallback_on_nan():
    """E5: add_et0 con rh=NaN en un día → et0_method == 'hg' ese día y 'pm' el resto."""
    dates = pd.date_range("2020-07-01", periods=5, freq="D")
    df = pd.DataFrame(
        {
            "tmax": [25.0, 26.0, 27.0, 24.0, 25.0],
            "tmin": [15.0, 16.0, 17.0, 14.0, 15.0],
            "rh": [70.0, np.nan, 75.0, 65.0, 70.0],
            "rs": [20.0, 21.0, 19.0, 22.0, 20.0],
            "ws": [2.0, 2.5, 1.8, 2.2, 2.0],
            "ps": [np.nan, np.nan, np.nan, np.nan, np.nan],
        },
        index=dates,
    )
    res = add_et0(df, lat=-17.3, elevation_m=280.0)

    # Verifica que el df original no fue mutado
    assert "et0" not in df.columns
    assert "et0_method" not in df.columns

    # Verifica columnas agregadas y fallback en el día con NaN
    assert "et0" in res.columns
    assert "et0_method" in res.columns
    assert res["et0_method"].tolist() == ["pm", "hg", "pm", "pm", "pm"]
    assert (res["et0"] >= 0.0).all()
    assert not res["et0"].isna().any()


def test_vectorized_et0_functions():
    """Verifica que calc_ra, calc_et0_penman_monteith y calc_et0_hargreaves funcionen con arrays."""
    lat_rad = float(np.radians(50.8))
    doys = np.array([180, 187, 195])
    ra_arr = calc_ra(lat_rad, doys)
    assert isinstance(ra_arr, np.ndarray)
    assert ra_arr.shape == (3,)

    tmax = np.array([20.0, 21.5, 23.0])
    tmin = np.array([11.0, 12.3, 13.0])
    rh = np.array([70.0, 73.5, 75.0])
    rs = np.array([21.0, 22.07, 23.0])
    ws = np.array([2.0, 2.078, 2.5])
    ps = np.full(3, np.nan)

    pm_arr = calc_et0_penman_monteith(tmax, tmin, rh, rs, ws, ps, lat_rad, 100.0, doys)
    assert isinstance(pm_arr, np.ndarray)
    assert pm_arr.shape == (3,)
    assert (pm_arr > 0).all()

    hg_arr = calc_et0_hargreaves(tmax, tmin, ra_arr)
    assert isinstance(hg_arr, np.ndarray)
    assert hg_arr.shape == (3,)
    assert (hg_arr > 0).all()


def test_add_et0_with_fixture():
    """Verifica add_et0 sobre el fixture completo de Santa Cruz (12,784 días)."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    if not fixture_path.exists():
        pytest.skip("Fixture power_demo.json no encontrado")

    with open(fixture_path, "r", encoding="utf-8") as f:
        raw_json = json.load(f)

    power_data = parse_power_response(raw_json)
    df_with_et0 = add_et0(power_data.df, lat=power_data.lat, elevation_m=power_data.elevation_m)

    assert len(df_with_et0) == 12784
    assert "et0" in df_with_et0.columns
    assert "et0_method" in df_with_et0.columns
    # El fixture de Santa Cruz tiene 0 NaNs en variables climáticas, debe usar pm en todos los días
    assert (df_with_et0["et0_method"] == "pm").all()
    assert (df_with_et0["et0"] >= 0.0).all()
    assert not df_with_et0["et0"].isna().any()
    # ET0 diario típicamente entre 0.5 y 10 mm/día en llanos tropicales
    assert df_with_et0["et0"].mean() == pytest.approx(4.0, abs=1.5)
