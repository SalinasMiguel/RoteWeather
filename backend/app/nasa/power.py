"""PLAN §2.3 — Cliente e ingestión de datos agroclimáticos de NASA POWER API.

Maneja parsing, normalización a columnas canónicas, conversión de fill values (-999.0)
a NaN, redondeo de coordenadas geográficas, caché en disco local y reintentos.
"""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import time
from typing import Any

import httpx
import numpy as np
import pandas as pd

from app.config import DATA_END, DATA_START

logger = logging.getLogger(__name__)

# Mapeo obligatorio y canónico de parámetros POWER (PLAN §2.3, AGENTS.md)
# Este es el único lugar donde aparecen los nombres nativos de la API de POWER.
POWER_PARAM_MAP: dict[str, str] = {
    "PRECTOTCORR": "prec",
    "T2M": "t2m",
    "T2M_MAX": "tmax",
    "T2M_MIN": "tmin",
    "RH2M": "rh",
    "ALLSKY_SFC_SW_DWN": "rs",
    "WS2M": "ws",
    "GWETTOP": "gwettop",
    "GWETROOT": "gwetroot",
    "PS": "ps",
}

CANONICAL_COLUMNS: list[str] = list(POWER_PARAM_MAP.values())
POWER_API_URL: str = "https://power.larc.nasa.gov/api/temporal/daily/point"


class PowerUnavailable(Exception):
    """PLAN §2.3 — Levantada cuando la API de NASA POWER no responde tras agotar reintentos."""

    pass


@dataclass
class PowerData:
    """PLAN §2.3 — Estructura canónica de datos agroclimáticos diarios de POWER."""

    lat: float
    lon: float
    elevation_m: float
    df: pd.DataFrame
    api_version: str


def parse_power_response(raw_json: dict[str, Any]) -> PowerData:
    """PLAN §2.3 — Parsea JSON crudo de POWER a PowerData con 10 columnas canónicas y DatetimeIndex diario."""
    # 1. Extracción de coordenadas y elevación (GeoJSON standard: [lon, lat, elev_m])
    coords = raw_json.get("geometry", {}).get("coordinates", [])
    lon = float(coords[0]) if len(coords) > 0 else 0.0
    lat = float(coords[1]) if len(coords) > 1 else 0.0
    elevation_m = float(coords[2]) if len(coords) > 2 else 0.0

    # 2. Versión de la API y fill_value
    header = raw_json.get("header", {})
    api_info = header.get("api")
    if isinstance(api_info, dict) and "version" in api_info:
        api_version = str(api_info["version"])
    elif "api_version" in header:
        api_version = str(header["api_version"])
    elif "version" in header:
        api_version = str(header["version"])
    else:
        api_version = "unknown"

    fill_value = float(header.get("fill_value", -999.0))

    # 3. Extracción de parámetros y construcción de columnas
    parameters_dict = raw_json.get("properties", {}).get("parameter", {})

    col_data: dict[str, dict[str, Any]] = {}
    all_dates: set[str] = set()

    for power_param, canonical_col in POWER_PARAM_MAP.items():
        param_series = parameters_dict.get(power_param, {})
        col_data[canonical_col] = param_series
        if isinstance(param_series, dict):
            all_dates.update(param_series.keys())

    if not all_dates:
        df = pd.DataFrame(columns=CANONICAL_COLUMNS, dtype="float64")
        df.index = pd.DatetimeIndex([], freq="D", name="date")
        return PowerData(
            lat=lat,
            lon=lon,
            elevation_m=elevation_m,
            df=df,
            api_version=api_version,
        )

    # Construir DataFrame a partir del diccionario de series
    df = pd.DataFrame(col_data)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.sort_index()

    # Reindexar con rango diario continuo completo (freq='D') para garantizar continuidad
    min_date = df.index.min()
    max_date = df.index.max()
    continuous_idx = pd.date_range(start=min_date, end=max_date, freq="D", name="date")
    df = df.reindex(continuous_idx)

    # Asegurar orden canónico de columnas y tipo float64
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    df = df[CANONICAL_COLUMNS]

    # AGENTS.md regla 25: El valor -999 de POWER se convierte a NaN en nasa/power.py
    # y en ningún otro lugar. Nunca entra a una suma.
    mask_fill = (df == -999.0) | (df == -999) | (df == fill_value)
    df[mask_fill] = np.nan

    return PowerData(
        lat=lat,
        lon=lon,
        elevation_m=elevation_m,
        df=df,
        api_version=api_version,
    )


