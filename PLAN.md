# RotaClima — PLAN.md

Motor de simulación explicable (sin ML, sin chatbot) que compara la rotación actual de un agricultor contra 2-3 alternativas usando ~34 campañas reales de NASA POWER. Challenge: NASA Space Apps "Field Shift".
Supuestos de proyecto: 48 h, 1 persona + agentes. Prioridad: correcto y demostrable > complejidad > estética.

**Normativo:** §2 (contratos) y §4 (fórmulas) no se modifican durante la implementación. Si algo parece mal, se anota en `QUESTIONS.md` y se detiene la tarea.

## 0. Decisiones (una línea cada una)

- Frontend **Vite + React + TS** (no Next): no hay SSR ni rutas de servidor; menos superficie para agentes.
- Gráficos **Recharts**, mapa **react-leaflet**: API declarativa, ejemplos abundantes.
- Fichas por **plantillas deterministas** (no LLM): cero riesgo de cifras inventadas; LLM solo como extra de redacción.
- ET0 **Penman-Monteith** por defecto, **Hargreaves** por día cuando falte RH/viento/radiación.
- Un solo balde de suelo (sin capas): suficiente para ranking relativo, testeable a mano.
- Fenología por **días calendario** (FAO-56 Tabla 11), no por grados-día: menos parámetros no verificables.
- Caché: respuesta cruda de POWER en JSON en disco; sin base de datos.

## 1. Estructura del repo

```
rotaclima/
├── AGENTS.md
├── PLAN.md
├── QUESTIONS.md                  # dudas de agentes; no se resuelven improvisando
├── README.md
├── backend/
│   ├── pyproject.toml            # fastapi, uvicorn, pydantic>=2, numpy, pandas, scipy, httpx, pytest
│   ├── app/
│   │   ├── main.py               # FastAPI: POST /analyze, GET /crops, GET /health
│   │   ├── config.py             # TODAS las constantes de §4.0 (única fuente)
│   │   ├── schemas.py            # Pydantic de §2
│   │   ├── data/
│   │   │   ├── crops.json        # §2.3
│   │   │   └── crops.py          # loader + validación
│   │   ├── nasa/
│   │   │   ├── power.py          # cliente + caché
│   │   │   └── modis.py          # extra
│   │   ├── engine/
│   │   │   ├── calendar.py       # campaña agrícola, fechas, rejilla de siembra
│   │   │   ├── et0.py            # Ra, Penman-Monteith, Hargreaves
│   │   │   ├── crop.py           # curva Kc, etapas, ventana sensible
│   │   │   ├── slot.py           # simulate_slot (balance hídrico + térmico)
│   │   │   ├── table.py          # SlotTable memoizada
│   │   │   ├── rotation.py       # evaluación de rotación, métricas, año malo
│   │   │   ├── soil.py           # puntaje de suelo
│   │   │   ├── climate.py        # perfil antes/ahora
│   │   │   ├── alternatives.py   # enumeración + selección de perfiles
│   │   │   └── cards.py          # fichas por plantilla
│   │   └── pipeline.py           # analyze(request) -> AnalyzeResponse
│   ├── cache/                    # .gitignore
│   ├── scripts/
│   │   ├── fetch_fixture.py      # baja POWER del punto demo -> tests/fixtures
│   │   └── precache_demo.py      # genera frontend/public/demo_santa_cruz.json
│   └── tests/
│       ├── fixtures/power_demo.json
│       └── test_*.py
├── notebooks/
│   └── 01_validacion_motor.ipynb # puerta go/no-go antes de la UI
├── contracts/
│   └── analyze_response.example.json   # fixture escrito a mano; el frontend arranca contra esto
└── frontend/
    ├── package.json  vite.config.ts
    ├── public/demo_santa_cruz.json
    └── src/
        ├── types.ts              # espejo manual de schemas.py
        ├── api.ts                # fetch /analyze + fallback a demo estático
        ├── App.tsx               # estado + navegación de 3 vistas
        └── views/ MapForm.tsx  ClimateShift.tsx  Compare.tsx
            components/ RotationEditor.tsx MetricDelta.tsx CompareTable.tsx RotationCard.tsx CalendarChart.tsx
```

## 2. Contratos

### 2.1 `/analyze` request

```python
SowDate = constr(pattern=r"^(0[1-9]|1[0-2])-(01|16)$")   # "MM-DD", solo días 01 o 16 (quincenas)

class SlotIn(BaseModel):
    crop_id: str                 # debe existir en crops.json
    sow_date: SowDate

class RotationYear(BaseModel):
    slots: list[SlotIn]          # 1..2, en orden cronológico DENTRO de la campaña agrícola

class Rotation(BaseModel):
    years: list[RotationYear]    # 1..3 (duración del ciclo en años)

class AnalyzeRequest(BaseModel):
    lat: float                   # -60..60
    lon: float                   # -180..180
    soil_texture: Literal["arenoso","franco","arcilloso"] = "franco"
    current_rotation: Rotation
    include_diversified: bool = False
```

Validación (HTTP 422 con mensaje en español): crop_id inexistente; slots solapados o sin `TURNAROUND_DAYS` entre cosecha y siguiente siembra (cíclico, §4.6); rotación sin ningún cultivo cosechable.

Ejemplo demo: `{"lat":-17.30,"lon":-62.25,"soil_texture":"franco","current_rotation":{"years":[{"slots":[{"crop_id":"soya","sow_date":"11-16"},{"crop_id":"soya","sow_date":"05-01"}]}]}}`

### 2.2 `/analyze` response

```python
class Source(BaseModel):
    dataset: str                 # "NASA POWER (MERRA-2 / CERES SYN1deg)"
    parameters: list[str]        # ["PRECTOTCORR", ...] nombres EXACTOS de POWER
    period: str                  # "campañas 2005/06–2024/25"

class Evidence(BaseModel):
    label: str                   # "Campañas malas"
    value: float | str
    unit: str                    # "de 20", "mm", "días", "%", ""
    source: Source

class Claim(BaseModel):
    text: str                    # TODO número del texto debe existir en evidence[].value
    evidence: list[Evidence]     # >=1

class SoilScore(BaseModel):
    total: float                 # 0..100
    nitrogen: float; diversity: float; erosion: float; organic_matter: float

class SlotOut(BaseModel):
    crop_id: str; crop_name: str; family: str; harvested: bool
    sow_date: str                # "MM-DD"
    sow_offset: int              # días desde inicio de campaña (año no bisiesto)
    stage_ends: list[int]        # 4 offsets acumulados: fin ini, dev, mid, late(=cosecha)
    sens_window: tuple[int,int]  # offsets [inicio, fin)
    prev_mode: Literal["fallow","crop"]
    mean_yield: float            # media Y_rel en ventana eval, 0..1
    failures: int                # campañas eval con Y_rel < SLOT_FAIL

class SeasonOut(BaseModel):
    season: int                  # año de inicio de campaña
    label: str                   # "2015/16" (sur) o "2015" (norte)
    index: float                 # I_y 0..1
    productivity: float          # P_y
    bad: bool
    limiting: Literal["agua","calor","helada","temperatura","ninguno"]

class RotationMetrics(BaseModel):
    mean_index: float            # media I en eval
    p10_index: float
    mean_productivity: float     # media P en eval
    productivity_vs_current: float   # 100 = igual a la actual
    bad_seasons: int; n_seasons: int # en eval (n=20)
    bad_before: int; bad_recent: int; n_period: int   # n=15 c/u
    soil: SoilScore

class RotationCard(BaseModel):
    profile: Literal["actual","adaptada","regenerativa","diversificada"]
    title: str
    why: list[Claim]; benefits: list[Claim]; risks: list[Claim]
    changes_vs_current: list[str]
    relaxed_constraints: list[str]   # vacío si la selección no relajó nada
    improves_on_current: bool

class RotationResult(BaseModel):
    profile: str
    rotation: Rotation
    slots: list[list[SlotOut]]   # por año de la rotación
    metrics: RotationMetrics
    seasons: list[SeasonOut]     # TODAS las campañas válidas (no solo eval)
    card: RotationCard

class ClimateMetric(BaseModel):
    id: str                      # ver §4.8
    label: str; unit: str
    before: float; recent: float; delta: float
    p_value: float | None        # Mann-Whitney bilateral
    significant: bool            # p < 0.10
    series: list[tuple[int, float | None]]   # (campaña, valor)
    source: Source

class Climatology(BaseModel):   # 24 quincenas desde el inicio de campaña
    rain_mm: list[float]; et0_mm: list[float]; tmax_c: list[float]; tmin_c: list[float]

class Meta(BaseModel):
    lat: float; lon: float; elevation_m: float
    hemisphere: Literal["N","S"]; ag_year_start: str      # "07-01" | "01-01"
    seasons: list[int]
    periods: dict[str, tuple[int,int]]    # before / recent / eval -> (primera, última campaña)
    et0_hargreaves_share: float           # fracción de días con fallback
    resolution_note: str                  # "POWER ≈ 0.5°×0.625° (≈50 km): clima regional, no de parcela"
    assumptions: list[str]                # textos de §4.10

class AnalyzeResponse(BaseModel):
    meta: Meta
    climate: list[ClimateMetric]
    climatology: dict[Literal["before","recent"], Climatology]
    rotations: list[RotationResult]       # orden fijo: actual, adaptada, regenerativa[, diversificada]
```

