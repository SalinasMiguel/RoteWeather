"""PLAN §4.0 — Constantes centralizadas del motor de simulación.

Única fuente de verdad para parámetros numéricos y umbrales agronómicos/climáticos.
AGENTS.md: Prohibido un literal mágico en engine/.
"""

# Fechas y límites de consulta a NASA POWER (§2.3, §4.1)
DATA_START: str = "19910101"
DATA_END: str = "20251231"

# Ventanas de análisis en número de campañas (§4.1)
N_BEFORE: int = 15
N_RECENT: int = 15
N_EVAL: int = 20

# Días de spin-up y manejo previo del balance hídrico (§4.1, §4.4)
SPINUP_DAYS: int = 180
PRE_CROP_DAYS: int = 120

# Coeficientes Kc durante el periodo de spin-up (supuesto S2, §4.4)
KC_FALLOW: float = 0.20
KC_PRE_CROP: float = 0.90

# Fracción de agotamiento inicial de TAW al inicio del spin-up (§4.4)
DR0_FRAC: float = 0.5

# Restricciones temporales de rotación en días (§4.1, §4.6)
GAP_CROP_MAX_DAYS: int = 30
TURNAROUND_DAYS: int = 10
MAX_OVERRUN_DAYS: int = 183

# Capacidad de agua disponible (AWC) en mm/m según textura (FAO-56 Tabla 19, §4.4)
AWC_MM_PER_M: dict[str, int] = {
    "arenoso": 80,
    "franco": 155,
    "arcilloso": 160,
}

# Número de curva (CN) para cálculo de escorrentía SCS-CN (USDA TR-55, §4.4)
CN: dict[str, int] = {
    "arenoso": 67,
    "franco": 78,
    "arcilloso": 85,
}

# Límites del factor de agotamiento de agua fácilmente disponible p (§4.4)
P_MIN: float = 0.1
P_MAX: float = 0.8

# Umbral de lluvia pequeña como fracción de ET0 (FAO-56 cap. 8, §4.4)
SMALL_RAIN_FRAC: float = 0.2

# Ventana sensible a floración en días respecto al inicio de etapa mid (§4.3)
SENS_BEFORE: int = 5
SENS_AFTER: int = 25

# Factores de penalización por helada y offset térmico (supuesto S6, §4.5)
F_FROST_SENS: float = 0.3
F_FROST_VEG: float = 0.7
FROST_VEG_OFFSET: float = 3.0

# Umbrales de clasificación de riesgo y falla (§4.6)
BAD_SEASON_I: float = 0.60
SLOT_FAIL: float = 0.50

# Umbrales para perfil y métricas climáticas (§4.8)
DRY_DAY_MM: float = 1.0
HOT_DAY_C: float = 35.0
DRY_SPELL_DAYS: int = 10
GDD_BASE: float = 10.0

# Detección de inicio de lluvias (onset, §4.8)
ONSET_MM: float = 20.0
ONSET_WINDOW: int = 3
ONSET_LOOKAHEAD: int = 30
ONSET_SEARCH_START: int = 62

# Detección de cese de lluvias (cessation, §4.8)
CESS_MIN_AFTER_ONSET: int = 60
CESS_WINDOW: int = 20
CESS_MM: float = 10.0

# Ponderaciones para cálculo de puntaje de suelo (§4.7)
N_POINTS: dict[str, float] = {
    "cobertura_leguminosa": 2.0,
    "leguminosa_grano": 0.5,
    "cobertura_no_leguminosa": 0.5,
    "extractiva": -1.0,
    "muy_extractiva": -1.5,
}

RESIDUE_POINTS: dict[str, int] = {
    "bajo": 1,
    "medio": 2,
    "alto": 3,
}
COVER_CROP_BONUS: int = 1

RESIDUE_COVER: dict[str, float] = {
    "bajo": 0.3,
    "medio": 0.5,
    "alto": 0.8,
}

DIVERSITY_BASE: dict[int, int] = {
    1: 30,
    2: 65,
    3: 85,
}  # >= 4 familias -> 100

# Umbrales de viabilidad y selección de alternativas (§5.1, §5.2, §5.3)
VIABLE_MIN: float = 0.50
VIABLE_MIN_COVER: float = 0.40

