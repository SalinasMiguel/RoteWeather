"""Tests para app.engine.climate (PLAN §4.8, §6 M1–M4)."""

import numpy as np
import pandas as pd
import pytest

from app.engine.climate import calc_campaign_metrics, calc_climate_profile


def test_m1_onset_synthetic_series():
    """M1: serie sintética seca hasta el offset 100 y luego 10 mm/día → onset = 100."""
    dates = pd.date_range("2015-01-01", periods=365, freq="D")
    prec = np.zeros(365, dtype=float)
    # Seco hasta offset 100 (0..100 inclusive), 10 mm/día a partir de offset 101
    prec[101:] = 10.0

    df = pd.DataFrame(
        {
            "prec": prec,
            "tmax": np.full(365, 25.0),
            "tmin": np.full(365, 15.0),
            "et0": np.full(365, 4.0),
        },
        index=dates,
    )

    metrics = calc_campaign_metrics(df, 2015, hemisphere="N")
    assert metrics["onset"] == pytest.approx(100.0)


def test_m2_dry_spells_inside_season():
    """M2: 12 días secos dentro de la estación → dry_spells = 1, max_dry_spell = 12."""
    dates = pd.date_range("2015-01-01", periods=365, freq="D")
    prec = np.zeros(365, dtype=float)

    # Lluvia desde offset 101 para activar onset en 100
    prec[101:250] = 10.0

    # Insertar exactamente una racha seca de 12 días dentro de la estación: offsets 140..151
    prec[140:152] = 0.0

    # Cese de lluvias a partir de offset 250: prec es 0.0 hasta el fin
    # c = 250 >= 100 + 60 = 160; sum(prec[250..269]) = 0 < 10 mm -> cessation = 250

    df = pd.DataFrame(
        {
            "prec": prec,
            "tmax": np.full(365, 25.0),
            "tmin": np.full(365, 15.0),
            "et0": np.full(365, 4.0),
        },
        index=dates,
    )

    metrics = calc_campaign_metrics(df, 2015, hemisphere="N")
    assert metrics["onset"] == pytest.approx(100.0)
    assert metrics["cessation"] == pytest.approx(250.0)
    assert metrics["season_length"] == pytest.approx(150.0)
    assert metrics["dry_spells"] == pytest.approx(1.0)
    assert metrics["max_dry_spell"] == pytest.approx(12.0)


def test_m3_hot_days():
    """M3: tmax = 36 en 7 días → hot_days = 7."""
    dates = pd.date_range("2015-01-01", periods=365, freq="D")
    tmax = np.full(365, 28.0)
    # Exactamente 7 días con tmax > 35.0 (36.0 °C)
    tmax[[10, 20, 30, 40, 50, 60, 70]] = 36.0

    df = pd.DataFrame(
        {
            "prec": np.zeros(365),
            "tmax": tmax,
            "tmin": np.full(365, 18.0),
            "et0": np.full(365, 3.5),
        },
        index=dates,
    )

    metrics = calc_campaign_metrics(df, 2015, hemisphere="N")
    assert metrics["hot_days"] == pytest.approx(7.0)


def test_m4_climate_profile_identical_before_recent():
    """M4: before y recent idénticos → delta = 0, significant = False."""
    # Construir un dataset multi-año de 30 campañas (1991 a 2020) idénticas
    seasons = list(range(1991, 2021))
    all_dates = pd.date_range("1991-01-01", "2020-12-31", freq="D")

    # Clima base para cualquier día
    n_days = len(all_dates)
    prec = np.where(all_dates.day_of_year % 10 == 0, 15.0, 0.5)
    tmax = np.full(n_days, 29.0)
    tmin = np.full(n_days, 18.0)
    et0 = np.full(n_days, 3.8)

    df = pd.DataFrame(
        {
            "prec": prec,
            "tmax": tmax,
            "tmin": tmin,
            "et0": et0,
        },
        index=all_dates,
    )

    metrics, clim_before, clim_recent = calc_climate_profile(
        df, seasons, hemisphere="N"
    )

    assert len(metrics) == 14
    for m in metrics:
        assert m.delta == pytest.approx(0.0, abs=1e-5), f"Fallo en métrica {m.id}"
        assert m.significant is False, f"Métrica {m.id} no debería ser significativa"

    # Verificar climatología quincenal
    assert len(clim_before.rain_mm) == 24
    assert len(clim_recent.rain_mm) == 24
    assert len(clim_before.et0_mm) == 24
    assert len(clim_recent.et0_mm) == 24
    assert len(clim_before.tmax_c) == 24
    assert len(clim_recent.tmax_c) == 24
    assert len(clim_before.tmin_c) == 24
    assert len(clim_recent.tmin_c) == 24

    for b in range(24):
        assert clim_before.rain_mm[b] == pytest.approx(clim_recent.rain_mm[b], abs=0.1)
        assert clim_before.et0_mm[b] == pytest.approx(clim_recent.et0_mm[b], abs=0.1)


def test_gdd_and_water_deficit():
    """Verifica acumulaciones térmicas (GDD) y déficit hídrico."""
    dates = pd.date_range("2015-01-01", periods=365, freq="D")
    # tmax = 30, tmin = 10 -> (tmax+tmin)/2 = 20 -> GDD por día = 20 - 10 = 10 °C·día
    # En 365 días: GDD total = 3650
    tmax = np.full(365, 30.0)
    tmin = np.full(365, 10.0)
    # Lluvia = 1 mm/día -> mes ~30 mm. ET0 = 5 mm/día -> mes ~150 mm. Déficit ~120 mm/mes
    prec = np.full(365, 1.0)
    et0 = np.full(365, 5.0)

    df = pd.DataFrame({"prec": prec, "tmax": tmax, "tmin": tmin, "et0": et0}, index=dates)

    metrics = calc_campaign_metrics(df, 2015, hemisphere="N")
    assert metrics["gdd"] == pytest.approx(3650.0, abs=1.0)
    assert metrics["et0_total"] == pytest.approx(365 * 5.0, abs=1.0)
    assert metrics["water_deficit"] == pytest.approx(365 * 4.0, abs=5.0)
