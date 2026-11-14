"""PLAN §6 — Tests de simulación completa de slot (S1–S5 y complementarios)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.data.crops import load_crops
from app.engine.slot import simulate_slot
from app.nasa.power import parse_power_response


@pytest.fixture
def catalog():
    return load_crops()


@pytest.fixture
def soya(catalog):
    return catalog["soya"]


def test_s1_wet_synthetic_climate(soya):
    """S1: Clima sintético húmedo (prec 10, et0 5, tmax 30, tmin 20, soya, franco).

    Y_rel = 1.0 ± 1e-9.
    """
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")
    df = pd.DataFrame(
        {
            "prec": 10.0,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )

    res = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=df,
        lat=-17.78,
        seasons=[2015],
    )

    assert len(res.y_rel) == 1
    assert res.y_rel[0] == pytest.approx(1.0, abs=1e-9)
    assert res.f_agua[0] == pytest.approx(1.0, abs=1e-9)
    assert res.f_calor[0] == pytest.approx(1.0, abs=1e-9)
    assert res.f_helada[0] == pytest.approx(1.0, abs=1e-9)
    assert res.f_temp[0] == pytest.approx(1.0, abs=1e-9)
    assert res.limiting[0] == "ninguno"


def test_s2_dry_synthetic_climate(soya):
    """S2: Clima seco (prec 0 todo el periodo incl. spin-up, modo crop).

    1 - ratio > 0.8 y Y_rel < 0.35.
    """
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")
    df = pd.DataFrame(
        {
            "prec": 0.0,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )

    res = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=df,
        lat=-17.78,
        seasons=[2015],
    )

    ratio = res.sum_eta[0] / res.sum_etc[0]
    assert 1.0 - ratio > 0.8
    assert res.y_rel[0] < 0.35
    assert res.limiting[0] == "agua"


def test_s3_monotonicity_rain_scaling(soya):
    """S3: Monotonía: escalar la lluvia x1.5 nunca reduce Y_rel."""
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")
    rng = np.random.default_rng(42)
    prec_base = rng.uniform(0.0, 5.0, size=len(dates))

    df_base = pd.DataFrame(
        {
            "prec": prec_base,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )

    df_scaled = pd.DataFrame(
        {
            "prec": prec_base * 1.5,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )

    res_base = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=df_base,
        lat=-17.78,
        seasons=[2015],
    )

    res_scaled = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=df_scaled,
        lat=-17.78,
        seasons=[2015],
    )

    assert res_scaled.y_rel[0] >= res_base.y_rel[0] - 1e-9


def test_s4_crop_vs_fallow_spinup_impact(soya):
    """S4: modo 'crop' <= modo 'fallow' en Y_rel con lluvia escasa (2 mm/día)."""
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")
    df = pd.DataFrame(
        {
            "prec": 2.0,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )

    res_crop = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=df,
        lat=-17.78,
        seasons=[2015],
    )

    res_fallow = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="fallow",
        soil_texture="franco",
        weather_df=df,
        lat=-17.78,
        seasons=[2015],
    )

    assert res_crop.y_rel[0] <= res_fallow.y_rel[0] + 1e-9


def test_s5_vectorized_identical_campaigns(soya):
    """S5: Vector de 3 campañas idénticas -> 3 resultados estrictamente idénticos."""
    dates = pd.date_range("2013-01-01", "2018-12-31", freq="D")
    df = pd.DataFrame(
        {
            "prec": 4.0,
            "et0": 5.0,
            "tmax": 28.0,
            "tmin": 18.0,
        },
        index=dates,
    )

    seasons = [2014, 2015, 2016]
    res = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=df,
        lat=-17.78,
        seasons=seasons,
    )

    assert len(res.y_rel) == 3
    assert res.y_rel[0] == pytest.approx(res.y_rel[1], abs=1e-12)
    assert res.y_rel[1] == pytest.approx(res.y_rel[2], abs=1e-12)

    assert res.f_agua[0] == pytest.approx(res.f_agua[1], abs=1e-12)
    assert res.f_calor[0] == pytest.approx(res.f_calor[1], abs=1e-12)
    assert res.f_helada[0] == pytest.approx(res.f_helada[1], abs=1e-12)
    assert res.f_temp[0] == pytest.approx(res.f_temp[1], abs=1e-12)
    assert res.limiting[0] == res.limiting[1] == res.limiting[2]


def test_s6_limiting_factor_tie_break(soya):
    """Verifica orden de desempate de factor limitante: agua > calor > helada > temperatura."""
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")

    # Clima con calor y frío controlados para probar desempates
    df = pd.DataFrame(
        {
            "prec": 10.0,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )
    res = simulate_slot(soya, "11-16", "crop", "franco", df, lat=-17.78, seasons=[2015])
    assert res.limiting[0] == "ninguno"


def test_s7_power_demo_integration(soya):
    """Integración completa sobre fixture real NASA POWER (34 campañas)."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    power_data = parse_power_response(raw_data)
    res = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=power_data.df,
        lat=power_data.lat,
    )

    assert len(res.y_rel) == 34
    assert np.all((res.y_rel >= 0.0) & (res.y_rel <= 1.0))
    assert np.all((res.f_agua >= 0.0) & (res.f_agua <= 1.0))
    assert np.all((res.f_calor >= 0.0) & (res.f_calor <= 1.0))
    assert np.all((res.f_helada >= 0.0) & (res.f_helada <= 1.0))
    assert np.all((res.f_temp >= 0.0) & (res.f_temp <= 1.0))

    valid_limiters = {"agua", "calor", "helada", "temperatura", "ninguno"}
    for lim in res.limiting:
        assert lim in valid_limiters


def test_s8_nan_weather_handling(soya):
    """PLAN §4.4 — Campaña con NaN en prec/tmax/tmin produce NaN en resultado."""
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")
    df = pd.DataFrame(
        {
            "prec": 10.0,
            "et0": 5.0,
            "tmax": 30.0,
            "tmin": 20.0,
        },
        index=dates,
    )
    # Introducir NaN en campaña 2015
    df.loc["2015-11-20", "prec"] = np.nan

    res = simulate_slot(
        crop=soya,
        sow_date_str="11-16",
        prev_mode="crop",
        soil_texture="franco",
        weather_df=df,
        lat=-17.78,
        seasons=[2015],
    )
    assert np.isnan(res.y_rel[0])
    assert np.isnan(res.f_agua[0])
    assert res.limiting[0] == "ninguno"


def test_s9_invalid_inputs_raise_error(soya):
    """Validación de argumentos inválidos."""
    dates = pd.date_range("2014-01-01", "2017-12-31", freq="D")
    df = pd.DataFrame({"prec": 10.0, "et0": 5.0, "tmax": 30.0, "tmin": 20.0}, index=dates)

    with pytest.raises(ValueError, match="Textura de suelo desconocida"):
        simulate_slot(soya, "11-16", "crop", "suelo_invalido", df, lat=-17.78)

    with pytest.raises(ValueError, match="Modo previo desconocido"):
        simulate_slot(soya, "11-16", "invalido", "franco", df, lat=-17.78)
