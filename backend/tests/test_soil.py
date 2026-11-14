"""Tests para app.engine.soil (PLAN §4.7, §6 G1–G4)."""

import numpy as np
import pytest

from app.engine.soil import calc_soil_score
from app.schemas import Rotation, RotationYear, SlotIn


def test_g1_soil_soya_soya():
    """G1: soya-soya: nitrogen = 80, diversity = 15, organic_matter = 33.3."""
    # Rotación de 1 año con 2 siembras de soya
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="soya", sow_date="05-01"),
                ]
            )
        ]
    )
    score = calc_soil_score(rot, hemisphere="S")

    assert score.nitrogen == pytest.approx(80.0, abs=0.1)
    assert score.diversity == pytest.approx(15.0, abs=0.1)
    assert score.organic_matter == pytest.approx(33.33, abs=0.1)
    # Sin lluvia, erosión es 100
    assert score.erosion == pytest.approx(100.0, abs=0.1)
    # Total = 0.25 * (80 + 15 + 33.33 + 100) = 57.08
    assert score.total == pytest.approx(57.08, abs=0.1)


def test_g2_soil_soya_maiz_same_year():
    """G2: soya + maíz (mismo año): nitrogen = 40, diversity = 65, organic_matter = 66.7."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                    SlotIn(crop_id="maiz", sow_date="05-01"),
                ]
            )
        ]
    )
    score = calc_soil_score(rot, hemisphere="S")

    assert score.nitrogen == pytest.approx(40.0, abs=0.1)
    assert score.diversity == pytest.approx(65.0, abs=0.1)
    assert score.organic_matter == pytest.approx(66.67, abs=0.1)
    assert score.erosion == pytest.approx(100.0, abs=0.1)


def test_g3_soil_maiz_solo():
    """G3: maíz solo: nitrogen = 30, diversity = 15, organic_matter = 50."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="maiz", sow_date="11-16"),
                ]
            )
        ]
    )
    score = calc_soil_score(rot, hemisphere="S")

    assert score.nitrogen == pytest.approx(30.0, abs=0.1)
    assert score.diversity == pytest.approx(15.0, abs=0.1)
    assert score.organic_matter == pytest.approx(50.0, abs=0.1)
    assert score.erosion == pytest.approx(100.0, abs=0.1)


def test_g4_erosion_weighted_runoff():
    """G4: erosión: W concentrado en un offset con cobertura 1.0 → 100; en offset de barbecho tras soya → 30."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="soya", sow_date="11-16"),
                ]
            )
        ]
    )
    # En hemisferio S: sow_date "11-16" tiene sow_offset = 138.
    # Ciclo de soya = 135 días (138 a 272).
    # L_ini = 20, L_dev = 30.
    # Cobertura plena (1.0) se alcanza a partir de offset 138 + 20 + 30 = 188 hasta 272.
    # Barbecho tras cosecha: a partir de offset 273 (rastrojo bajo = 0.3).

    # Caso 1: Escorrentía concentrada en día con cobertura plena (offset 200)
    w_plena = np.zeros(365, dtype=float)
    w_plena[200] = 50.0
    score_plena = calc_soil_score(rot, hemisphere="S", w_runoff=w_plena)
    assert score_plena.erosion == pytest.approx(100.0, abs=0.1)

    # Caso 2: Escorrentía concentrada en día de barbecho tras cosecha (offset 300)
    w_barbecho = np.zeros(365, dtype=float)
    w_barbecho[300] = 50.0
    score_barbecho = calc_soil_score(rot, hemisphere="S", w_runoff=w_barbecho)
    assert score_barbecho.erosion == pytest.approx(30.0, abs=0.1)


def test_soil_multiyear_rotation():
    """Rotación de 2 años: año 1 soya, año 2 maíz."""
    rot = Rotation(
        years=[
            RotationYear(slots=[SlotIn(crop_id="soya", sow_date="11-16")]),
            RotationYear(slots=[SlotIn(crop_id="maiz", sow_date="11-16")]),
        ]
    )
    score = calc_soil_score(rot, hemisphere="S")
    # L = 2 años
    # N_ano = (1/2) * (0.5 - 1.5) = -0.5
    # nitrogen = clip(60 + 20*(-0.5)) = 50.0
    assert score.nitrogen == pytest.approx(50.0, abs=0.1)
    # Familias distintas = 2 (Fabaceae, Poaceae) -> base 65
    # repite = 0 (pares: (soya, maiz) y (maiz, soya)) -> 65.0
    assert score.diversity == pytest.approx(65.0, abs=0.1)
    # pts: soya = 1, maiz = 3. Total pts = 4. Por año = 2.
    # organic_matter = 100 * (2 / 6) = 33.33
    assert score.organic_matter == pytest.approx(33.33, abs=0.1)


def test_soil_cover_crop_bonus():
    """Cultivo de cobertura no cosechable recibe bono de materia orgánica."""
    rot = Rotation(
        years=[
            RotationYear(
                slots=[
                    SlotIn(crop_id="crotalaria", sow_date="11-16"),
                ]
            )
        ]
    )
    # crotalaria: cobertura_leguminosa (N=2.0), rastrojo alto (pts=3), no cosechable (+1 bono)
    score = calc_soil_score(rot, hemisphere="S")
    # N_ano = 2.0 -> 60 + 20*(2.0) = 100.0
    assert score.nitrogen == pytest.approx(100.0, abs=0.1)
    # pts = 3 + 1 = 4 -> 100 * (4 / 6) = 66.67
    assert score.organic_matter == pytest.approx(66.67, abs=0.1)
