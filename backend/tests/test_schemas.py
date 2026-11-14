"""PLAN §2.1 y §2.2 — Tests unitarios para validación de contratos y esquemas Pydantic."""

import json
import pytest
from pydantic import ValidationError

from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    Claim,
    ClimateMetric,
    Climatology,
    Evidence,
    Meta,
    Rotation,
    RotationCard,
    RotationMetrics,
    RotationResult,
    RotationYear,
    SeasonOut,
    SlotIn,
    SlotOut,
    SoilScore,
    Source,
)


def test_T0_3_demo_request_validates_successfully():
    """PLAN §2.1 — El JSON del ejemplo demo debe validar sin errores."""
    raw_json = (
        '{"lat":-17.30,"lon":-62.25,"soil_texture":"franco",'
        '"current_rotation":{"years":[{"slots":['
        '{"crop_id":"soya","sow_date":"11-16"},'
        '{"crop_id":"soya","sow_date":"05-01"}'
        ']}]}}'
    )
    req = AnalyzeRequest.model_validate_json(raw_json)
    assert req.lat == -17.30
    assert req.lon == -62.25
    assert req.soil_texture == "franco"
    assert req.include_diversified is False
    assert len(req.current_rotation.years) == 1
    assert len(req.current_rotation.years[0].slots) == 2
    assert req.current_rotation.years[0].slots[0].crop_id == "soya"
    assert req.current_rotation.years[0].slots[0].sow_date == "11-16"
    assert req.current_rotation.years[0].slots[1].crop_id == "soya"
    assert req.current_rotation.years[0].slots[1].sow_date == "05-01"


@pytest.mark.parametrize(
    "invalid_date",
    [
        "11-15",        # día no es 01 ni 16
        "05-02",        # día no es 01 ni 16
        "12-31",        # día no es 01 ni 16
        "00-01",        # mes 00 inválido
        "13-16",        # mes 13 inválido
        "2024-11-16",   # formato no es MM-DD
        "11/16",        # barra en vez de guión
        "1-01",         # mes sin cero inicial
        "01-1",         # día sin cero inicial
        "",             # cadena vacía
        " 11-16",       # espacio inicial
        "11-16 ",       # espacio final
    ],
)
def test_T0_3_invalid_sow_date_raises_validation_error(invalid_date: str):
    """PLAN §2.1 — Cualquier fecha que no sea quincena (01 o 16 de mes 01..12) debe fallar."""
    with pytest.raises(ValidationError):
        SlotIn(crop_id="soya", sow_date=invalid_date)


@pytest.mark.parametrize(
    "valid_date",
    [
        f"{m:02d}-{d:02d}"
        for m in range(1, 13)
        for d in (1, 16)
    ],
)
def test_T0_3_all_24_quincenas_are_valid(valid_date: str):
    """PLAN §4.1 — Las 24 fechas quincenales del año deben ser válidas."""
    slot = SlotIn(crop_id="maiz", sow_date=valid_date)
    assert slot.sow_date == valid_date


@pytest.mark.parametrize(
    "lat, lon",
    [
        (-60.1, -62.25),   # lat < -60
        (60.1, -62.25),    # lat > 60
        (-17.30, -180.1),  # lon < -180
        (-17.30, 180.1),   # lon > 180
    ],
)
def test_T0_3_invalid_coordinates_raise_validation_error(lat: float, lon: float):
    """PLAN §2.1 — Coordenadas fuera de rango deben levantar ValidationError."""
    with pytest.raises(ValidationError):
        AnalyzeRequest(
            lat=lat,
            lon=lon,
            current_rotation=Rotation(
                years=[RotationYear(slots=[SlotIn(crop_id="soya", sow_date="11-16")])]
            ),
        )


def test_T0_3_invalid_soil_texture_raises_validation_error():
    """PLAN §2.1 — Textura de suelo no permitida debe levantar ValidationError."""
    with pytest.raises(ValidationError):
        AnalyzeRequest(
            lat=-17.30,
            lon=-62.25,
            soil_texture="limo",  # solo "arenoso", "franco", "arcilloso"
            current_rotation=Rotation(
                years=[RotationYear(slots=[SlotIn(crop_id="soya", sow_date="11-16")])]
            ),
        )


def test_T0_3_rotation_years_length_constraints():
    """PLAN §2.1 — La rotación debe tener entre 1 y 3 años."""
    slot = SlotIn(crop_id="soya", sow_date="11-16")
    year = RotationYear(slots=[slot])

    # 0 años debe fallar
    with pytest.raises(ValidationError):
        Rotation(years=[])

    # 4 años debe fallar
    with pytest.raises(ValidationError):
        Rotation(years=[year, year, year, year])

    # 1, 2 y 3 años deben pasar
    assert len(Rotation(years=[year]).years) == 1
    assert len(Rotation(years=[year, year]).years) == 2
    assert len(Rotation(years=[year, year, year]).years) == 3


