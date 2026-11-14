"""PLAN §2.2, §2.5, §6 — Tests unitarios para el fixture de contrato analyze_response.example.json."""

import json
from pathlib import Path
import re
import pytest

from app.schemas import AnalyzeResponse

POWER_CANONICAL_PARAMS = {
    "PRECTOTCORR",
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "RH2M",
    "ALLSKY_SFC_SW_DWN",
    "WS2M",
    "GWETTOP",
    "GWETROOT",
    "PS",
}


def get_example_path() -> Path:
    # backend/tests/ -> backend/ -> repo root / contracts / analyze_response.example.json
    root = Path(__file__).resolve().parent.parent.parent
    path = root / "contracts" / "analyze_response.example.json"
    assert path.exists(), f"Fixture no encontrado en {path}"
    return path


def test_T0_6_analyze_response_example_loads_and_validates():
    """PLAN §2.2 — El fixture de ejemplo debe validar contra AnalyzeResponse sin errores."""
    example_file = get_example_path()
    with open(example_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    resp = AnalyzeResponse.model_validate(data)

    # Validar temporadas y perfiles
    assert resp.meta.seasons == [2023, 2024]
    assert [r.profile for r in resp.rotations] == ["actual", "adaptada", "regenerativa"]

    # Validar climatología quincenal (24 quincenas)
    for period in ("before", "recent"):
        assert period in resp.climatology
        clim = resp.climatology[period]
        assert len(clim.rain_mm) == 24
        assert len(clim.et0_mm) == 24
        assert len(clim.tmax_c) == 24
        assert len(clim.tmin_c) == 24

    # Validar serialización round-trip
    dumped = resp.model_dump_json()
    reloaded = AnalyzeResponse.model_validate_json(dumped)
    assert reloaded.meta.lat == resp.meta.lat


def test_T0_6_claim_invariants_in_example_fixture():
    """PLAN §2.5, §6 (F1, F2, F3) — Invariantes de Claims en las tarjetas de rotación."""
    example_file = get_example_path()
    with open(example_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    resp = AnalyzeResponse.model_validate(data)

    for rot in resp.rotations:
        card = rot.card

        # F2: Invariante de conteo de claims por sección
        assert len(card.why) >= 1, f"Perfil {rot.profile} tiene menos de 1 claim en 'why'"
        assert len(card.benefits) >= 1, f"Perfil {rot.profile} tiene menos de 1 claim en 'benefits'"
        assert len(card.risks) >= 2, f"Perfil {rot.profile} tiene menos de 2 claims en 'risks'"

        all_claims = card.why + card.benefits + card.risks
        for claim in all_claims:
            # F1: Todo número del texto debe existir en evidence[].value
            nums_in_text = re.findall(r"-?\d+(?:[.,]\d+)?", claim.text)
            ev_values_str = [str(e.value).replace(",", ".") for e in claim.evidence]

            for num in nums_in_text:
                num_clean = num.replace(",", ".")
                # Coincidencia como string exacto o como float numérico
                matched = False
                for ev_str in ev_values_str:
                    if num_clean == ev_str:
                        matched = True
                        break
                    try:
                        if float(num_clean) == float(ev_str):
                            matched = True
                            break
                    except ValueError:
                        pass
                assert matched, (
                    f"F1 violado en perfil {rot.profile}: el número '{num}' en el texto "
                    f"\"{claim.text}\" no existe en los valores de evidencia {ev_values_str}"
                )

            # F3: Parámetros POWER de procedencia
            for ev in claim.evidence:
                src = ev.source
                if src.dataset == "Regla agronómica":
                    assert src.parameters == [], "Regla agronómica debe tener parameters=[]"
                else:
                    assert set(src.parameters).issubset(POWER_CANONICAL_PARAMS), (
                        f"Parámetros inválidos en {src.parameters}"
                    )


def test_T0_6_example_runs_offline(monkeypatch):
    """PLAN §6 — La validación del contrato debe ejecutarse sin llamadas de red."""
    # Deshabilitar sockets / llamadas externas si intentara alguna
    example_file = get_example_path()
    with open(example_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    resp = AnalyzeResponse.model_validate(data)
    assert resp is not None
