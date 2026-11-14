"""Tests para app.engine.calendar (PLAN §4.1, §6 C1–C4)."""

from datetime import date
from app.engine.calendar import (
    format_season_label,
    get_hemisphere,
    get_season_partitions,
    get_season_start_date,
    get_sow_offset,
    get_sowing_grid,
    get_valid_seasons,
    parse_sow_date,
)


def test_c1_parse_sow_date_south_spring():
    """C1: lat −17, campaña 2015, '11-16' → 2015-11-16."""
    hem = get_hemisphere(-17.0)
    assert hem == "S"
    assert parse_sow_date("11-16", 2015, hem) == date(2015, 11, 16)


def test_c2_parse_sow_date_south_autumn():
    """C2: lat −17, 2015, '04-16' → 2016-04-16."""
    hem = get_hemisphere(-17.0)
    assert hem == "S"
    assert parse_sow_date("04-16", 2015, hem) == date(2016, 4, 16)


def test_c3_parse_sow_date_north():
    """C3: lat 40, 2015, ambas → 2015."""
    hem = get_hemisphere(40.0)
    assert hem == "N"
    assert parse_sow_date("04-16", 2015, hem) == date(2015, 4, 16)
    assert parse_sow_date("11-16", 2015, hem) == date(2015, 11, 16)


def test_c4_valid_seasons_and_partitions():
    """C4: campañas válidas S = 1991..2024, N = 1992..2024; before S = 1991..2005, eval S = 2005..2024."""
    seasons_s = get_valid_seasons("S")
    assert seasons_s == list(range(1991, 2025))
    assert len(seasons_s) == 34

    seasons_n = get_valid_seasons("N")
    assert seasons_n == list(range(1992, 2025))
    assert len(seasons_n) == 33

    parts_s = get_season_partitions(seasons_s)
    assert parts_s["before"] == list(range(1991, 2006))
    assert len(parts_s["before"]) == 15

    assert parts_s["recent"] == list(range(2010, 2025))
    assert len(parts_s["recent"]) == 15

    assert parts_s["eval"] == list(range(2005, 2025))
    assert len(parts_s["eval"]) == 20


def test_get_hemisphere_boundary():
    """Verifica límites del hemisferio: lat < 0 es 'S', lat >= 0 es 'N'."""
    assert get_hemisphere(-0.0001) == "S"
    assert get_hemisphere(0.0) == "N"
    assert get_hemisphere(10.5) == "N"


def test_get_season_start_date():
    """Verifica fechas de inicio de campaña según hemisferio."""
    assert get_season_start_date(2020, "S") == date(2020, 7, 1)
    assert get_season_start_date(2020, "N") == date(2020, 1, 1)


def test_get_sowing_grid():
    """Verifica rejilla de 24 fechas quincenales ordenadas desde inicio de campaña."""
    grid_s = get_sowing_grid("S")
    assert len(grid_s) == 24
    assert grid_s[0] == "07-01"
    assert grid_s[1] == "07-16"
    assert grid_s[-2] == "06-01"
    assert grid_s[-1] == "06-16"

    grid_n = get_sowing_grid("N")
    assert len(grid_n) == 24
    assert grid_n[0] == "01-01"
    assert grid_n[1] == "01-16"
    assert grid_n[-2] == "12-01"
    assert grid_n[-1] == "12-16"


def test_get_sow_offset():
    """Verifica cálculo de offset en días en un año no bisiesto."""
    assert get_sow_offset("07-01", "S") == 0
    assert get_sow_offset("11-16", "S") == 138
    assert get_sow_offset("04-16", "S") == 289

    assert get_sow_offset("01-01", "N") == 0
    assert get_sow_offset("04-16", "N") == 105


def test_format_season_label():
    """Verifica formateo de etiquetas de campaña."""
    assert format_season_label(2015, "S") == "2015/16"
    assert format_season_label(1999, "S") == "1999/00"
    assert format_season_label(2024, "S") == "2024/25"
    assert format_season_label(2015, "N") == "2015"