def test_T0_3_rotation_year_slots_length_constraints():
    """PLAN §2.1 — Cada año de rotación debe tener entre 1 y 2 slots."""
    slot = SlotIn(crop_id="soya", sow_date="11-16")

    # 0 slots debe fallar
    with pytest.raises(ValidationError):
        RotationYear(slots=[])

    # 3 slots debe fallar
    with pytest.raises(ValidationError):
        RotationYear(slots=[slot, slot, slot])

    # 1 y 2 slots deben pasar
    assert len(RotationYear(slots=[slot]).slots) == 1
    assert len(RotationYear(slots=[slot, slot]).slots) == 2


def test_T0_3_claim_requires_at_least_one_evidence():
    """PLAN §2.2 — Un Claim debe tener al menos una evidencia."""
    with pytest.raises(ValidationError):
        Claim(text="Afirmación sin evidencia", evidence=[])


def test_T0_3_response_models_roundtrip():
    """PLAN §2.2 — Instanciación y serialización completa de AnalyzeResponse."""
    src = Source(
        dataset="NASA POWER (MERRA-2 / CERES SYN1deg)",
        parameters=["PRECTOTCORR", "T2M_MAX"],
        period="campañas 2005/06–2024/25",
    )
    ev = Evidence(label="Campañas malas", value="3 de 20", unit="de 20", source=src)
    claim = Claim(text="Tu rotación tuvo 3 campañas malas de 20.", evidence=[ev])
    soil = SoilScore(total=65.0, nitrogen=80.0, diversity=50.0, erosion=70.0, organic_matter=60.0)

    slot_out = SlotOut(
        crop_id="soya",
        crop_name="Soya",
        family="Fabaceae",
        harvested=True,
        sow_date="11-16",
        sow_offset=138,
        stage_ends=[20, 50, 110, 135],
        sens_window=(45, 75),
        prev_mode="fallow",
        mean_yield=0.88,
        failures=2,
    )

    season_out = SeasonOut(
        season=2023,
        label="2023/24",
        index=0.85,
        productivity=0.88,
        bad=False,
        limiting="ninguno",
    )

    metrics = RotationMetrics(
        mean_index=0.82,
        p10_index=0.61,
        mean_productivity=0.84,
        productivity_vs_current=100.0,
        bad_seasons=3,
        n_seasons=20,
        bad_before=2,
        bad_recent=4,
        n_period=15,
        soil=soil,
    )

    card = RotationCard(
        profile="actual",
        title="Rotación Actual",
        why=[claim],
        benefits=[claim],
        risks=[claim],
        changes_vs_current=[],
        relaxed_constraints=[],
        improves_on_current=False,
    )

    rot_result = RotationResult(
        profile="actual",
        rotation=Rotation(years=[RotationYear(slots=[SlotIn(crop_id="soya", sow_date="11-16")])]),
        slots=[[slot_out]],
        metrics=metrics,
        seasons=[season_out],
        card=card,
    )

    climate_metric = ClimateMetric(
        id="rain_total",
        label="Lluvia total anual",
        unit="mm",
        before=1250.0,
        recent=1180.0,
        delta=-70.0,
        p_value=0.15,
        significant=False,
        series=[(2005, 1200.0), (2006, 1300.0)],
        source=src,
    )

    climatology = Climatology(
        rain_mm=[50.0] * 24,
        et0_mm=[4.0] * 24,
        tmax_c=[30.0] * 24,
        tmin_c=[20.0] * 24,
    )

    meta = Meta(
        lat=-17.30,
        lon=-62.25,
        elevation_m=350.0,
        hemisphere="S",
        ag_year_start="07-01",
        seasons=[2005, 2006],
        periods={"before": (1991, 2005), "recent": (2010, 2024), "eval": (2005, 2024)},
        et0_hargreaves_share=0.02,
        resolution_note="POWER ≈ 0.5°×0.625° (≈50 km): clima regional, no de parcela",
        assumptions=["S1. POWER regional", "S2. Spinup 180 días"],
    )

    resp = AnalyzeResponse(
        meta=meta,
        climate=[climate_metric],
        climatology={"before": climatology, "recent": climatology},
        rotations=[rot_result],
    )

    # Serialización y deserialización
    dumped = resp.model_dump_json()
    loaded = AnalyzeResponse.model_validate_json(dumped)
    assert loaded.meta.lat == -17.30
    assert loaded.rotations[0].profile == "actual"
    assert loaded.rotations[0].slots[0][0].sens_window == (45, 75)
    assert loaded.climate[0].series == [(2005, 1200.0), (2006, 1300.0)]