ADAPT_MIN_PROD: float = 0.95
REGEN_MAX_LOSS: float = 0.20
REGEN_MAX_LOSS_RELAXED: float = 0.30
REGEN_MIN_SOIL_GAIN: int = 10
REGEN_MIN_SOIL_GAIN_RELAXED: int = 1
IMPROVE_PROD_RATIO: float = 1.02

CANDIDATE_TOP_PERF: int = 30
CANDIDATE_TOP_SOIL: int = 10

DIVERSIFIED_MIN_FAMILIES: int = 3
DIVERSIFIED_MIN_CROPS: int = 3
DIVERSIFIED_CYCLE_YEARS: int = 2

# Umbrales para plantillas de fichas de rotación (PLAN §4.9)
PROD_CHANGE_UPPER_RATIO: float = 102.0
CARD_BENEFIT_PROD_MIN: float = PROD_CHANGE_UPPER_RATIO

PROD_CHANGE_LOWER_RATIO: float = 98.0
CARD_RISK_PROD_MAX: float = PROD_CHANGE_LOWER_RATIO

EROSION_DIFF_THRESHOLD: float = 5.0
CARD_EROSION_DIFF_MIN: float = EROSION_DIFF_THRESHOLD

REGIONAL_RESOLUTION_KM: int = 50
CARD_RESOLUTION_KM: int = REGIONAL_RESOLUTION_KM

MAX_WORST_SEASONS_REPORT: int = 3
CARD_MAX_WORST_SEASONS: int = MAX_WORST_SEASONS_REPORT

MAX_SCORE_POINTS: int = 100
CARD_BAD_SEASON_THRESHOLD_PERCENT: int = 60
CARD_REGEN_LOSS_INITIAL_PERCENT: int = 20
CARD_REGEN_LOSS_RELAXED_PERCENT: int = 30

# Supuestos y metadatos del pipeline (PLAN §4.10)
RESOLUTION_NOTE: str = (
    "POWER ≈ 0.5°×0.625° (≈50 km): clima regional, no de parcela"
)

ASSUMPTIONS: list[str] = [
    "S1. POWER es reanálisis a ≈50 km (MERRA-2) y 1° (radiación CERES): clima regional. Tmax tiende a quedar por debajo de estaciones; los conteos de días >35 °C son conservadores.",
    "S2. Agua inicial: spin-up de 180 días con Kc fijo de barbecho (0.20) o de cultivo previo (0.90). No se simula el cultivo anterior real.",
    "S3. Fenología por días calendario; Kc sin ajuste por humedad/viento; sin fotoperiodo.",
    "S4. El puntaje de suelo no modifica el rendimiento simulado.",
    "S5. Se asume siembra directa.",
    "S6. Helada: regla escalón (0.3 en floración, 0.7 vegetativa).",
    "S7. Umbrales de calor fuera de Teixeira 2013: derivados de ECOCROP.",
    "S8. Clases de N y rastrojo: conocimiento agronómico general, no medición.",
    "S9. Cultivos de cobertura: parámetros por analogía.",
    "S10. Rendimiento relativo al potencial; sin precios. value_weight = 1 para todos salvo que el usuario lo cambie.",
    "S11. Un balde de suelo; no se modela anegamiento, plagas, malezas ni fallas de emergencia.",
    "S12. Las tendencias de lluvia en reanálisis pueden incluir artefactos del sistema de observación; por eso se reporta p_value y se dice \"no significativo\" cuando corresponde.",
]

# Constantes auxiliares del motor de simulación (AGENTS.md: cero literales mágicos en engine/)
DAYS_IN_YEAR: int = 365
REFERENCE_NON_LEAP_YEAR: int = 2001

LIMITING_THRESHOLD: float = 0.95
TOLERANCE_TIE: float = 1e-9
PERCENT_BASE: float = 100.0
P10_PERCENTILE: float = 10.0

N_BASE: float = 60.0
N_SCALE: float = 20.0
SCORE_MIN: float = 0.0
SCORE_MAX: float = 100.0
OM_MAX_PTS: float = 6.0
COMPONENT_WEIGHT: float = 0.25
REPEAT_PENALTY: float = 0.5
COVER_FULL: float = 1.0

SIGNIFICANCE_ALPHA: float = 0.10
MIN_OBS_MANNWHITNEY: int = 5
Q1_END: int = 91
Q2_END: int = 182
Q3_END: int = 273
MONTHS_IN_YEAR: int = 12
FORTNIGHTS_IN_YEAR: int = 24
