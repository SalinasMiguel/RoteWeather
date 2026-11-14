"""PLAN §6 — Tests de factores térmicos y aptitud climática (H1–H4)."""

import numpy as np
import pytest

from app.engine.slot import (
    calc_frost_factor,
    calc_heat_factor,
    calc_temp_factor,
    calc_trapezoid,
)


def test_h1_trapezoid():
    """H1: trapecio(10/20/33/38): x=15->0.5, 25->1.0, 35.5->0.5, 40->0.0."""
    a, b, c, d = 10.0, 20.0, 33.0, 38.0

    assert calc_trapezoid(15.0, a, b, c, d) == pytest.approx(0.5, abs=1e-9)
    assert calc_trapezoid(25.0, a, b, c, d) == pytest.approx(1.0, abs=1e-9)
    assert calc_trapezoid(35.5, a, b, c, d) == pytest.approx(0.5, abs=1e-9)
    assert calc_trapezoid(40.0, a, b, c, d) == pytest.approx(0.0, abs=1e-9)

    # Fronteras y valores fuera de rango
    assert calc_trapezoid(10.0, a, b, c, d) == pytest.approx(0.0, abs=1e-9)
    assert calc_trapezoid(20.0, a, b, c, d) == pytest.approx(1.0, abs=1e-9)
    assert calc_trapezoid(33.0, a, b, c, d) == pytest.approx(1.0, abs=1e-9)
    assert calc_trapezoid(38.0, a, b, c, d) == pytest.approx(0.0, abs=1e-9)
    assert calc_trapezoid(5.0, a, b, c, d) == pytest.approx(0.0, abs=1e-9)

    # Vectorizado sobre array
    x_arr = np.array([15.0, 25.0, 35.5, 40.0])
    res_arr = calc_trapezoid(x_arr, a, b, c, d)
    assert isinstance(res_arr, np.ndarray)
    assert np.allclose(res_arr, [0.5, 1.0, 0.5, 0.0])


def test_h2_heat_factor():
    """H2: tmax constante = Tcrit -> f_calor=1; = Tlim -> 0; punto medio -> 0.5."""
    tcrit = 35.0
    tlim = 40.0

    # 1. Constante Tcrit
    tmax_tcrit = np.full(30, tcrit)
    assert calc_heat_factor(tmax_tcrit, tcrit, tlim) == pytest.approx(1.0, abs=1e-9)

    # 2. Constante Tlim
    tmax_tlim = np.full(30, tlim)
    assert calc_heat_factor(tmax_tlim, tcrit, tlim) == pytest.approx(0.0, abs=1e-9)

    # 3. Constante punto medio (37.5)
    tmax_mid = np.full(30, 37.5)
    assert calc_heat_factor(tmax_mid, tcrit, tlim) == pytest.approx(0.5, abs=1e-9)

    # 4. Debajo de Tcrit
    tmax_low = np.full(30, 30.0)
    assert calc_heat_factor(tmax_low, tcrit, tlim) == pytest.approx(1.0, abs=1e-9)

    # 5. Ventana sensible vacía
    tmax_empty = np.zeros(0)
    assert calc_heat_factor(tmax_empty, tcrit, tlim) == pytest.approx(1.0, abs=1e-9)


def test_h3_frost_factor():
    """H3: tmin=-1 en sens -> 0.3; tmin=-4 fuera de sens -> 0.7; tmin=-1 solo fuera -> 1.0."""
    t_helada = 0.0
    n_days = 100
    sens_start, sens_end = 40, 70

    # Caso 1: tmin = -1 dentro de sens (helada en floración)
    tmin_cycle_1 = np.full(n_days, 15.0)
    tmin_cycle_1[50] = -1.0
    tmin_sens_1 = tmin_cycle_1[sens_start:sens_end]
    assert calc_frost_factor(tmin_sens_1, tmin_cycle_1, t_helada) == pytest.approx(0.3, abs=1e-9)

    # Caso 2: tmin = -4 fuera de sens (y >= 0 dentro)
    tmin_cycle_2 = np.full(n_days, 15.0)
    tmin_cycle_2[10] = -4.0
    tmin_sens_2 = tmin_cycle_2[sens_start:sens_end]
    assert calc_frost_factor(tmin_sens_2, tmin_cycle_2, t_helada) == pytest.approx(0.7, abs=1e-9)

    # Caso 3: tmin = -1 solo fuera de sens (y >= 0 dentro)
    # Como -1 >= t_helada - 3.0 (-3.0), no califica como helada severa vegetativa
    tmin_cycle_3 = np.full(n_days, 15.0)
    tmin_cycle_3[10] = -1.0
    tmin_sens_3 = tmin_cycle_3[sens_start:sens_end]
    assert calc_frost_factor(tmin_sens_3, tmin_cycle_3, t_helada) == pytest.approx(1.0, abs=1e-9)

    # Caso 4: Precedencia estricta: helada en sens (-1.0) y helada severa en ciclo (-5.0)
    tmin_cycle_4 = np.full(n_days, 15.0)
    tmin_cycle_4[50] = -1.0
    tmin_cycle_4[10] = -5.0
    tmin_sens_4 = tmin_cycle_4[sens_start:sens_end]
    assert calc_frost_factor(tmin_sens_4, tmin_cycle_4, t_helada) == pytest.approx(0.3, abs=1e-9)


def test_h4_no_thermal_stress():
    """H4: Sin calor ni frío -> f_calor = 1.0, f_helada = 1.0."""
    tcrit = 35.0
    tlim = 40.0
    t_helada = 0.0

    tmax_sens = np.full(30, 28.0)
    assert calc_heat_factor(tmax_sens, tcrit, tlim) == pytest.approx(1.0, abs=1e-9)

    tmin_sens = np.full(30, 15.0)
    tmin_cycle = np.full(100, 12.0)
    assert calc_frost_factor(tmin_sens, tmin_cycle, t_helada) == pytest.approx(1.0, abs=1e-9)


def test_h5_vectorized_thermal_factors():
    """Validación de consistencia vectorizada vs escalar sobre múltiples campañas."""
    m = 3
    n_cycle = 50
    t_ecocrop = [10.0, 20.0, 33.0, 38.0]
    tcrit, tlim = 35.0, 40.0
    t_helada = 0.0

    # 3 campañas: camp 0 óptima, camp 1 calor extremo, camp 2 helada en sens
    tmax_mat = np.full((n_cycle, m), 25.0)
    tmin_mat = np.full((n_cycle, m), 15.0)

    # Camp 1: calor en floración (días 20..30)
    tmax_mat[20:30, 1] = 40.0

    # Camp 2: helada en floración (día 25)
    tmin_mat[25, 2] = -2.0

    tmean_mat = (tmax_mat + tmin_mat) / 2.0
    f_temp_vec = calc_temp_factor(tmean_mat, t_ecocrop)
    f_calor_vec = calc_heat_factor(tmax_mat[20:30, :], tcrit, tlim)
    f_helada_vec = calc_frost_factor(tmin_mat[20:30, :], tmin_mat, t_helada)

    for i in range(m):
        f_temp_s = calc_temp_factor(tmean_mat[:, i], t_ecocrop)
        f_calor_s = calc_heat_factor(tmax_mat[20:30, i], tcrit, tlim)
        f_helada_s = calc_frost_factor(tmin_mat[20:30, i], tmin_mat[:, i], t_helada)

        assert f_temp_vec[i] == pytest.approx(f_temp_s, abs=1e-9)
        assert f_calor_vec[i] == pytest.approx(f_calor_s, abs=1e-9)
        assert f_helada_vec[i] == pytest.approx(f_helada_s, abs=1e-9)
