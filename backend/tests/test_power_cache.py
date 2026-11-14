"""PLAN §2.3, §3 T1.2 — Tests unitarios para el cliente de NASA POWER, caché local y reintentos."""

import json
from pathlib import Path
import httpx
import pytest

from app.nasa.power import (
    PowerData,
    PowerUnavailable,
    fetch_power,
)
from tests.test_power_parse import _build_synthetic_power_payload


def test_T1_2_coordinate_rounding_and_cache_filename(tmp_path: Path):
    """T1.2 — Las coordenadas se redondean a 2 decimales en la query y en el nombre de caché."""
    recorded_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        payload = _build_synthetic_power_payload()
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    # Coordenadas con múltiples decimales que deben redondearse a -17.30 y -62.25
    lat_input = -17.30000001
    lon_input = -62.25499999

    res = fetch_power(
        lat=lat_input,
        lon=lon_input,
        start="20240101",
        end="20240103",
        cache_dir=tmp_path,
        client=client,
        retry_delays=(0.0, 0.0, 0.0),
    )

    assert isinstance(res, PowerData)
    assert len(recorded_requests) == 1

    # Verificar parámetros HTTP
    req = recorded_requests[0]
    query_params = dict(req.url.params)
    assert query_params["latitude"] == "-17.30"
    assert query_params["longitude"] == "-62.25"

    # Verificar archivo de caché con formato {lat:.2f}_{lon:.2f}_{start}_{end}.json
    expected_cache_file = tmp_path / "-17.30_-62.25_20240101_20240103.json"
    assert expected_cache_file.exists()


def test_T1_2_cache_hit_avoids_network_call(tmp_path: Path):
    """T1.2 — La segunda llamada consecutiva lee de disco sin generar peticiones HTTP."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        payload = _build_synthetic_power_payload()
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    # 1ª llamada: Cache miss -> hace request HTTP y escribe en tmp_path
    res1 = fetch_power(
        lat=-17.30,
        lon=-62.25,
        start="20240101",
        end="20240103",
        cache_dir=tmp_path,
        client=client,
        retry_delays=(0.0, 0.0, 0.0),
    )
    assert call_count == 1
    assert isinstance(res1, PowerData)

    # 2ª llamada con un cliente cuyo handler levantaría AssertionError si fuera llamado
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        pytest.fail("La segunda llamada no debe realizar peticiones HTTP (debe ser cache hit)")

    no_network_client = httpx.Client(transport=httpx.MockTransport(fail_if_called))

    res2 = fetch_power(
        lat=-17.30,
        lon=-62.25,
        start="20240101",
        end="20240103",
        cache_dir=tmp_path,
        client=no_network_client,
        retry_delays=(0.0, 0.0, 0.0),
    )
    assert isinstance(res2, PowerData)
    assert call_count == 1  # No se incrementó


def test_T1_2_retry_success_after_transient_failures(tmp_path: Path):
    """T1.2 — Reintenta ante fallos transitorios y retorna PowerData si un intento posterior tiene éxito."""
    attempt = 0

    def mock_flaky_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            return httpx.Response(500, text="Internal Server Error")
        elif attempt == 2:
            return httpx.Response(503, text="Service Unavailable")
        else:
            payload = _build_synthetic_power_payload()
            return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(mock_flaky_handler))

    res = fetch_power(
        lat=-17.30,
        lon=-62.25,
        start="20240101",
        end="20240103",
        cache_dir=tmp_path,
        client=client,
        retry_delays=(0.0, 0.0, 0.0),
    )

    assert isinstance(res, PowerData)
    assert attempt == 3


def test_T1_2_power_unavailable_after_3_consecutive_failures(tmp_path: Path):
    """T1.2 — Tras 3 fallos consecutivos se levanta PowerUnavailable."""
    attempts = 0

    def mock_always_fails(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, text="NASA POWER Down")

    client = httpx.Client(transport=httpx.MockTransport(mock_always_fails))

    with pytest.raises(PowerUnavailable) as exc_info:
        fetch_power(
            lat=-17.30,
            lon=-62.25,
            start="20240101",
            end="20240103",
            cache_dir=tmp_path,
            client=client,
            retry_delays=(0.0, 0.0, 0.0),
        )

    assert attempts == 3
    assert "NASA POWER API no disponible tras 3 intentos" in str(exc_info.value)


def test_T1_2_power_unavailable_after_3_network_timeouts(tmp_path: Path):
    """T1.2 — Excepciones de red/timeout también activan los 3 intentos antes de PowerUnavailable."""
    attempts = 0

    def mock_timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectTimeout("Connection to power.larc.nasa.gov timed out")

    client = httpx.Client(transport=httpx.MockTransport(mock_timeout_handler))

    with pytest.raises(PowerUnavailable):
        fetch_power(
            lat=-17.30,
            lon=-62.25,
            start="20240101",
            end="20240103",
            cache_dir=tmp_path,
            client=client,
            retry_delays=(0.0, 0.0, 0.0),
        )

    assert attempts == 3