### 2.3 Cliente POWER

```python
def fetch_power(lat: float, lon: float, start: str = DATA_START, end: str = DATA_END) -> PowerData

@dataclass
class PowerData:
    lat: float; lon: float; elevation_m: float
    df: pd.DataFrame      # índice DatetimeIndex diario continuo; columnas float con NaN (nunca -999)
    api_version: str
```

- URL: `https://power.larc.nasa.gov/api/temporal/daily/point`
- Query: `parameters=PRECTOTCORR,T2M,T2M_MAX,T2M_MIN,RH2M,ALLSKY_SFC_SW_DWN,WS2M,GWETTOP,GWETROOT,PS&community=AG&longitude={lon}&latitude={lat}&start=YYYYMMDD&end=YYYYMMDD&format=JSON` (**VERIFICADO**)
- Respuesta: `properties.parameter[PARAM][YYYYMMDD] -> float`; `header.fill_value == -999.0`; `geometry.coordinates == [lon, lat, elev_m]` (**VERIFICADO**)
- Renombrado de columnas (obligatorio, único lugar donde aparecen los nombres POWER):

| POWER                   | columna                 | unidad                              |
| ----------------------- | ----------------------- | ----------------------------------- |
| PRECTOTCORR             | `prec`                  | mm/día                              |
| T2M / T2M_MAX / T2M_MIN | `t2m` / `tmax` / `tmin` | °C                                  |
| RH2M                    | `rh`                    | %                                   |
| ALLSKY_SFC_SW_DWN       | `rs`                    | MJ/m²/día (solo con `community=AG`) |
| WS2M                    | `ws`                    | m/s a 2 m                           |
| GWETTOP / GWETROOT      | `gwettop` / `gwetroot`  | 0..1                                |
| PS                      | `ps`                    | kPa                                 |

- lat/lon se redondean a 2 decimales **antes** de pedir. Caché: `backend/cache/power/{lat:.2f}_{lon:.2f}_{start}_{end}.json` (respuesta cruda). Timeout 60 s, 3 reintentos con espera 2/4/8 s. Error final → `PowerUnavailable`.
- Supuesto no verificado: límite de 20 parámetros por request diario (usamos 10, verificado que funciona).

### 2.4 `crops.json`

```json
{
  "soya": {
    "nombre": "Soya",
    "familia": "Fabaceae",
    "cosechable": true,
    "value_weight": 1.0,
    "etapas_dias": {
      "valor": [20, 30, 60, 25],
      "fuente": "FAO-56 Tabla 11",
      "verificar": true
    },
    "kc": {
      "valor": [0.4, 1.15, 0.5],
      "fuente": "FAO-56 Tabla 12",
      "verificar": true
    },
    "zr_max_m": {
      "valor": 1.0,
      "fuente": "FAO-56 Tabla 22 (0.6–1.3)",
      "verificar": true
    },
    "p": { "valor": 0.5, "fuente": "FAO-56 Tabla 22", "verificar": true },
    "ky": {
      "valor": 0.85,
      "fuente": "FAO-56 Tabla 24 / FAO-33",
      "verificar": true
    },
    "t_ecocrop": {
      "valor": [10, 20, 33, 38],
      "fuente": "FAO ECOCROP (TMIN, TOPMN, TOPMX, TMAX)",
      "verificar": true
    },
    "t_calor": {
      "valor": [35, 40],
      "fuente": "Teixeira et al. 2013 (Tcrit, Tlim)",
      "verificar": true
    },
    "t_helada": { "valor": 0, "fuente": "supuesto S6", "verificar": true },
    "clase_n": {
      "valor": "leguminosa_grano",
      "fuente": "supuesto S8",
      "verificar": true
    },
    "clase_rastrojo": {
      "valor": "bajo",
      "fuente": "supuesto S8",
      "verificar": true
    }
  }
}
```

Todo campo numérico o categórico agronómico es `{valor, fuente, verificar}`. El loader expone un `Crop` plano y `GET /crops` devuelve `id, nombre, familia, cosechable, n_verificar_pendientes`.
`clase_n ∈ {cobertura_leguminosa, leguminosa_grano, cobertura_no_leguminosa, extractiva, muy_extractiva}`; `clase_rastrojo ∈ {bajo, medio, alto}`.

**Tabla semilla** — valores recordados de las fuentes, **NO cotejados**: todos entran con `verificar: true`. Tarea T0.5 los coteja.

| id         | familia    | cos. | etapas ini/dev/mid/late | Kc ini/mid/end  | Zr  | p   | Ky     | ECOCROP Tmin/opt/opt/Tmax | calor crit/lim | N                       | rastrojo |
| ---------- | ---------- | ---- | ----------------------- | --------------- | --- | --- | ------ | ------------------------- | -------------- | ----------------------- | -------- |
| soya       | Fabaceae   | sí   | 20/30/60/25             | .40/1.15/.50    | 1.0 | .50 | .85    | 10/20/33/38               | 35/40          | leguminosa_grano        | bajo     |
| maiz       | Poaceae    | sí   | 25/40/45/30             | .30/1.20/.35    | 1.3 | .55 | 1.25   | 10/18/33/47               | 35/45          | muy_extractiva          | alto     |
| sorgo      | Poaceae    | sí   | 20/35/40/30             | .30/1.05/.55    | 1.5 | .55 | .90    | 8/22/35/40                | 35/40 \*       | extractiva              | alto     |
| trigo      | Poaceae    | sí   | 15/25/50/30             | .30/1.15/.30    | 1.2 | .55 | 1.15   | 5/15/23/27                | 27/40          | extractiva              | medio    |
| girasol    | Asteraceae | sí   | 25/35/45/25             | .35/1.10/.35    | 1.2 | .45 | .95    | 5/17/34/45                | 34/45 \*       | muy_extractiva          | medio    |
| frijol     | Fabaceae   | sí   | 20/30/40/20             | .40/1.15/.35    | 0.7 | .45 | 1.15   | 7/16/25/32                | 25/32 \*       | leguminosa_grano        | bajo     |
| mani       | Fabaceae   | sí   | 25/35/45/25             | .40/1.15/.60    | 0.8 | .50 | .70    | 10/22/32/45               | 32/45 \*       | leguminosa_grano        | bajo     |
| algodon    | Malvaceae  | sí   | 30/50/55/45             | .35/1.15/.60    | 1.4 | .65 | .85    | 15/22/36/42               | 36/42 \*       | muy_extractiva          | bajo     |
| cebada     | Poaceae    | sí   | 15/25/50/30             | .30/1.15/.25    | 1.2 | .55 | 1.15 † | 2/15/20/40                | 20/40 \*       | extractiva              | medio    |
| papa       | Solanaceae | sí   | 25/30/45/30             | .50/1.15/.75    | 0.5 | .35 | 1.10   | 7/15/25/30                | 25/30 \*       | extractiva              | bajo     |
| mijo       | Poaceae    | sí   | 15/25/40/25             | .30/1.00/.30    | 1.5 | .55 | .90 †  | 12/25/35/40               | 35/40 \*       | extractiva              | alto     |
| avena_cob  | Poaceae    | no   | 15/25/45/5 ‡            | .30/1.15/1.15 ‡ | 1.2 | .55 | 1.0 ‡  | 5/16/20/30                | 20/30 \*       | cobertura_no_leguminosa | alto     |
| crotalaria | Fabaceae   | no   | 15/25/45/5 ‡            | .40/1.10/1.10 ‡ | 1.0 | .50 | 1.0 ‡  | 15/23/30/37               | 30/37 \*       | cobertura_leguminosa    | alto     |