def fetch_power(
    lat: float,
    lon: float,
    start: str = DATA_START,
    end: str = DATA_END,
    cache_dir: Path | str | None = None,
    client: httpx.Client | None = None,
    retry_delays: tuple[float, ...] = (2.0, 4.0, 8.0),
) -> PowerData:
    """PLAN §2.3 — Cliente POWER con redondeo a 2 decimales, caché local en disco y reintentos exponenciales.

    Parámetros:
        lat: Latitud geográfica en grados decimales.
        lon: Longitud geográfica en grados decimales.
        start: Fecha inicial en formato YYYYMMDD (por defecto 19910101).
        end: Fecha final en formato YYYYMMDD (por defecto 20251231).
        cache_dir: Directorio de almacenamiento de caché. Por defecto backend/cache/power.
        client: Cliente httpx opcional para inyección en tests offline.
        retry_delays: Tupla de tiempos de espera entre reintentos.
    """
    # 1. Redondeo estricto de coordenadas a 2 decimales antes de consultar o guardar en caché
    lat_r = round(float(lat), 2)
    lon_r = round(float(lon), 2)

    # 2. Resolución de ruta de caché
    if cache_dir is None:
        # backend/app/nasa/power.py -> backend/cache/power/
        resolved_cache_dir = Path(__file__).resolve().parent.parent.parent / "cache" / "power"
    else:
        resolved_cache_dir = Path(cache_dir)

    resolved_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = resolved_cache_dir / f"{lat_r:.2f}_{lon_r:.2f}_{start}_{end}.json"

    # 3. Comprobar si existe en caché local (cache hit)
    if cache_file.exists():
        logger.debug("Cache hit para POWER: %s", cache_file)
        with open(cache_file, "r", encoding="utf-8") as f:
            raw_json = json.load(f)
        return parse_power_response(raw_json)

    # 4. Cache miss: Consulta a la API de NASA POWER con reintentos
    url = POWER_API_URL
    params = {
        "parameters": ",".join(POWER_PARAM_MAP.keys()),
        "community": "AG",
        "longitude": f"{lon_r:.2f}",
        "latitude": f"{lat_r:.2f}",
        "start": start,
        "end": end,
        "format": "JSON",
    }

    max_attempts = 3
    last_error: Exception | None = None

    def _execute_requests(http_client: httpx.Client) -> PowerData:
        nonlocal last_error
        for attempt in range(max_attempts):
            try:
                resp = http_client.get(url, params=params)
                if resp.status_code == 200:
                    raw_data = resp.json()
                    # Guardar respuesta cruda en disco
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(raw_data, f)
                    return parse_power_response(raw_data)
                else:
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {resp.status_code} desde NASA POWER",
                        request=resp.request,
                        response=resp,
                    )
            except Exception as exc:
                last_error = exc

            # Si no es el último intento, esperar antes de reintentar
            if attempt < max_attempts - 1:
                delay = retry_delays[attempt] if attempt < len(retry_delays) else 0.0
                if delay > 0:
                    time.sleep(delay)

        raise PowerUnavailable(
            f"NASA POWER API no disponible tras {max_attempts} intentos para ({lat_r:.2f}, {lon_r:.2f}): {last_error}"
        ) from last_error

    if client is not None:
        return _execute_requests(client)
    else:
        with httpx.Client(timeout=60.0) as default_client:
            return _execute_requests(default_client)
