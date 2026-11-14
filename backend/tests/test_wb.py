"""PLAN §6 — Tests de balance hídrico y escorrentía (W1–W4)."""

import numpy as np
import pytest

from app.engine.slot import calc_runoff, wb_step


def test_w1_runoff_scs_cn():
    """W1: runoff(50, 78) = 11.86 ± 0.05, runoff(10, 78) = 0.0."""
    ro_50 = calc_runoff(50.0, 78.0)
    assert ro_50 == pytest.approx(11.86, abs=0.05)

    ro_10 = calc_runoff(10.0, 78.0)
    assert ro_10 == pytest.approx(0.0, abs=1e-9)

    # Vectorizado sobre array de precipitaciones
    prec_arr = np.array([50.0, 10.0, 0.0])
    ro_arr = calc_runoff(prec_arr, 78.0)
    assert isinstance(ro_arr, np.ndarray)
    assert ro_arr[0] == pytest.approx(11.86, abs=0.05)
    assert ro_arr[1] == pytest.approx(0.0, abs=1e-9)
    assert ro_arr[2] == pytest.approx(0.0, abs=1e-9)


def test_w2_constant_rain_no_stress():
    """W2: Lluvia 10 mm/día, et0 5 -> Ks=1 siempre, ratio=1."""
    taw = 150.0
    cn = 78.0
    dr = 0.5 * taw
    kc = 1.0
    p_tab = 0.5
    prec = 10.0
    et0 = 5.0

    sum_eta = 0.0
    sum_etc = 0.0

    for day in range(100):
        dr, eta, etc, pe, ro, dp, ks = wb_step(
            dr=dr,
            prec=prec,
            et0=et0,
            kc=kc,
            p_tab=p_tab,
            taw=taw,
            cn=cn,
        )
        assert ks == pytest.approx(1.0, abs=1e-9)
        assert eta == pytest.approx(etc, abs=1e-9)
        sum_eta += eta
        sum_etc += etc

    ratio = sum_eta / sum_etc
    assert ratio == pytest.approx(1.0, abs=1e-9)


def test_w3_mass_balance_closure():
    """W3: Cierre de balance de masa en 200 días aleatorios (semilla fija).

    Dr_fin = Dr_0 - ΣPe + ΣETa + ΣDP ± 1e-6.
    """
    rng = np.random.default_rng(20261113)
    taw = 155.0
    cn = 78.0
    dr_0 = 0.5 * taw
    dr = dr_0

    sum_pe = 0.0
    sum_eta = 0.0
    sum_dp = 0.0

    for _ in range(200):
        prec = float(rng.uniform(0.0, 30.0))
        et0 = float(rng.uniform(1.0, 7.0))
        kc = float(rng.uniform(0.2, 1.2))
        p_tab = 0.5

        dr, eta, etc, pe, ro, dp, ks = wb_step(
            dr=dr,
            prec=prec,
            et0=et0,
            kc=kc,
            p_tab=p_tab,
            taw=taw,
            cn=cn,
        )
        sum_pe += pe
        sum_eta += eta
        sum_dp += dp

    expected_dr_fin = dr_0 - sum_pe + sum_eta + sum_dp
    assert dr == pytest.approx(expected_dr_fin, abs=1e-6)


def test_w4_small_rain_cutoff():
    """W4: prec = 0.5 mm con et0 = 5.0 -> Pe = 0 (corte por lluvia pequeña)."""
    dr = 50.0
    prec = 0.5
    et0 = 5.0
    kc = 1.0
    p_tab = 0.5
    taw = 150.0
    cn = 78.0

    dr_new, eta, etc, pe, ro, dp, ks = wb_step(
        dr=dr,
        prec=prec,
        et0=et0,
        kc=kc,
        p_tab=p_tab,
        taw=taw,
        cn=cn,
    )
    # 0.5 < SMALL_RAIN_FRAC (0.2) * 5.0 = 1.0 -> Pe = 0.0
    assert pe == pytest.approx(0.0, abs=1e-9)
    assert ro == pytest.approx(0.0, abs=1e-9)


def test_w5_vectorized_wb_step():
    """Validación de consistencia vectorizada vs escalar sobre múltiples campañas."""
    m = 5
    dr = np.array([10.0, 30.0, 50.0, 70.0, 90.0])
    prec = np.array([0.0, 5.0, 15.0, 30.0, 50.0])
    et0 = np.array([4.0, 5.0, 6.0, 5.0, 4.0])
    kc = np.array([0.4, 0.8, 1.15, 1.0, 0.5])
    p_tab = np.full(m, 0.5)
    taw = np.full(m, 155.0)
    cn = np.full(m, 78.0)

    dr_vec, eta_vec, etc_vec, pe_vec, ro_vec, dp_vec, ks_vec = wb_step(
        dr=dr,
        prec=prec,
        et0=et0,
        kc=kc,
        p_tab=p_tab,
        taw=taw,
        cn=cn,
    )

    for i in range(m):
        dr_s, eta_s, etc_s, pe_s, ro_s, dp_s, ks_s = wb_step(
            dr=float(dr[i]),
            prec=float(prec[i]),
            et0=float(et0[i]),
            kc=float(kc[i]),
            p_tab=float(p_tab[i]),
            taw=float(taw[i]),
            cn=float(cn[i]),
        )
        assert dr_vec[i] == pytest.approx(dr_s, abs=1e-9)
        assert eta_vec[i] == pytest.approx(eta_s, abs=1e-9)
        assert etc_vec[i] == pytest.approx(etc_s, abs=1e-9)
        assert pe_vec[i] == pytest.approx(pe_s, abs=1e-9)
        assert ro_vec[i] == pytest.approx(ro_s, abs=1e-9)
        assert dp_vec[i] == pytest.approx(dp_s, abs=1e-9)
        assert ks_vec[i] == pytest.approx(ks_s, abs=1e-9)