`*` no está en Teixeira 2013: derivado mecánicamente como (TOPMX, TMAX) de ECOCROP — supuesto S7. `†` sin valor en FAO-56 Tabla 24: analogía con trigo/sorgo. `‡` cultivo de cobertura sin entrada en FAO-56: supuesto S9 (ciclo cortado a 90 días, Kc_end = Kc_mid porque se termina en verde). `t_helada = 0` para todos.

### 2.5 Ficha de rotación

Es `RotationCard` (§2.2). Invariante testeado: para cada `Claim`, todo número que aparezca en `text` (regex `-?\d+(?:[.,]\d+)?`) coincide con algún `evidence[].value` formateado con el mismo redondeo. Sin excepción.

## 3. Fases y tareas

Convención: cada tarea = una sesión de agente, <150 líneas de cambio. `[P]` paralelizable con las de su fase, `[S]` secuencial. Aceptación = comando que debe pasar. Todos los `pytest` se corren desde `backend/`.

### F0 — Contratos y esqueleto (h 0–3)

| ID   | Objetivo                                                                                                                                                          | Archivos                                                                    | Aceptación                                                                                                    | Dep  |     |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---- | --- |
| T0.1 | Esqueleto del repo, `pyproject.toml`, `.gitignore`, `/health`                                                                                                     | `backend/pyproject.toml`, `app/main.py`, árbol vacío                        | `pytest -q` (0 tests, exit 5 aceptado) y `uvicorn app.main:app` responde `/health`                            | —    | S   |
| T0.2 | Constantes de §4.0                                                                                                                                                | `app/config.py`                                                             | `python -c "from app import config; assert config.BAD_SEASON_I==0.6"`                                         | T0.1 | S   |
| T0.3 | Schemas Pydantic de §2.1-2.2 copiados literalmente                                                                                                                | `app/schemas.py`, `tests/test_schemas.py`                                   | test: el ejemplo demo valida; `sow_date="11-15"` → error                                                      | T0.1 | P   |
| T0.4 | `crops.json` con la tabla semilla + loader                                                                                                                        | `app/data/crops.json`, `app/data/crops.py`, `tests/test_crops.py`           | test: 13 cultivos; todo campo agronómico tiene `fuente` y `verificar`; `sum(etapas)` = ciclo; Kc_mid ≥ Kc_ini | T0.1 | P   |
| T0.5 | **Humano**: cotejar soya, maíz, sorgo, trigo, girasol contra FAO-56 (fao.org/4/x0490e, Tablas 11/12/22/24) y ECOCROP; poner `verificar:false` solo en lo cotejado | `crops.json`                                                                | diff revisado por Cbass                                                                                       | T0.4 | P   |
| T0.6 | Fixture de respuesta escrito a mano (2 campañas, 3 rotaciones)                                                                                                    | `contracts/analyze_response.example.json`, `tests/test_contract_example.py` | test: el JSON valida contra `AnalyzeResponse`                                                                 | T0.3 | P   |

### F1 — Datos (h 3–5)

| ID   | Objetivo                                                         | Archivos                                                     | Aceptación                                                                                       | Dep  |     |
| ---- | ---------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | ---- | --- |
| T1.1 | Parser POWER → `PowerData` (−999→NaN, renombrado, índice diario) | `app/nasa/power.py`, `tests/test_power_parse.py`             | test con JSON sintético de 3 días que incluye un −999: columna NaN, 10 columnas, elevación leída | T0.2 | P   |
| T1.2 | Fetch con caché, redondeo de coords, reintentos                  | `app/nasa/power.py`, `tests/test_power_cache.py`             | test con `httpx.MockTransport`: 2ª llamada no toca red; 3 fallos → `PowerUnavailable`            | T1.1 | S   |
| T1.3 | Script que baja el punto demo y lo guarda como fixture           | `scripts/fetch_fixture.py`, `tests/fixtures/power_demo.json` | `python scripts/fetch_fixture.py` crea el archivo; 12784 días; 0 NaN en `prec/tmax/tmin`         | T1.2 | S   |

### F2 — Motor (h 5–17). Leer §4 completo antes de cada tarea.

| ID    | Objetivo                                                                       | Archivos                                                                               | Aceptación                                                                | Dep        |     |
| ----- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ---------- | --- |
| T2.1  | Campaña agrícola y rejilla de siembra (§4.1)                                   | `engine/calendar.py`, `tests/test_calendar.py`                                         | tests §6 C1-C4                                                            | T0.2       | P   |
| T2.2  | Ra, Penman-Monteith, Hargreaves, `add_et0(df)` (§4.2)                          | `engine/et0.py`, `tests/test_et0.py`                                                   | tests §6 E1-E5                                                            | T0.2       | P   |
| T2.3  | Curva Kc, ventana sensible (§4.3)                                              | `engine/crop.py`, `tests/test_crop.py`                                                 | tests §6 K1-K3                                                            | T0.4       | P   |
| T2.4  | Escorrentía CN + paso diario de balance (§4.4), funciones puras vectorizadas   | `engine/slot.py` (`runoff`, `wb_step`), `tests/test_wb.py`                             | tests §6 W1-W4                                                            | T0.2       | P   |
| T2.5  | Factores térmicos (§4.5), funciones puras                                      | `engine/slot.py` (`trapezoid`, `heat_factor`, `frost_factor`), `tests/test_thermal.py` | tests §6 H1-H4                                                            | T0.2       | P   |
| T2.6  | `simulate_slot` completo (§4.4-4.5) vectorizado sobre campañas                 | `engine/slot.py`, `tests/test_slot.py`                                                 | tests §6 S1-S5                                                            | T2.1-T2.5  | S   |
| T2.7  | `SlotTable` memoizada + suavizado de fechas (§4.6)                             | `engine/table.py`, `tests/test_table.py`                                               | test: 2ª lectura no recalcula (contador); suavizado circular de ventana 3 | T2.6       | S   |
| T2.8  | Evaluación de rotación: modos, validación, `P`, `I`, año malo, métricas (§4.6) | `engine/rotation.py`, `tests/test_rotation.py`                                         | tests §6 R1-R5                                                            | T2.7       | S   |
| T2.9  | Puntaje de suelo (§4.7)                                                        | `engine/soil.py`, `tests/test_soil.py`                                                 | tests §6 G1-G4                                                            | T2.1, T2.3 | P   |
| T2.10 | Perfil climático antes/ahora + climatología quincenal (§4.8)                   | `engine/climate.py`, `tests/test_climate.py`                                           | tests §6 M1-M4                                                            | T2.1, T2.2 | P   |

### F3 — Puerta de validación en notebook (h 17–20) **[S, humano + agente]**

| ID  | Objetivo                                                                                              | Archivos                              | Aceptación                                     | Dep |
| --- | ----------------------------------------------------------------------------------------------------- | ------------------------------------- | ---------------------------------------------- | --- |
| N1  | Notebook con el punto demo: ET0 anual, serie `I` de soya-soya, factores por campaña, perfil climático | `notebooks/01_validacion_motor.ipynb` | corre de principio a fin sin red (usa fixture) | F2  |
| N2  | **Go/no-go** (Cbass)                                                                                  | —                                     | checklist de abajo                             | N1  |

