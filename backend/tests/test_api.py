"""PLAN §6 — Tests de integración para API y pipeline (P1–P3 y complementarios)."""

from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.nasa.power import PowerUnavailable, parse_power_response
from app.pipeline import clear_analyze_cache


@pytest.fixture
def client():
    clear_analyze_cache()
    return TestClient(app)


@pytest.fixture
def mock_power_data():
    fixture_path = (
        Path(__file__).resolve().parent / "fixtures" / "power_demo.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_power_response(data)


@pytest.fixture
def demo_request_payload():
    return {
        "lat": -17.30,
        "lon": -62.25,
        "soil_texture": "franco",
        "current_rotation": {
            "years": [
                {
                    "slots": [
                        {"crop_id": "soya", "sow_date": "11-16"},
                        {"crop_id": "soya", "sow_date": "05-01"},
                    ]
                }
            ]
        },
        "include_diversified": False,
    }


def test_p1_analyze_demo_query(
    client, mock_power_data, demo_request_payload, monkeypatch
):
    """PLAN §6 P1 — POST /analyze con el demo y POWER mockeado: 200, 3 rotaciones (actual/adaptada/regenerativa)."""
    monkeypatch.setattr(
        "app.pipeline.fetch_power",
        lambda lat, lon, start, end, client=None: mock_power_data,
    )

    response = client.post("/analyze", json=demo_request_payload)
    assert response.status_code == 200, response.text
    data = response.json()

    # Validar metadatos principales
    meta = data["meta"]
    assert meta["lat"] == -17.30
    assert meta["lon"] == -62.25
    assert meta["hemisphere"] == "S"
    assert meta["ag_year_start"] == "07-01"
    assert len(meta["seasons"]) == 34
    assert meta["periods"]["eval"] == [2005, 2024]
    assert "POWER ≈" in meta["resolution_note"]
    assert len(meta["assumptions"]) == 12

    # Clima y climatología quincenal
    assert len(data["climate"]) >= 10
    assert "before" in data["climatology"]
    assert "recent" in data["climatology"]
    assert len(data["climatology"]["before"]["rain_mm"]) == 24

    # Rotaciones devueltas en orden estricto
    rotations = data["rotations"]
    assert len(rotations) == 3
    profiles = [r["profile"] for r in rotations]
    assert profiles == ["actual", "adaptada", "regenerativa"]

    # Fichas presentes con evidencias
    for r in rotations:
        card = r["card"]
        assert len(card["why"]) >= 1
        assert len(card["benefits"]) >= 1
        assert len(card["risks"]) >= 2
        assert any("Resolución ≈50 km" in claim["text"] for claim in card["risks"])


def test_p2_byte_for_byte_reproducibility(
    client, mock_power_data, demo_request_payload, monkeypatch
):
    """PLAN §6 P2 — Dos llamadas idénticas producen JSON idéntico byte a byte."""
    monkeypatch.setattr(
        "app.pipeline.fetch_power",
        lambda lat, lon, start, end, client=None: mock_power_data,
    )

    resp1 = client.post("/analyze", json=demo_request_payload)
    resp2 = client.post("/analyze", json=demo_request_payload)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.content == resp2.content


def test_p3_unknown_crop_id_returns_422(client, mock_power_data, monkeypatch):
    """PLAN §6 P3 — Cultivo desconocido devuelve HTTP 422 con mensaje descriptivo en español."""
    monkeypatch.setattr(
        "app.pipeline.fetch_power",
        lambda lat, lon, start, end, client=None: mock_power_data,
    )

    bad_payload = {
        "lat": -17.30,
        "lon": -62.25,
        "soil_texture": "franco",
        "current_rotation": {
            "years": [
                {
                    "slots": [
                        {"crop_id": "cultivo_fantasma", "sow_date": "11-16"}
                    ]
                }
            ]
        },
    }
    resp = client.post("/analyze", json=bad_payload)
    assert resp.status_code == 422
    assert "desconocido" in resp.json()["detail"].lower()


def test_turnaround_violation_returns_422(
    client, mock_power_data, monkeypatch
):
    """PLAN §2.1 — Violación de turnaround (< 10 días entre slots) devuelve HTTP 422."""
    monkeypatch.setattr(
        "app.pipeline.fetch_power",
        lambda lat, lon, start, end, client=None: mock_power_data,
    )

    # soya ciclo 135 días sembrada el 11-16 cosecha el 03-31. Si se siembra otra el 04-01 -> gap = 1 día (< 10)
    bad_payload = {
        "lat": -17.30,
        "lon": -62.25,
        "soil_texture": "franco",
        "current_rotation": {
            "years": [
                {
                    "slots": [
                        {"crop_id": "soya", "sow_date": "11-16"},
                        {"crop_id": "soya", "sow_date": "04-01"},
                    ]
                }
            ]
        },
    }
    resp = client.post("/analyze", json=bad_payload)
    assert resp.status_code == 422
    assert "días" in resp.json()["detail"]


def test_no_harvestable_crop_returns_422(
    client, mock_power_data, monkeypatch
):
    """PLAN §2.1 — Rotación sin ningún cultivo cosechable devuelve HTTP 422."""
    monkeypatch.setattr(
        "app.pipeline.fetch_power",
        lambda lat, lon, start, end, client=None: mock_power_data,
    )

    cover_only_payload = {
        "lat": -17.30,
        "lon": -62.25,
        "soil_texture": "franco",
        "current_rotation": {
            "years": [
                {
                    "slots": [
                        {"crop_id": "crotalaria", "sow_date": "11-16"}
                    ]
                }
            ]
        },
    }
    resp = client.post("/analyze", json=cover_only_payload)
    assert resp.status_code == 422
    assert "cosechable" in resp.json()["detail"].lower()


def test_overrun_violation_returns_422(
    client, mock_power_data, monkeypatch
):
    """PLAN §2.1 — Rotación con fecha de cosecha que supera 365 + MAX_OVERRUN_DAYS devuelve HTTP 422."""
    monkeypatch.setattr(
        "app.pipeline.fetch_power",
        lambda lat, lon, start, end, client=None: mock_power_data,
    )
    # En hemisferio S, soya@05-01 tiene sow_offset = 304 y ciclo = 135 (cosecha en 439 días).
    # Ajustando MAX_OVERRUN_DAYS = 50 durante el test, el límite de campaña es 365 + 50 = 415 días.
    # 439 > 415 días desencadena la violación temporal por exceso de duración de campaña.
    monkeypatch.setattr("app.engine.rotation.MAX_OVERRUN_DAYS", 50)

    payload = {
        "lat": -17.30,
        "lon": -62.25,
        "soil_texture": "franco",
        "current_rotation": {
            "years": [
                {
                    "slots": [
                        {"crop_id": "soya", "sow_date": "05-01"},
                    ]
                }
            ]
        },
        "include_diversified": False,
    }
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 422
    assert "excede el límite máximo de campaña" in resp.json()["detail"]


def test_health_endpoint(client):
    """Verifica GET /health responde status ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_crops_endpoint(client):
    """PLAN §2.4 — Verifica GET /crops devuelve el catálogo con los 13 cultivos."""
    resp = client.get("/crops")
    assert resp.status_code == 200
    crops = resp.json()
    assert len(crops) == 13
    crop_ids = {c["id"] for c in crops}
    assert "soya" in crop_ids
    assert "crotalaria" in crop_ids
    for c in crops:
        assert "nombre" in c
        assert "familia" in c
        assert "cosechable" in c
        assert "n_verificar_pendientes" in c


def test_power_unavailable_returns_503(
    client, demo_request_payload, monkeypatch
):
    """PLAN §2.3 — Si fetch_power levanta PowerUnavailable, el API responde HTTP 503."""

    def mock_fail(*args, **kwargs):
        raise PowerUnavailable("Simulated NASA POWER service failure")

    monkeypatch.setattr("app.pipeline.fetch_power", mock_fail)

    resp = client.post("/analyze", json=demo_request_payload)
    assert resp.status_code == 503
    assert "POWER" in resp.json()["detail"]
