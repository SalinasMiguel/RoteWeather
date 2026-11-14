"""Tests para app.engine.crop (PLAN §4.3, §6 K1–K3)."""

import pytest

from app.data.crops import get_crop, load_crops
from app.engine.crop import get_kc_curve, get_sensitive_window


def test_k1_soya_kc_curve():
    """K1: soya (20/30/60/25, Kc .40/1.15/.50): kc(0)=0.40, kc(35)=0.775, kc(50)=1.15, kc(109)=1.15, kc(134)=0.526 (±0.001)."""
    soya = get_crop("soya")
    assert soya.etapas_dias == [20, 30, 60, 25]
    assert soya.kc == [0.40, 1.15, 0.50]

    kc = get_kc_curve(soya)

    assert kc[0] == pytest.approx(0.40, abs=0.001)
    assert kc[35] == pytest.approx(0.775, abs=0.001)
    assert kc[50] == pytest.approx(1.15, abs=0.001)
    assert kc[109] == pytest.approx(1.15, abs=0.001)
    assert kc[134] == pytest.approx(0.526, abs=0.001)


def test_k2_soya_sensitive_window():
    """K2: sens = [45, 75)."""
    soya = get_crop("soya")
    sens = get_sensitive_window(soya)
    assert sens == (45, 75)


def test_k3_soya_cycle_length():
    """K3: N = 135."""
    soya = get_crop("soya")
    assert soya.ciclo == 135
    kc = get_kc_curve(soya)
    assert len(kc) == 135


def test_all_catalog_crops_kc_curves():
    """Verifica que todos los 13 cultivos del catálogo generen curvas Kc y ventanas sensibles coherentes."""
    catalog = load_crops()
    assert len(catalog) == 13

    for crop_id, crop in catalog.items():
        kc = get_kc_curve(crop)
        assert len(kc) == crop.ciclo
        assert (kc >= 0.0).all(), f"Crop {crop_id} tiene valores Kc negativos"
        assert (kc <= 2.0).all(), f"Crop {crop_id} tiene valores Kc > 2.0"

        start_sens, end_sens = get_sensitive_window(crop)
        assert 0 <= start_sens <= end_sens <= crop.ciclo
        assert (end_sens - start_sens) <= 30
