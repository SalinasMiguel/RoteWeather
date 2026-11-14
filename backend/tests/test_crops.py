"""PLAN §2.4 — Tests unitarios para el catálogo y cargador de cultivos."""

import json
from pathlib import Path
import pytest

from app.data.crops import (
    AGRONOMIC_FIELDS,
    REQUIRED_CROPS,
    DEFAULT_CROPS_PATH,
    get_crop,
    load_crops,
)


def test_T0_4_load_all_13_crops():
    """PLAN §2.4 — Deben cargarse exactamente los 13 cultivos requeridos."""
    catalog = load_crops()
    assert len(catalog) == 13
    assert set(catalog.keys()) == REQUIRED_CROPS


def test_T0_4_agronomic_fields_fuente_and_verificar():
    """PLAN §2.4 — Todo campo agronómico debe tener fuente no vacía y verificar=True en la semilla."""
    with open(DEFAULT_CROPS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for cid, crop_data in data.items():
        for afield in AGRONOMIC_FIELDS:
            assert afield in crop_data, f"Cultivo {cid} no tiene {afield}"
            entry = crop_data[afield]
            assert isinstance(entry, dict)
            assert "valor" in entry
            assert "fuente" in entry and isinstance(entry["fuente"], str) and entry["fuente"].strip(), (
                f"Cultivo {cid} campo {afield} tiene fuente vacía"
            )
            assert entry["verificar"] is True, f"Cultivo {cid} campo {afield} no tiene verificar=True"


def test_T0_4_crop_stages_sum_to_cycle():
    """PLAN §2.4 — Las 4 etapas fenológicas deben ser positivas y sumar el ciclo total."""
    catalog = load_crops()
    for cid, crop in catalog.items():
        assert len(crop.etapas_dias) == 4
        assert all(d > 0 for d in crop.etapas_dias)
        assert sum(crop.etapas_dias) == crop.ciclo
        assert crop.L_ini == crop.etapas_dias[0]
        assert crop.L_dev == crop.etapas_dias[1]
        assert crop.L_mid == crop.etapas_dias[2]
        assert crop.L_late == crop.etapas_dias[3]


def test_T0_4_kc_mid_ge_kc_ini():
    """PLAN §2.4 — Kc_mid debe ser mayor o igual a Kc_ini para todos los cultivos."""
    catalog = load_crops()
    for cid, crop in catalog.items():
        assert len(crop.kc) == 3
        assert crop.kc_mid >= crop.kc_ini, f"Cultivo {cid} tiene Kc_mid < Kc_ini"
        assert crop.kc_ini == crop.kc[0]
        assert crop.kc_mid == crop.kc[1]
        assert crop.kc_end == crop.kc[2]


def test_T0_4_clase_n_and_rastrojo_enums():
    """PLAN §2.4 — Las clases de nitrógeno y rastrojo deben pertenecer a los enums permitidos."""
    allowed_n = {
        "cobertura_leguminosa",
        "leguminosa_grano",
        "cobertura_no_leguminosa",
        "extractiva",
        "muy_extractiva",
    }
    allowed_rastrojo = {"bajo", "medio", "alto"}

    catalog = load_crops()
    for cid, crop in catalog.items():
        assert crop.clase_n in allowed_n, f"Cultivo {cid} clase_n inválida: {crop.clase_n}"
        assert crop.clase_rastrojo in allowed_rastrojo, f"Cultivo {cid} clase_rastrojo inválida: {crop.clase_rastrojo}"


def test_T0_4_flat_crop_properties():
    """PLAN §2.4 — Soya debe tener los parámetros especificados de FAO-56."""
    soya = get_crop("soya")
    assert soya.id == "soya"
    assert soya.nombre == "Soya"
    assert soya.familia == "Fabaceae"
    assert soya.cosechable is True
    assert soya.value_weight == 1.0
    assert soya.ciclo == 135
    assert soya.kc_ini == 0.40
    assert soya.kc_mid == 1.15
    assert soya.kc_end == 0.50
    assert soya.zr_max_m == 1.0
    assert soya.p == 0.50
    assert soya.ky == 0.85
    assert soya.t_helada == 0.0
    assert soya.n_verificar_pendientes == 10


def test_T0_4_cover_crops_properties():
    """PLAN §2.4 — Los cultivos de cobertura no son cosechables y su Kc_end == Kc_mid (verde)."""
    catalog = load_crops()
    for cid in ("avena_cob", "crotalaria"):
        crop = catalog[cid]
        assert crop.cosechable is False
        assert crop.value_weight == 0.0
        assert crop.ciclo == 90
        assert crop.kc_mid == crop.kc_end


def test_T0_4_invalid_crop_fails_validation(tmp_path: Path):
    """PLAN §2.4 — Datos corruptos deben levantar ValueError."""
    with open(DEFAULT_CROPS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Kc_mid < Kc_ini
    corrupted = dict(data)
    corrupted["soya"]["kc"]["valor"] = [0.80, 0.40, 0.20]
    bad_file = tmp_path / "bad_kc.json"
    bad_file.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(ValueError, match="Kc_mid .* must be >= Kc_ini"):
        load_crops(bad_file)

    # 2. Fuente vacía
    corrupted = dict(data)
    corrupted["soya"]["p"]["fuente"] = "   "
    bad_file = tmp_path / "bad_fuente.json"
    bad_file.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(ValueError, match="empty fuente"):
        load_crops(bad_file)

    # 3. Falta cultivo requerido
    corrupted = dict(data)
    del corrupted["crotalaria"]
    bad_file = tmp_path / "missing_crop.json"
    bad_file.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required crop"):
        load_crops(bad_file)


def test_T0_4_get_crop_unknown_raises_key_error():
    """PLAN §2.4 — Consultar un cultivo inexistente debe levantar KeyError."""
    with pytest.raises(KeyError, match="not found in catalog"):
        get_crop("platano")