Checklist go/no-go (si falla un punto, se revisa parámetro/fórmula **antes** de tocar UI):

1. ET0 anual entre 1100 y 2000 mm y lluvia anual entre 700 y 1800 mm (órdenes de magnitud para Santa Cruz; verificar contra SENAMHI).
2. Soya de verano: `mean_yield` > soya de invierno (la de invierno depende de humedad residual).
3. La línea base tiene entre 1 y 15 campañas malas de 20. Si da 0 o 20, el modelo no discrimina: revisar `AWC`, modo de spin-up y `BAD_SEASON_I` **documentando el cambio**; no ajustar para que "se vea bien".
4. Las 3 campañas con peor `I` se contrastan con sequías reportadas (ANAPO/prensa). Anotar coincidencias y fallos tal cual.
5. Correlación entre `1 − Dr/TAW` simulado y `gwetroot` de POWER > 0.5 (chequeo de cordura, **no** validación independiente: comparten la misma lluvia).

### F4 — Alternativas, fichas, API (h 20–28)

| ID   | Objetivo                                                                                             | Archivos                                              | Aceptación                                                            | Dep               |     |
| ---- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------------------- | ----------------- | --- |
| T4.1 | Enumeración de planes anuales y rotaciones de 2 años (§5.1-5.2)                                      | `engine/alternatives.py`, `tests/test_enum.py`        | tests §6 A1-A3                                                        | T2.8              | S   |
| T4.2 | Selección de perfiles con relajación (§5.3)                                                          | `engine/alternatives.py`, `tests/test_select.py`      | tests §6 A4-A6                                                        | T4.1, T2.9        | S   |
| T4.3 | Fichas por plantilla (§4.9)                                                                          | `engine/cards.py`, `tests/test_cards.py`              | tests §6 F1-F3                                                        | T2.8, T2.9, T2.10 | P   |
| T4.4 | `pipeline.analyze` + `POST /analyze` + `GET /crops` + CORS + caché de respuesta por hash del request | `app/pipeline.py`, `app/main.py`, `tests/test_api.py` | tests §6 P1-P3                                                        | T4.2, T4.3        | S   |
| T4.5 | Precache del demo                                                                                    | `scripts/precache_demo.py`                            | genera `frontend/public/demo_santa_cruz.json` válido contra el schema | T4.4              | S   |

### F5 — Frontend (arranca en h 3 contra `contracts/analyze_response.example.json`)

| ID   | Objetivo                                                                                                                                                                                                                   | Archivos                                                                          | Aceptación                                                                    | Dep  |     |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ---- | --- |
| T5.1 | Scaffold Vite+React+TS, `types.ts` espejo de §2, `api.ts` con fallback a JSON estático                                                                                                                                     | `frontend/*`, `src/types.ts`, `src/api.ts`                                        | `npm run build` sin errores de tipos                                          | T0.6 | S   |
| T5.2 | Vista (a): mapa Leaflet con clic → lat/lon, selector de suelo, `RotationEditor` (años → slots → cultivo + mes + quincena), botón "Cargar demo Santa Cruz"                                                                  | `views/MapForm.tsx`, `components/RotationEditor.tsx`                              | build OK; el payload emitido valida contra `AnalyzeRequest` (copiar a `curl`) | T5.1 | P   |
| T5.3 | Vista (b) "Tu clima cambió": una tarjeta por `ClimateMetric` (antes → ahora, delta, etiqueta "no significativo" si `!significant`), serie por campaña, pie con fuente NASA                                                 | `views/ClimateShift.tsx`, `components/MetricDelta.tsx`                            | build OK; renderiza el fixture                                                | T5.1 | P   |
| T5.4 | Vista (c) tabla comparativa (filas: campañas malas X/20, productividad vs actual, índice p10, suelo total y 4 componentes) + `RotationCard` con por qué/beneficios/riesgos y chip de evidencia por claim                   | `views/Compare.tsx`, `components/CompareTable.tsx`, `components/RotationCard.tsx` | build OK; cada claim muestra dataset + parámetros + periodo                   | T5.1 | P   |
| T5.5 | Calendario: eje X = 24 quincenas desde inicio de campaña; barras de lluvia y línea ET0 (ahora, y antes en tenue), líneas Tmax/Tmin; debajo una fila por rotación con barras por slot (etapas y ventana sensible resaltada) | `components/CalendarChart.tsx`                                                    | build OK; slots que cruzan el fin de campaña se dibujan partidos              | T5.1 | P   |
| T5.6 | Tira de campañas por rotación (20 celdas, roja si `bad`, tooltip con factor limitante) + estados de carga/error + banner "modo demo offline"                                                                               | `views/Compare.tsx`, `App.tsx`                                                    | con backend apagado la app muestra el demo estático                           | T5.4 | S   |

### F6 — Integración y demo (h 28–40)

| ID   | Objetivo                                                                                                | Aceptación                                                                   | Dep    |
| ---- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------ |
| T6.1 | E2E: backend real + frontend, caso demo                                                                 | recorrido manual de §7 sin errores; primera respuesta < 30 s, cacheada < 1 s | F4, F5 |
| T6.2 | Si primera respuesta > 30 s: prefiltro de fechas por `f_temp` climatológico ≥ 0.5 antes de simular agua | mismas rotaciones elegidas antes y después (test de regresión)               | T6.1   |
| T6.3 | README: cómo correr, fuentes NASA, limitaciones (§4.10), tabla requisito→pantalla                       | revisión humana                                                              | T6.1   |
| T6.4 | Video/slides según §7                                                                                   | —                                                                            | T6.1   |

### F7 — Extras (h 40–48, solo si F6 está cerrada; en este orden)

1. **E1 MODIS backtest**: `nasa/modis.py` pide MOD13Q1 en bloques de ≤10 fechas (límite **verificado**; ~5 s por fecha), caché en disco, solo offline para el punto demo. NDVI máximo por campaña vs `I` de la línea base: Spearman + cuántas campañas malas caen en el tercil inferior de NDVI. Se muestra tal cual salga.
2. **E2 Diversificada** (`include_diversified=true`).
3. **E3 Redacción con Claude API** (`claude-haiku-5-5`): entrada = JSON de claims; instrucción = reescribir sin añadir ni cambiar cifras; salida validada con el mismo test F1; si falla, se usa la plantilla.
4. **E4 SMAP vía AppEEARS**: precacheado para el punto demo, solo como gráfico de contexto.

## 4. Fórmulas y reglas del motor (NORMATIVO)

### 4.0 Constantes (`config.py`)

```python
DATA_START, DATA_END = "19910101", "20251231"
N_BEFORE, N_RECENT, N_EVAL = 15, 15, 20
SPINUP_DAYS, PRE_CROP_DAYS = 180, 120
KC_FALLOW, KC_PRE_CROP = 0.20, 0.90          # supuesto S2
DR0_FRAC = 0.5
GAP_CROP_MAX_DAYS, TURNAROUND_DAYS, MAX_OVERRUN_DAYS = 30, 10, 183
AWC_MM_PER_M = {"arenoso": 80, "franco": 155, "arcilloso": 160}   # FAO-56 Tabla 19, verificar
CN = {"arenoso": 67, "franco": 78, "arcilloso": 85}               # USDA TR-55, verificar
P_MIN, P_MAX = 0.1, 0.8
SMALL_RAIN_FRAC = 0.2                        # lluvia < 0.2·ET0 se ignora (FAO-56 cap. 8)
SENS_BEFORE, SENS_AFTER = 5, 25              # ventana sensible alrededor del inicio de etapa mid
F_FROST_SENS, F_FROST_VEG, FROST_VEG_OFFSET = 0.3, 0.7, 3.0      # supuesto S6
BAD_SEASON_I, SLOT_FAIL = 0.60, 0.50
DRY_DAY_MM, HOT_DAY_C, DRY_SPELL_DAYS, GDD_BASE = 1.0, 35.0, 10, 10.0
ONSET_MM, ONSET_WINDOW, ONSET_LOOKAHEAD, ONSET_SEARCH_START = 20.0, 3, 30, 62
CESS_MIN_AFTER_ONSET, CESS_WINDOW, CESS_MM = 60, 20, 10.0
N_POINTS = {"cobertura_leguminosa": 2.0, "leguminosa_grano": 0.5,
            "cobertura_no_leguminosa": 0.5, "extractiva": -1.0, "muy_extractiva": -1.5}
RESIDUE_POINTS = {"bajo": 1, "medio": 2, "alto": 3}; COVER_CROP_BONUS = 1
RESIDUE_COVER = {"bajo": 0.3, "medio": 0.5, "alto": 0.8}
DIVERSITY_BASE = {1: 30, 2: 65, 3: 85}       # >=4 -> 100
VIABLE_MIN, VIABLE_MIN_COVER = 0.50, 0.40
ADAPT_MIN_PROD, REGEN_MAX_LOSS, REGEN_MAX_LOSS_RELAXED, REGEN_MIN_SOIL_GAIN = 0.95, 0.20, 0.30, 10
```

