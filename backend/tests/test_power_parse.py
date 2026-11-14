"""PLAN §2.3, §3 T1.1 — Tests unitarios para el parser de NASA POWER."""

import numpy as np
import pandas as pd
import pytest

from app.nasa.power import (
    CANONICAL_COLUMNS,
    POWER_PARAM_MAP,
    PowerData,
    parse_power_response,
)


def _build_synthetic_power_payload(
    dates: list[str] = ("20240101", "20240102", "20240103"),
    fill_prec_day: str | None = "20240102",
) -> dict:
    """Construye un payload sintético de NASA POWER para pruebas 100% offline."""
    param_dict = {}
    base_values = {
        "PRECTOTCORR": 5.2,
        "T2M": 24.1,
        "T2M_MAX": 31.5,
        "T2M_MIN": 18.2,
        "RH2M": 75.0,
        "ALLSKY_SFC_SW_DWN": 19.8,
        "WS2M": 2.4,
        "GWETTOP": 0.65,
        "GWETROOT": 0.58,
        "PS": 98.2,
    }

    for power_key, default_val in base_values.items():
        daily_series = {}
        for d in dates:
            if power_key == "PRECTOTCORR" and d == fill_prec_day:
                daily_series[d] = -999.0  # fill value
            else:
                daily_series[d] = float(default_val)
        param_dict[power_key] = daily_series

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [-62.25, -17.30, 280.15],  # [lon, lat, elev_m]
        },
        "header": {
            "title": "NASA/POWER Source Daily Test Data",
            "api": {"version": "v2.10.3", "name": "POWER Daily API"},
            "fill_value": -999.0,
        },
        "properties": {
            "parameter": param_dict,
        },
    }


def test_T1_1_canonical_columns_and_types():
    """T1.1 — Todas las 10 columnas canónicas deben estar presentes con dtype float64."""
    payload = _build_synthetic_power_payload()
    power_data = parse_power_response(payload)

    assert isinstance(power_data, PowerData)
    assert list(power_data.df.columns) == CANONICAL_COLUMNS

    for col in CANONICAL_COLUMNS:
        assert power_data.df[col].dtype == np.float64, f"Columna {col} debe ser float64"

    # Verificar nombres nativos de POWER no expuestos en columnas
    for power_key in POWER_PARAM_MAP.keys():
        assert power_key not in power_data.df.columns


def test_T1_1_nan_conversion_strictly_applied():
    """T1.1, AGENTS.md regla 25 — El valor -999.0 debe ser reemplazado por NaN en df."""
    payload = _build_synthetic_power_payload(fill_prec_day="20240102")
    power_data = parse_power_response(payload)
    df = power_data.df

    # Verificar que el día con fill_value es NaN
    assert np.isnan(df.loc["2024-01-02", "prec"])
    assert df.loc["2024-01-01", "prec"] == pytest.approx(5.2)
    assert df.loc["2024-01-03", "prec"] == pytest.approx(5.2)

    # Invariante dura: -999.0 nunca jamás debe existir en el DataFrame
    assert not (df == -999.0).any().any()
    assert not (df == -999).any().any()


def test_T1_1_datetime_index_continuity_and_frequency():
    """T1.1 — El índice debe ser pd.DatetimeIndex continuo con freq='D' aun con huecos."""
    # Saltamos el día 20240102 intencionalmente en la entrada
    payload = _build_synthetic_power_payload(dates=["20240101", "20240103"], fill_prec_day=None)
    power_data = parse_power_response(payload)
    df = power_data.df

    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.freqstr == "D"
    assert len(df) == 3  # 2024-01-01, 2024-01-02, 2024-01-03

    # El día intermedio faltante debe ser reindexado automáticamente con NaN
    assert np.isnan(df.loc["2024-01-02", "prec"])
    assert np.isnan(df.loc["2024-01-02", "tmax"])


def test_T1_1_geometry_coordinates_and_elevation_extraction():
    """T1.1 — Elevación de geometry.coordinates[2], lon de [0], lat de [1]."""
    payload = _build_synthetic_power_payload()
    power_data = parse_power_response(payload)

    assert power_data.elevation_m == pytest.approx(280.15)
    assert power_data.lon == pytest.approx(-62.25)
    assert power_data.lat == pytest.approx(-17.30)


def test_T1_1_api_version_extraction_and_fallback():
    """T1.1 — Extrae versión de header.api.version o usa fallback."""
    payload = _build_synthetic_power_payload()
    power_data = parse_power_response(payload)
    assert power_data.api_version == "v2.10.3"

    # Fallback con header simplificado
    payload_fallback = {
        "geometry": {"coordinates": [-60.0, -15.0, 150.0]},
        "header": {"api_version": "v2.0-legacy", "fill_value": -999.0},
        "properties": {"parameter": {}},
    }
    pd_fallback = parse_power_response(payload_fallback)
    assert pd_fallback.api_version == "v2.0-legacy"


def test_T1_1_missing_parameter_column_filled_with_nan():
    """T1.1 — Si falta un parámetro en el payload, la columna existe como NaN float64."""
    payload = _build_synthetic_power_payload()
    # Eliminar PS
    del payload["properties"]["parameter"]["PS"]

    power_data = parse_power_response(payload)
    assert "ps" in power_data.df.columns
    assert power_data.df["ps"].isna().all()
    assert power_data.df["ps"].dtype == np.float64


def test_T1_3_power_demo_fixture_validates_offline():
    """T1.3, PLAN §3, ORIGINAL_REQUEST R3 — El fixture power_demo.json tiene 12.784 días y 0 NaNs."""
    from pathlib import Path
    import json

    fixture_path = Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    assert fixture_path.exists(), f"Fixture no encontrado en {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        raw_json = json.load(f)

    power_data = parse_power_response(raw_json)
    df = power_data.df

    # Verificación de invariantes
    assert len(df) == 12784
    assert df["prec"].isna().sum() == 0
    assert df["tmax"].isna().sum() == 0
    assert df["tmin"].isna().sum() == 0
    assert power_data.elevation_m == pytest.approx(280.15)
    assert power_data.lat == pytest.approx(-17.30)
    assert power_data.lon == pytest.approx(-62.25)
    assert power_data.api_version == "v2.10.3"

