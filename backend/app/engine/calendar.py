"""PLAN §4.1 — Campaña agrícola, particiones y rejilla de siembra."""

from datetime import date, datetime, timedelta
from typing import Literal

from app.config import (
    DATA_END,
    DATA_START,
    DAYS_IN_YEAR,
    MAX_OVERRUN_DAYS,
    N_BEFORE,
    N_EVAL,
    N_RECENT,
    REFERENCE_NON_LEAP_YEAR,
    SPINUP_DAYS,
)


def get_hemisphere(lat: float) -> Literal["N", "S"]:
    """PLAN §4.1 — Retorna 'S' si lat < 0, si no 'N'."""
    return "S" if lat < 0 else "N"


def get_season_start_date(year: int, hemisphere: Literal["N", "S"]) -> date:
    """PLAN §4.1 — 1-jul si S, 1-ene si N."""
    return date(year, 7, 1) if hemisphere == "S" else date(year, 1, 1)


def get_valid_seasons(hemisphere: Literal["N", "S"]) -> list[int]:
    """PLAN §4.1 — Campañas válidas según inicio(y) - SPINUP_DAYS >= DATA_START y fin <= DATA_END."""
    start_bound = datetime.strptime(DATA_START, "%Y%m%d").date()
    end_bound = datetime.strptime(DATA_END, "%Y%m%d").date()

    min_year = start_bound.year - 2
    max_year = end_bound.year + 2

    valid: list[int] = []
    for y in range(min_year, max_year + 1):
        ini = get_season_start_date(y, hemisphere)
        has_spinup = (ini - timedelta(days=SPINUP_DAYS)) >= start_bound
        fits_dataset = (ini + timedelta(days=DAYS_IN_YEAR + MAX_OVERRUN_DAYS)) <= end_bound
        if has_spinup and fits_dataset:
            valid.append(y)

    return sorted(valid)


def parse_sow_date(sow_date_str: str, season: int, hemisphere: Literal["N", "S"]) -> date:
    """PLAN §4.1 — Convierte 'MM-DD' y campaña a objeto date."""
    parts = sow_date_str.split("-")
    month = int(parts[0])
    day = int(parts[1])

    if hemisphere == "N":
        return date(season, month, day)

    target_year = season if month >= 7 else season + 1
    return date(target_year, month, day)


def get_sowing_grid(hemisphere: Literal["N", "S"]) -> list[str]:
    """PLAN §4.1 — Rejilla de 24 fechas 'MM-DD' (días 01 y 16) ordenadas desde inicio de campaña."""
    start_month = 7 if hemisphere == "S" else 1
    grid: list[str] = []
    for i in range(12):
        month = (start_month - 1 + i) % 12 + 1
        grid.append(f"{month:02d}-01")
        grid.append(f"{month:02d}-16")
    return grid


def get_sow_offset(sow_date_str: str, hemisphere: Literal["N", "S"]) -> int:
    """PLAN §4.1 — Días desde inicio de campaña en un año no bisiesto."""
    sow_d = parse_sow_date(sow_date_str, REFERENCE_NON_LEAP_YEAR, hemisphere)
    ini_d = get_season_start_date(REFERENCE_NON_LEAP_YEAR, hemisphere)
    return (sow_d - ini_d).days


def get_season_partitions(seasons: list[int]) -> dict[str, list[int]]:
    """PLAN §4.1 — Retorna {'before': seasons[:15], 'recent': seasons[-15:], 'eval': seasons[-20:]}."""
    return {
        "before": seasons[:N_BEFORE],
        "recent": seasons[-N_RECENT:],
        "eval": seasons[-N_EVAL:],
    }


def format_season_label(season: int, hemisphere: Literal["N", "S"]) -> str:
    """PLAN §4.1 — f'{season}/{(season+1)%100:02d}' si S else f'{season}'."""
    return f"{season}/{(season + 1) % 100:02d}" if hemisphere == "S" else f"{season}"