### 4.1 Campaña agrícola y fechas

```
hemisferio = "S" si lat < 0, si no "N"
inicio(y)  = date(y, 7, 1) si S ; date(y, 1, 1) si N
campaña y válida  <=>  inicio(y) − SPINUP_DAYS >= DATA_START  y  inicio(y) + 365 + MAX_OVERRUN_DAYS <= DATA_END
     -> S: 1991..2024 (34)   N: 1992..2024 (33)
seasons = lista ordenada de campañas válidas (LA MISMA para todas las rotaciones)
before = seasons[:15]   recent = seasons[-15:]   eval = seasons[-20:]
etiqueta = f"{y}/{(y+1)%100:02d}" si S ; f"{y}" si N

fecha_siembra("MM-DD", y) = date(y, MM, DD)      si N, o si S y MM >= 7
                          = date(y+1, MM, DD)    si S y MM < 7
rejilla de siembra = 24 fechas: día 01 y 16 de cada mes, ORDENADAS desde el inicio de campaña
sow_offset (para contrato/UI) = días desde inicio de campaña en un año NO bisiesto
```

Regla dura: nunca `groupby(year)` calendario. Toda agregación usa la campaña.

### 4.2 ET0 (mm/día)

Entradas diarias: `tmax, tmin, rh, rs, ws, ps`, latitud φ (rad, negativa al sur), elevación z (m), J = día del año.

```
# Radiación extraterrestre (FAO-56 ec. 21-25)
dr  = 1 + 0.033·cos(2π·J/365)
δ   = 0.409·sin(2π·J/365 − 1.39)
ωs  = arccos(clip(−tan φ · tan δ, −1, 1))
Ra  = (24·60/π)·0.0820·dr·(ωs·sin φ·sin δ + cos φ·cos δ·sin ωs)        # MJ/m²/día

# Penman-Monteith (FAO-56 ec. 6)
T    = (tmax + tmin)/2                     # NO usar t2m
e0(x)= 0.6108·exp(17.27·x/(x + 237.3))
es   = (e0(tmax) + e0(tmin))/2
ea   = es·rh/100                           # FAO-56 ec. 19
Δ    = 4098·e0(T)/(T + 237.3)²
P    = ps  si no es NaN ; si no 101.3·((293 − 0.0065·z)/293)^5.26
γ    = 0.000665·P
Rso  = (0.75 + 2e−5·z)·Ra
Rns  = 0.77·rs
Rnl  = 4.903e−9·((tmax+273.16)⁴ + (tmin+273.16)⁴)/2·(0.34 − 0.14·√ea)·(1.35·clip(rs/Rso, 0.3, 1.0) − 0.35)
Rn   = Rns − Rnl ;  G = 0
ET0_pm = (0.408·Δ·Rn + γ·900/(T+273)·ws·(es − ea)) / (Δ + γ·(1 + 0.34·ws))

# Hargreaves (FAO-56 ec. 52)
ET0_hg = 0.0023·(T + 17.8)·√max(tmax − tmin, 0)·Ra·0.408

et0 = ET0_pm si rh, rs y ws no son NaN ; si no ET0_hg          # decisión por DÍA
et0 = max(et0, 0)
```

`add_et0(df, lat, elev)` añade columnas `et0` y `et0_method ∈ {"pm","hg"}`.

### 4.3 Cultivo: Kc y ventana sensible

```
L = [L_ini, L_dev, L_mid, L_late] ; N = sum(L) ; t = días desde siembra, 0..N−1
kc(t) = Kc_ini                                              t < L_ini
      = Kc_ini + (Kc_mid − Kc_ini)·(t − L_ini)/L_dev        L_ini <= t < L_ini+L_dev
      = Kc_mid                                              L_ini+L_dev <= t < L_ini+L_dev+L_mid
      = Kc_mid + (Kc_end − Kc_mid)·(t − (N − L_late))/L_late   resto
t_mid = L_ini + L_dev
sens  = { t : max(0, t_mid − SENS_BEFORE) <= t < min(N, t_mid + SENS_AFTER) }
cosecha = siembra + N días
```

Sin ajuste climático de Kc (FAO-56 ec. 62): supuesto S3.

### 4.4 Balance hídrico por slot

Un **slot** = (cultivo, fecha de siembra, modo). Estado: agotamiento `Dr` (mm) en un balde de capacidad `TAW`. Vectorizado: cada variable es un array de largo = nº de campañas.

```
TAW = AWC_MM_PER_M[suelo]·zr_max_m
S   = 25400/CN[suelo] − 254
Dr  = DR0_FRAC·TAW
para t = −SPINUP_DAYS .. N−1:
    día = fecha_siembra(y) + t                         # por campaña
    si t < 0:
        Kc    = KC_PRE_CROP si (modo == "crop" y t >= −PRE_CROP_DAYS) si no KC_FALLOW
        p_tab = 0.5
    si no:
        Kc    = kc(t) ; p_tab = cultivo.p
    RO  = (prec − 0.2·S)²/(prec + 0.8·S)  si prec > 0.2·S  si no 0          # SCS-CN
    Pe  = 0  si prec < SMALL_RAIN_FRAC·et0  si no  prec − RO
    D   = Dr − Pe ;  DP = max(0, −D) ;  D = max(0, D)                      # lluvia entra ANTES de evaluar estrés
    ETc = Kc·et0
    p   = clip(p_tab + 0.04·(5 − ETc), P_MIN, P_MAX) ;  RAW = p·TAW
    Ks  = 1  si D <= RAW  si no  (TAW − D)/(TAW − RAW)
    ETa = Ks·ETc
    Dr  = min(TAW, D + ETa)
    si t >= 0:  ΣETa += ETa ;  ΣETc += ETc
ratio   = ΣETa/ΣETc  si ΣETc > 0  si no 1          # ratio de SUMAS, nunca media de ratios
f_agua  = clip(1 − ky·(1 − ratio), 0, 1)            # FAO-56 ec. 90
```

Si `prec`, `tmax` o `tmin` tienen NaN en la ventana de una campaña, el resultado de esa campaña es NaN y el pipeline falla con error explícito (no se rellena).

### 4.5 Factores térmicos y rendimiento del slot

```
T = (tmax + tmin)/2
trapecio(x; a,b,c,d) = 0 si x<=a o x>=d ; (x−a)/(b−a) si a<x<b ; 1 si b<=x<=c ; (d−x)/(d−c) si c<x<d
f_temp   = media_{t=0..N−1} trapecio(T_t; t_ecocrop)                       # aptitud térmica general
h_t      = clip((tmax_t − Tcrit)/(Tlim − Tcrit), 0, 1)
f_calor  = 1 − media_{t∈sens} h_t                                          # calor en floración
helada_s = existe t∈sens con tmin_t < t_helada
helada_v = existe t∈[0,N) con tmin_t < t_helada − FROST_VEG_OFFSET
f_helada = F_FROST_SENS si helada_s ; F_FROST_VEG si helada_v ; 1 en otro caso

Y_rel    = f_agua · f_calor · f_helada · f_temp          # 0..1
limitante = el factor mínimo si min < 0.95, si no "ninguno"; empate: orden agua, calor, helada, temperatura
```

