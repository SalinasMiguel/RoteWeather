"""PLAN §2.1 y §2.2 — Esquemas Pydantic y contratos de la API RotaClima.

Definiciones de entrada y salida para /analyze conformes a Pydantic v2.
"""

from typing import Literal
from pydantic import BaseModel, Field, constr

# ==============================================================================
# §2.1 /analyze request
# ==============================================================================

# "MM-DD", solo días 01 o 16 (quincenas de siembra)
SowDate = constr(pattern=r"^(0[1-9]|1[0-2])-(01|16)$")


class SlotIn(BaseModel):
    crop_id: str  # debe existir en crops.json
    sow_date: SowDate


class RotationYear(BaseModel):
    slots: list[SlotIn] = Field(..., min_length=1, max_length=2)  # 1..2 slots por año


class Rotation(BaseModel):
    years: list[RotationYear] = Field(..., min_length=1, max_length=3)  # 1..3 años de ciclo


class AnalyzeRequest(BaseModel):
    lat: float = Field(..., ge=-60.0, le=60.0)  # -60..60
    lon: float = Field(..., ge=-180.0, le=180.0)  # -180..180
    soil_texture: Literal["arenoso", "franco", "arcilloso"] = "franco"
    current_rotation: Rotation
    include_diversified: bool = False


# ==============================================================================
# §2.2 /analyze response
# ==============================================================================


class Source(BaseModel):
    dataset: str  # "NASA POWER (MERRA-2 / CERES SYN1deg)"
    parameters: list[str]  # ["PRECTOTCORR", ...] nombres EXACTOS de POWER
    period: str  # "campañas 2005/06–2024/25"


class Evidence(BaseModel):
    label: str  # "Campañas malas"
    value: float | str
    unit: str  # "de 20", "mm", "días", "%", ""
    source: Source


class Claim(BaseModel):
    text: str  # Todo número del texto debe existir en evidence[].value
    evidence: list[Evidence] = Field(..., min_length=1)  # >= 1


class SoilScore(BaseModel):
    total: float  # 0..100
    nitrogen: float
    diversity: float
    erosion: float
    organic_matter: float


class SlotOut(BaseModel):
    crop_id: str
    crop_name: str
    family: str
    harvested: bool
    sow_date: str  # "MM-DD"
    sow_offset: int  # días desde inicio de campaña (año no bisiesto)
    stage_ends: list[int]  # 4 offsets acumulados: fin ini, dev, mid, late(=cosecha)
    sens_window: tuple[int, int]  # offsets [inicio, fin)
    prev_mode: Literal["fallow", "crop"]
    mean_yield: float  # media Y_rel en ventana eval, 0..1
    failures: int  # campañas eval con Y_rel < SLOT_FAIL


class SeasonOut(BaseModel):
    season: int  # año de inicio de campaña
    label: str  # "2015/16" (sur) o "2015" (norte)
    index: float  # I_y 0..1
    productivity: float  # P_y
    bad: bool
    limiting: Literal["agua", "calor", "helada", "temperatura", "ninguno"]


class RotationMetrics(BaseModel):
    mean_index: float  # media I en eval
    p10_index: float
    mean_productivity: float  # media P en eval
    productivity_vs_current: float  # 100 = igual a la actual
    bad_seasons: int
    n_seasons: int  # en eval (n=20)
    bad_before: int
    bad_recent: int
    n_period: int  # n=15 c/u
    soil: SoilScore


class RotationCard(BaseModel):
    profile: Literal["actual", "adaptada", "regenerativa", "diversificada"]
    title: str
    why: list[Claim]
    benefits: list[Claim]
    risks: list[Claim]
    changes_vs_current: list[str]
    relaxed_constraints: list[str]  # vacío si la selección no relajó nada
    improves_on_current: bool


class RotationResult(BaseModel):
    profile: str
    rotation: Rotation
    slots: list[list[SlotOut]]  # por año de la rotación
    metrics: RotationMetrics
    seasons: list[SeasonOut]  # TODAS las campañas válidas (no solo eval)
    card: RotationCard


class ClimateMetric(BaseModel):
    id: str  # ver §4.8
    label: str
    unit: str
    before: float
    recent: float
    delta: float
    p_value: float | None  # Mann-Whitney bilateral
    significant: bool  # p < 0.10
    series: list[tuple[int, float | None]]  # (campaña, valor)
    source: Source


class Climatology(BaseModel):  # 24 quincenas desde el inicio de campaña
    rain_mm: list[float]
    et0_mm: list[float]
    tmax_c: list[float]
    tmin_c: list[float]


class Meta(BaseModel):
    lat: float
    lon: float
    elevation_m: float
    hemisphere: Literal["N", "S"]
    ag_year_start: str  # "07-01" | "01-01"
    seasons: list[int]
    periods: dict[str, tuple[int, int]]  # before / recent / eval -> (primera, última campaña)
    et0_hargreaves_share: float  # fracción de días con fallback
    resolution_note: str  # "POWER ≈ 0.5°×0.625° (≈50 km): clima regional, no de parcela"
    assumptions: list[str]  # textos de §4.10


class AnalyzeResponse(BaseModel):
    meta: Meta
    climate: list[ClimateMetric]
    climatology: dict[Literal["before", "recent"], Climatology]
    rotations: list[RotationResult]  # orden fijo: actual, adaptada, regenerativa[, diversificada]