`simulate_slot` devuelve por campaña: `y_rel, f_agua, f_calor, f_helada, f_temp, sum_eta, sum_etc`.

### 4.6 Rotación: modos, validez, productividad, año malo

```
Secuencia cíclica de slots: año 1 slot 1, año 1 slot 2, año 2 slot 1, ...; el predecesor del primero es el último.
gap(s)  = siembra(s) − cosecha(pred(s))    en días, sumando 365 por cada cambio de año de la rotación
modo(s) = "crop" si gap(s) <= GAP_CROP_MAX_DAYS si no "fallow"

Rotación válida <=> para todo s: gap(s) >= TURNAROUND_DAYS
                    y  sow_offset(s) + N(s) <= 365 + MAX_OVERRUN_DAYS
                    y  existe al menos un slot cosechable

Para la campaña y (clima de y aplicado a TODAS las fases k = 1..L de la rotación):
    P_y   = (1/L)·Σ_k Σ_{s∈año k, cosechable} w_s·Y_rel(s, y)
    Pot   = (1/L)·Σ_k Σ_{s∈año k, cosechable} w_s
    I_y   = P_y / Pot
    mala  = I_y < BAD_SEASON_I
    limitante_y = limitante del slot cosechable con menor Y_rel en y

Métricas (ventana eval salvo indicación):
    mean_index = media(I) ; p10_index = percentil 10 lineal de I ; mean_productivity = media(P)
    bad_seasons = Σ mala (n = 20)
    bad_before / bad_recent = Σ mala sobre before / recent (n = 15)
    failures(s) = Σ_y [Y_rel(s,y) < SLOT_FAIL]
    productivity_vs_current = 100·mean_productivity / mean_productivity(actual)

SlotTable: memo por (crop_id, índice de fecha 0..23, modo) -> arrays por campaña.
Tabla suavizada (SOLO para elegir fechas en §5): Ȳ[c,g,m] = media(Y[c,g−1,m], Y[c,g,m], Y[c,g+1,m]) con g circular.
```

Los cultivos de cobertura (`cosechable=false`) no suman a `P` ni a `Pot`; sí cuentan para suelo, modo del siguiente slot y validez.

### 4.7 Puntaje de suelo (0–100, reglas)

```
seq = secuencia cíclica de TODOS los slots (incluye coberturas) ; L = años del ciclo

Nitrógeno:   N_año = (1/L)·Σ_s N_POINTS[clase_n(s)]
             nitrogen = clip(60 + 20·N_año, 0, 100)

Diversidad:  n_fam   = nº de familias distintas en seq
             repite  = (nº de pares cíclicos adyacentes con la misma familia)/len(seq)     # 1 slot solo -> 1.0
             diversity = DIVERSITY_BASE.get(n_fam, 100)·(1 − 0.5·repite)

Mat. org.:   pts(s) = RESIDUE_POINTS[clase_rastrojo(s)] + (COVER_CROP_BONUS si no cosechable)
             organic_matter = clip(100·((1/L)·Σ_s pts(s))/6, 0, 100)

Erosión (única parte con datos NASA):
    W[o] = media sobre campañas eval de RO(prec) en el offset o = 0..364          # RO de §4.4, CN del suelo
    cover_k[o] para cada año k de la rotación:
        dentro de un slot, t = días desde siembra, r = RESIDUE_COVER del slot predecesor:
            t < L_ini                 -> r
            L_ini <= t < L_ini+L_dev  -> max(r, (t − L_ini)/L_dev)
            resto del ciclo           -> 1.0
        entre cosecha y la siguiente siembra -> RESIDUE_COVER[clase_rastrojo del slot cosechado]
    erosion = 100·media_k( Σ_o W[o]·cover_k[o] / Σ_o W[o] )      ; si Σ W = 0 -> 100

total = 0.25·(nitrogen + diversity + erosion + organic_matter)
```

Supone siembra directa (el rastrojo queda en superficie): supuesto S5. El suelo **no** retroalimenta el rendimiento: supuesto S4.

### 4.8 Perfil climático (por campaña; luego before vs recent)

| id              | Definición                                                                                                                                       | Parámetros POWER                                    |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| `rain_total`    | Σ prec de la campaña (mm)                                                                                                                        | PRECTOTCORR                                         |
| `rain_q1..q4`   | Σ prec por trimestre de campaña (días 0-90, 91-181, 182-272, 273-fin)                                                                            | PRECTOTCORR                                         |
| `onset`         | primer offset o ≥ `ONSET_SEARCH_START` con Σ prec[o..o+2] ≥ 20 mm **y** sin racha de ≥10 días secos (prec < 1 mm) en [o, o+30). NaN si no existe | PRECTOTCORR                                         |
| `cessation`     | primer offset c ≥ onset + 60 con Σ prec[c..c+19] < 10 mm. NaN si onset es NaN                                                                    | PRECTOTCORR                                         |
| `season_length` | cessation − onset                                                                                                                                | PRECTOTCORR                                         |
| `hot_days`      | nº de días con tmax > 35                                                                                                                         | T2M_MAX                                             |
| `dry_spells`    | nº de rachas de ≥10 días secos consecutivos dentro de [onset, cessation); NaN si no hay onset                                                    | PRECTOTCORR                                         |
| `max_dry_spell` | racha seca más larga en la misma ventana                                                                                                         | PRECTOTCORR                                         |
| `gdd`           | Σ max(0, (tmax+tmin)/2 − 10)                                                                                                                     | T2M_MAX, T2M_MIN                                    |
| `et0_total`     | Σ et0                                                                                                                                            | T2M_MAX, T2M_MIN, RH2M, WS2M, ALLSKY_SFC_SW_DWN, PS |
| `water_deficit` | Σ max(0, et0 − prec) mensual acumulado                                                                                                           | todas las anteriores                                |

Por métrica: `before` = media (ignorando NaN) en before, `recent` igual, `delta = recent − before`, `p_value` = `scipy.stats.mannwhitneyu(a, b, alternative="two-sided")` (None si alguna muestra tiene <5 valores), `significant = p < 0.10`.
Climatología quincenal: 24 bins desde el inicio de campaña (días 1-15 y 16-fin de cada mes); lluvia y ET0 = suma media por bin; tmax/tmin = media. Una para before, otra para recent.

### 4.9 Fichas (plantillas)

Cada plantilla produce un `Claim` con su `evidence`. Números con redondeo fijo: conteos enteros, mm y días sin decimales, índices y puntajes sin decimales (×100 si son fracción), °C con 1 decimal. Se emite la plantilla solo si su condición se cumple.

| Sección      | Condición                                     | Texto                                                                                                                                       | Parámetros citados                                                                             |
| ------------ | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| why (actual) | siempre                                       | "Es la rotación que usás hoy: línea base de la comparación." + evidence `bad_seasons`                                                       | los de agua                                                                                    |
| why (actual) | `bad_recent != bad_before`                    | "Con el clima de {before} tuvo {bad_before} campañas malas de {n}; con el de {recent}, {bad_recent} de {n}."                                | agua + T2M_MAX                                                                                 |
| why          | fecha de siembra cambia y `onset.significant` | "El inicio de lluvias pasó del día {a} al día {b} de la campaña; sembrar {cultivo} el {fecha} baja las campañas malas de {x} a {y} de {n}." | PRECTOTCORR                                                                                    |
| why          | fecha cambia y onset no significativo         | "Sembrar {cultivo} el {fecha} en vez del {fecha0} baja las campañas malas de {x} a {y} de {n}."                                             | agua                                                                                           |
| why          | sustitución de cultivo                        | "{nuevo} reemplaza a {viejo}: {viejo} perdió más de la mitad del rendimiento en {k0} de {n} campañas; {nuevo} en {k1}."                     | agua, T2M_MAX, T2M_MIN                                                                         |
| why (regen.) | siempre                                       | "Sube el puntaje de suelo de {s0} a {s1} sobre 100."                                                                                        | PRECTOTCORR (erosión)                                                                          |
| benefits     | `bad < bad_actual`                            | "{d} campañas malas menos de {n}."                                                                                                          | agua                                                                                           |
| benefits     | `productivity_vs_current > 102`               | "Productividad {v}% respecto de la actual."                                                                                                 | agua                                                                                           |
| benefits     | erosión sube ≥5                               | "El {e}% de la escorrentía de lluvias intensas cae con el suelo cubierto (antes {e0}%)."                                                    | PRECTOTCORR                                                                                    |
| benefits     | diversidad sube                               | "{f} familias botánicas en el ciclo (antes {f0})."                                                                                          | — (regla; `source.dataset = "Regla agronómica"`)                                               |
| risks        | siempre                                       | "Campaña mala (menos del 60% del potencial) en {bad} de {n}: {lista de hasta 3 peores}."                                                    | agua                                                                                           |
| risks        | limitante dominante ≠ ninguno                 | "Factor limitante más frecuente: {factor} ({k} de {n} campañas)."                                                                           | según factor: agua→PRECTOTCORR+ET0; calor→T2M_MAX; helada→T2M_MIN; temperatura→T2M_MAX,T2M_MIN |
| risks        | `productivity_vs_current < 98`                | "Produce {v}% de lo que rinde la actual."                                                                                                   | agua                                                                                           |
| risks        | `repite > 0`                                  | "Repite familia botánica en {k} de {m} transiciones."                                                                                       | — (regla)                                                                                      |
| risks        | `relaxed_constraints` no vacío                | "No hubo alternativa dentro del límite de pérdida del {x}%; se aceptó hasta {y}%."                                                          | —                                                                                              |
| risks        | `!improves_on_current`                        | "Con cambios mínimos no encontramos una opción mejor que tu rotación actual."                                                               | agua                                                                                           |
| risks        | siempre (1 por ficha)                         | "Resolución ≈50 km: es el clima regional, no el de tu parcela."                                                                             | —                                                                                              |

"los de agua" = `PRECTOTCORR, T2M_MAX, T2M_MIN, RH2M, WS2M, ALLSKY_SFC_SW_DWN, PS`.

### 4.10 Supuestos y límites (van a `meta.assumptions` y al README)

- S1. POWER es reanálisis a ≈50 km (MERRA-2) y 1° (radiación CERES): clima regional. Tmax tiende a quedar por debajo de estaciones; los conteos de días >35 °C son conservadores.
- S2. Agua inicial: spin-up de 180 días con Kc fijo de barbecho (0.20) o de cultivo previo (0.90). No se simula el cultivo anterior real.
- S3. Fenología por días calendario; Kc sin ajuste por humedad/viento; sin fotoperiodo.
- S4. El puntaje de suelo no modifica el rendimiento simulado.
- S5. Se asume siembra directa.
- S6. Helada: regla escalón (0.3 en floración, 0.7 vegetativa).
- S7. Umbrales de calor fuera de Teixeira 2013: derivados de ECOCROP.
- S8. Clases de N y rastrojo: conocimiento agronómico general, no medición.
- S9. Cultivos de cobertura: parámetros por analogía.
- S10. Rendimiento **relativo** al potencial; sin precios. `value_weight = 1` para todos salvo que el usuario lo cambie.
- S11. Un balde de suelo; no se modela anegamiento, plagas, malezas ni fallas de emergencia.
- S12. Las tendencias de lluvia en reanálisis pueden incluir artefactos del sistema de observación; por eso se reporta `p_value` y se dice "no significativo" cuando corresponde.

## 5. Generación de alternativas

### 5.1 Planes anuales

```
viable(c, g)   = media_eval(Ȳ[c, g, "fallow"]) >= VIABLE_MIN   (VIABLE_MIN_COVER si c no es cosechable)
simples        = { (c, g) : c cosechable, viable }
dobles(cA, cB) = pares (gA, gB) con ambos viables, al menos uno cosechable,
                 siembra_B >= cosecha_A + TURNAROUND_DAYS  y  cosecha_B + TURNAROUND_DAYS <= siembra_A + 365
Para cada tupla de cultivos (cA) o (cA, cB): quedarse con UNA combinación de fechas:
    orden lexicográfico sobre la tabla SUAVIZADA: (bad_seasons asc, mean_productivity desc, índices de fecha asc)
=> como mucho 12 + 13·13 planes
```

### 5.2 Rotaciones candidatas

- Ciclo 1 año: todos los planes.
- Ciclo 2 años: pares {p, q} de planes con multiconjunto de cultivos distinto, tomados de `top30(bad asc, mean_P desc) ∪ top10(soil desc)`; válidos según §4.6 (los modos del primer slot de cada año se recalculan con el otro plan como predecesor).
- Toda candidata se evalúa con la tabla **sin suavizar** y se le calcula el suelo.

### 5.3 Selección (determinista, secuencial)

```
B = rotación actual (tal cual la ingresó el usuario, sin reoptimizar)

ADAPTADA — cambio mínimo:
  C_A = rotaciones con el mismo nº de años y de slots por año que B, que difieren de B en a lo sumo UN cultivo
        (por posición), con fechas reoptimizadas según §5.1, y distintas de B (algún cultivo o alguna fecha)
  filtro: mean_P >= ADAPT_MIN_PROD·mean_P(B)   (si queda vacío, se quita el filtro y se anota en relaxed_constraints)
  elegir: (bad_seasons asc, p10_index desc, mean_P desc, nº de cambios asc, id asc)
  improves_on_current = bad < bad(B)  o  mean_P > 1.02·mean_P(B)

REGENERATIVA — mejor suelo con pérdida acotada:
  C_R = candidatas de §5.2 con multiconjunto de cultivos distinto de B y de ADAPTADA
  filtros: soil.total >= soil(B) + REGEN_MIN_SOIL_GAIN ; mean_P >= (1 − REGEN_MAX_LOSS)·mean_P(B) ; bad <= bad(B)
  relajación en orden si queda vacío (cada paso se anota): pérdida 0.20 -> 0.30 ; quitar bad <= bad(B) ; ganancia de suelo 10 -> 1
  elegir: (soil.total desc, mean_P desc, id asc)

DIVERSIFICADA (opcional):
  C_D = ciclo de 2 años, >= 3 familias, >= 3 cultivos cosechables distintos, soil >= soil(B),
        multiconjunto distinto de las anteriores
  elegir: entre las de bad <= bad(B): (mean_P desc, bad asc) ; si no hay: (bad asc, mean_P desc)
```

`id` de una rotación = string canónico `"soya@11-16+soya@05-01|maiz@11-01"`. Si un perfil no tiene ninguna candidata ni tras relajar, se omite y el pipeline falla solo si quedan menos de 3 rotaciones en total (en ese caso se completa con la 2ª mejor de ADAPTADA).

## 6. Tests mínimos (valor esperado → tolerancia)

**Calendario** — C1: lat −17, campaña 2015, "11-16" → 2015-11-16. C2: lat −17, 2015, "04-16" → 2016-04-16. C3: lat 40, 2015, ambas → 2015. C4: campañas válidas S = 1991..2024, N = 1992..2024; before S = 1991..2005, eval S = 2005..2024.

**ET0** — E1: Ra(lat −20°, J=246) = 32.2 ± 0.3 (FAO-56 ej. 8). E2: Ra(lat 50.8°, J=187) = 41.09 ± 0.3 (FAO-56 ej. 18). E3: PM con tmax 21.5, tmin 12.3, rh 73.5, ws 2.078, rs 22.07, lat 50.8°, z 100, J 187, ps NaN → 3.6 ≤ ET0 ≤ 4.0 (el ejemplo da 3.88 con RHmax/RHmin; con RH media ≈ 3.8). E4: Hargreaves mismo día → 4.06 ± 0.15. E5: `add_et0` con rh=NaN en un día → `et0_method == "hg"` ese día y "pm" el resto.

**Cultivo** — K1 (soya 20/30/60/25, Kc .40/1.15/.50): kc(0)=0.40, kc(35)=0.775, kc(50)=1.15, kc(109)=1.15, kc(134)=0.50+0.65/25=0.526 (±0.001). K2: sens = [45, 75). K3: N = 135.

**Balance** — W1: `runoff(prec=50, CN=78)` → S=71.64, RO=(50−14.33)²/(50+57.31)=11.86 ± 0.05; `runoff(10, 78)` = 0. W2: lluvia 10 mm/día, et0 5 → Ks=1 siempre, ratio=1. W3: cierre de masa en 200 días aleatorios (semilla fija): `Dr_fin = Dr_0 − ΣPe + ΣETa + ΣDP` ± 1e−6. W4: prec = 0.5 mm con et0 = 5 → Pe = 0.

**Térmico** — H1: trapecio(10/20/33/38): x=15→0.5, 25→1, 35.5→0.5, 40→0. H2: tmax constante = Tcrit → f_calor=1; = Tlim → 0; punto medio → 0.5. H3: tmin=−1 dentro de sens → 0.3; tmin=−4 fuera de sens (y ≥0 dentro) → 0.7; tmin=−1 solo fuera de sens → 1.0. H4: sin calor ni frío → 1.

**Slot** (clima sintético constante, soya, franco) — S1 húmedo (prec 10, et0 5, tmax 30, tmin 20): Y_rel = 1.0 ± 1e−9. S2 seco (prec 0 todo el periodo incl. spin-up, modo crop): `1 − ratio > 0.8` y Y_rel < 0.35. S3 monotonía: escalar la lluvia ×1.5 nunca baja Y_rel. S4: modo "crop" ≤ modo "fallow" en Y_rel con lluvia escasa (2 mm/día). S5: vector de 3 campañas idénticas → 3 resultados idénticos.

**Rotación** — R1: soya@11-16 + soya@05-01, lat<0: cosecha A = 11-16 + 135 d = 03-31; gap B = 31 d → modo "fallow"; con B@04-16 gap = 16 d → "crop". R2: slots solapados → inválida. R3: con Y sintético [1.0, 0.5] en un año de 2 slots, I = 0.75, no mala; [0.7, 0.4] → I = 0.55, mala. R4: rotación de 2 años = media de fases. R5: cobertura no entra en Pot.

**Suelo** — G1 soya-soya: nitrogen = 80, diversity = 15, organic_matter = 33.3. G2 soya + maíz (mismo año): nitrogen = 40, diversity = 65, organic_matter = 66.7. G3 maíz solo: nitrogen = 30, diversity = 15, organic_matter = 50. G4 erosión: W concentrado en un offset con cobertura 1.0 → 100; en offset de barbecho tras soya → 30.

**Clima** — M1: serie sintética seca hasta el offset 100 y luego 10 mm/día → onset = 100. M2: 12 días secos dentro de la estación → `dry_spells = 1`, `max_dry_spell = 12`. M3: tmax = 36 en 7 días → `hot_days = 7`. M4: before y recent idénticos → delta = 0, `significant = False`.

**Alternativas** — A1: ningún plan viola `TURNAROUND_DAYS`. A2: determinismo (dos corridas → mismos ids). A3: una sola combinación de fechas por tupla de cultivos. A4: los multiconjuntos de cultivos de actual / regenerativa / adaptada cumplen las reglas de distinción. A5: con candidatas sintéticas donde nada cumple la pérdida 0.20 → `relaxed_constraints` no vacío. A6: ADAPTADA difiere de B en ≤1 cultivo.

**Fichas** — F1: todo número en `text` ∈ evidence. F2: toda ficha tiene ≥1 claim en why, benefits o "sin beneficios medibles", y ≥2 en risks. F3: todo `Source.parameters` ⊂ nombres POWER de §2.3 o lista vacía con dataset "Regla agronómica".

**API** — P1: `POST /analyze` con el demo y POWER mockeado desde el fixture → 200, 3 rotaciones, orden actual/adaptada/regenerativa. P2: dos llamadas → JSON idéntico byte a byte. P3: crop_id inexistente → 422.

## 7. Demo y pitch (3 min)

Punto demo: lote agrícola en la zona de expansión este de Santa Cruz (Cuatro Cañadas/Pailón). **Coordenadas a confirmar sobre el mapa** (el centro de la ciudad da NDVI urbano). Rotación actual: soya verano (11-16) → soya invierno (05-01).

| Tiempo    | Pantalla              | Qué se dice                                                                                                                                                                                         |
| --------- | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0:00–0:25 | Portada               | "Tu rotación fue diseñada para el clima de 2005. Con datos NASA te mostramos cómo cambió y qué rotación encaja hoy."                                                                                |
| 0:25–0:50 | (a) Mapa + formulario | Clic en el lote, rotación actual en 3 selecciones. Sin registro, sin sensores.                                                                                                                      |
| 0:50–1:25 | (b) Tu clima cambió   | 2-3 métricas con mayor cambio, leídas del resultado real (no guionar cifras antes de N2). Mostrar una marcada "no significativo": el sistema no exagera.                                            |
| 1:25–2:20 | (c) Comparación       | Tabla: campañas malas X de 20, productividad, suelo. Abrir una ficha: por qué / beneficios / riesgos, y el chip de evidencia con el parámetro NASA. Tira de 20 campañas: cuáles fallaron y por qué. |
| 2:20–2:40 | Calendario            | Lluvia y ET0 antes/ahora con las ventanas de cada cultivo y la floración resaltada.                                                                                                                 |
| 2:40–3:00 | Cierre                | Sin ML ni caja negra: cada cifra se recalcula desde POWER. Límites dichos en voz alta (50 km, rendimiento relativo). Siguiente paso: validación con NDVI MODIS.                                     |

Checklist requisito → dónde se ve:

| Requisito del challenge                 | Dónde                                                      |
| --------------------------------------- | ---------------------------------------------------------- |
| ≥3 estrategias incluida la actual       | Vista (c), columnas Actual / Adaptada / Regenerativa       |
| Por qué se sugiere                      | `card.why`                                                 |
| Riesgos                                 | `card.risks` + tira de campañas malas                      |
| Beneficios                              | `card.benefits`                                            |
| Datos NASA específicos que la respaldan | chip de evidencia por claim (dataset, parámetros, periodo) |
| Datos satelitales + realidad local      | vista (b) + suelo y rotación ingresados por el usuario     |
| Qué sembrar a continuación              | primer slot de la rotación elegida, con fecha              |

## 8. Riesgos y fallbacks

| Riesgo                                            | Señal                                | Respuesta                                                                                        |
| ------------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------ |
| POWER caído o lento en la demo                    | timeout                              | caché en disco + `demo_santa_cruz.json` estático en el frontend; banner "modo demo offline"      |
| El modelo no discrimina (0 o 20 campañas malas)   | N2 punto 3                           | revisar AWC/spin-up con registro del cambio; último recurso: reportar percentiles y decirlo      |
| Ninguna alternativa mejora a la actual            | `improves_on_current = false`        | se muestra tal cual; es un resultado válido y más creíble que forzar una mejora                  |
| Tabla de slots lenta (>30 s)                      | T6.1                                 | T6.2 (prefiltro térmico); si no alcanza, reducir rejilla a 12 fechas (mensual)                   |
| MODIS tarda (≈5 s por fecha, máx. 10 por request) | —                                    | solo offline y precacheado; nunca en `/analyze`                                                  |
| Valores de cultivos sin cotejar                   | `verificar: true`                    | la UI muestra "parámetros pendientes de verificación: n"; cotejar al menos los 5 del demo (T0.5) |
| Agente cambia una fórmula                         | diff en `engine/` sin tarea asociada | tests de §6 fijan los valores; regla de AGENTS.md                                                |

Orden de recorte si falta tiempo: F7 completo → T5.5 calendario → `dry_spells`/`cessation` del perfil climático → rotaciones de 2 años (dejar solo ciclo 1 año) → vista (b) reducida a 3 métricas. **No se recorta**: tests de §6 del motor, fichas con evidencia, 3 rotaciones.
