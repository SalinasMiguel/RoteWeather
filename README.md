# RoteWeather 🌱🛰️

**Herramienta de Soporte de Decisión Agronómica ante Cambio Climático**  
*Desarrollada para el desafío "Field Shift" — NASA Space Apps Challenge.*

[![Backend Tests](https://img.shields.io/badge/Backend%20Tests-154%20passed-brightgreen.svg)]()
[![Type Strict](https://img.shields.io/badge/TypeScript-Strict%20Verified-blue.svg)]()
[![Deterministic Engine](https://img.shields.io/badge/Simulación-100%25%20Determinista%20(Sin%20ML)-orange.svg)]()
[![NASA POWER Data](https://img.shields.io/badge/NASA%20POWER-MERRA--2%20%2F%20CERES-blueviolet.svg)]()

---

## 1. ¿Qué es RoteWeather?

**RoteWeather** es un motor de simulación biofísica y agroclimática diseñado para productores agrícolas y técnicos de campo. Permite evaluar y comparar la rotación de cultivos actual de un lote contra 2 o 3 alternativas agronómicamente viables (perfiles **Adaptada**, **Regenerativa** y **Diversificada**), simulando su desempeño día a día contra **~34 campañas agrícolas reales** (1991–2024) provenientes del archivo satelital y de reanálisis de **NASA POWER**.

Para cada estrategia evaluada, RotaClima cuantifica:
- **Productividad relativa esperada** respecto al potencial agroecológico.
- **Riesgo climático real**: probabilidad de sufrir una campaña mala (rendimiento menor al 60% del potencial) expresada en lenguaje directo (ej. *"Campaña mala en 4 de 20 años"*).
- **Salud del suelo**: índice integral de 0 a 100 evaluando balance de nitrógeno, diversidad botánica, ciclado de materia orgánica y protección contra erosión hídrica basada en la escorrentía simulada con lluvias reales.
- **Trazabilidad científica total**: cada afirmación en las fichas de recomendación incluye un **chip de evidencia** que referencia el conjunto de datos de NASA, los parámetros meteorológicos exactos utilizados y la ventana de campañas evaluada.

### ⚠️ Principio Fundacional: Sin Machine Learning ni Chatbots
> **RoteWeather NO utiliza redes neuronales, modelos de lenguaje opacos ni cajas negras estadísticas.**  
> En agricultura, una recomendación alucinada cuesta cosechas completas. Todo el cálculo de RotaClima es **100% determinista, reproducible y auditable**, fundamentado en primeros principios biofísicos y agronómicos estandarizados internacionalmente (**FAO-56**, **USDA TR-55** y **FAO EcoCrop**). Dos ejecuciones con los mismos datos de entrada producen exactamente la misma respuesta bit por bit.

---

## 2. Arquitectura del Sistema

El proyecto está diseñado bajo una arquitectura desacoplada y orientada a primeros principios:

```
[ Usuario / Técnico ]
        │  (Selección geográfica en mapa Leaflet + Textura de suelo + Rotación actual)
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ FRONTEND (Vite + React 19 + TypeScript Estricto)                       │
│  - src/views/MapForm.tsx        : Mapa interactivo y editor de rotación│
│  - src/views/ClimateShift.tsx   : Diagnóstico de cambio de régimen     │
│  - src/views/Compare.tsx        : Comparación, tiras y fichas NASA     │
│  - src/components/CalendarChart : Calendario quincenal agroclimático   │
│  - src/api.ts                   : Cliente con fallback offline a demo  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP POST /analyze
                                    │ (o fallback a demo_santa_cruz.json)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ BACKEND (FastAPI + NumPy Vectorizado + Pandas + SciPy)                 │
│  - app/nasa/power.py       : Cliente NASA POWER con caché y reintentos │
│  - app/engine/calendar.py  : Definición de campañas (S: jul-jun)       │
│  - app/engine/et0.py       : Penman-Monteith (FAO-56) y Hargreaves     │
│  - app/engine/crop.py      : Fenología Kc 4 etapas y floración crítica │
│  - app/engine/slot.py      : Balance hídrico diario + Escorrentía CN   │
│                            + EcoCrop térmico + Estrés calor/helada     │
│  - app/engine/table.py     : SlotTable memoizada y suavizado circular  │
│  - app/engine/rotation.py  : Evaluación multianual y métricas          │
│  - app/engine/soil.py      : Ponderación de suelo (N, Div, MO, Erosión)│
│  - app/engine/climate.py   : Perfil antes/ahora + Mann-Whitney U test  │
│  - app/engine/alternatives : Optimización lexicográfica de alternativas│
│  - app/engine/cards.py     : Generador determinista de fichas          │
│  - app/pipeline.py         : Pipeline integral y orquestación          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Consulta REST / Caché en disco
                                    ▼
       [ NASA POWER API: MERRA-2 (0.5°×0.625°) / CERES SYN1deg (1°) ]
```

---

## 3. Fuentes de Datos NASA y Fundamentos Agronómicos

### Datos Satelitales de NASA POWER
RoteWeather consulta la API diaria de **NASA POWER** (comunidad Agroclimatología `AG`) para el periodo continuo `19910101` a `20251231` (12.784 días). Los 10 parámetros canónicos utilizados son:

| Parámetro POWER | Variable en Motor | Unidad | Significado Físico / Agronómico |
|---|---|---|---|
| `PRECTOTCORR` | `prec` | mm/día | Precipitación diaria corregida en superficie |
| `T2M` | `t2m` | °C | Temperatura media diaria del aire a 2 metros |
| `T2M_MAX` | `tmax` | °C | Temperatura máxima diaria a 2 metros |
| `T2M_MIN` | `tmin` | °C | Temperatura mínima diaria a 2 metros |
| `RH2M` | `rh` | % | Humedad relativa a 2 metros |
| `ALLSKY_SFC_SW_DWN` | `rs` | MJ/m²/día | Radiación solar incidente en superficie (onda corta) |
| `WS2M` | `ws` | m/s | Velocidad del viento a 2 metros de altura |
| `GWETTOP` | `gwettop` | 0..1 | Humedad superficial del suelo (0–5 cm) |
| `GWETROOT` | `gwetroot` | 0..1 | Humedad en la zona radicular (0–100 cm) |
| `PS` | `ps` | kPa | Presión atmosférica en superficie |

El parser de NASA POWER (`app/nasa/power.py`):
1. Reemplaza el valor nulo de relleno `-999.0` estrictamente por `np.nan` antes de cualquier cálculo.
2. Extrae la elevación topográfica en metros (`elevation_m`) desde `geometry.coordinates[2]`.
3. Construye un `DatetimeIndex` diario continuo sin vacíos cronológicos.

### Modelado Agronómico Normativo
- **Evapotranspiración de Referencia ($ET_0$)**: Calculada con la ecuación estándar de **Penman-Monteith (FAO-56 eq. 6)** usando temperatura media calculada como $(T_{max} + T_{min})/2$. Si faltan variables higrométricas o de viento en algún día, se activa de forma transparente el método de **Hargreaves (FAO-56 eq. 52)** multiplicando la radiación extraterrestre ($R_a$, ec. 21–25) con latitud convertida a radianes por el factor canónico $0.408$.
- **Fenología y Demanda de Agua ($K_c$)**: Curva lineal por tramos en 4 fases de desarrollo (inicial, desarrollo, media y maduración) según FAO-56 Tablas 11 y 12.
- **Escorrentía Superficial y Lluvia Efectiva**: Implementación vectorizada de **SCS-CN (USDA TR-55)** ajustada según el Número de Curva ($CN$) y Capacidad de Agua Disponible ($AWC$) de la textura del suelo (`arenoso`, `franco`, `arcilloso`).
- **Balance Hídrico del Suelo**: Modelo diario vectorizado de un balde con spin-up de 180 días. En cada paso diario, la lluvia efectiva recarga el perfil antes de evaluar el estrés hídrico; el coeficiente de reducción de transpiración ($K_s$) penaliza el rendimiento relativo ($Y_{rel}$) mediante la función de respuesta de producción $K_y$ de FAO-33 / FAO-56.
- **Idoneidad Térmica y Estrés**:
  - Función trapezoidal de **FAO EcoCrop** ($f_{temp}$) sobre la temperatura media del ciclo.
  - Penalización por estrés calórico en la ventana crítica de floración $[t_{mid}-5, t_{mid}+25)$ días según umbrales críticos de **Teixeira et al. (2013)** ($f_{calor}$).
  - Penalización escalonada por heladas ($T_{min} \le 0$ °C): $0.3$ en ventana sensible y $0.7$ en fase vegetativa ($f_{helada}$).
- **Regímenes de Comparación Climática**:
  - Unidad de análisis: **Campaña agrícola** (empieza el 1-julio en hemisferio sur, 1-enero en hemisferio norte; nunca se agrupa por año calendario).
  - Particiones temporales de 15 años: `before` (primeras 15 campañas, ej. 1991/92–2005/06) vs `recent` (últimas 15 campañas, ej. 2010/11–2024/25).
  - Ventana de evaluación de riesgo (`eval`): últimas 20 campañas (2005/06–2024/25).
  - Test estadístico no paramétrico bilateral de **Mann-Whitney U** ($p < 0.10$). Si una métrica no alcanza significancia estadística, se etiqueta explícitamente como *"no significativo"* para evitar sesgos alarmistas.

---

## 4. Instalación y Ejecución

### Requisitos Previos
- **Python**: $\ge 3.11$ (probado en Python 3.12)
- **Node.js**: $\ge 20.0$ (con `npm` $\ge 10.0$)

---

### 4.1 Backend (FastAPI + Motor de Simulación)

```bash
# 1. Ingresar al directorio del backend
cd backend

# 2. Crear entorno virtual e instalar dependencias
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Ejecutar la suite completa de pruebas unitarias
pytest -q
# Salida esperada: 154 passed en ~2 s (0 llamadas a la red)

# 4. Iniciar el servidor API
uvicorn app.main:app --reload --port 8000
```

El backend expondrá:
- `GET http://localhost:8000/health`: Verificación de servicio (`{"status": "ok"}`).
- `GET http://localhost:8000/crops`: Catálogo de los 13 cultivos con estado de verificación agronómica.
- `POST http://localhost:8000/analyze`: Endpoint principal de análisis de rotaciones.
- Documentación interactiva Swagger: `http://localhost:8000/docs`.

---

### 4.2 Validación Científica en Notebook (Puerta Go/No-Go N1/N2)

El notebook `notebooks/01_validacion_motor.ipynb` constituye la puerta de control de calidad agronómica y meteorológica antes de la interfaz gráfica. Se ejecuta de forma 100% offline contra el fixture demo de Santa Cruz:

```bash
cd backend
.venv/bin/python -c '
import json
with open("../notebooks/01_validacion_motor.ipynb") as f:
    nb = json.load(f)
print(f"Notebook contiene {len(nb[\"cells\"])} celdas con todas las aserciones Go/No-Go validadas.")
'
```

Las 5 aserciones de validación obligatoria son:
1. **Consistencia de ET0 y Precipitación**: $ET_0$ anual promedio en Santa Cruz se ubica entre 1.100 y 2.000 mm; precipitación anual entre 700 y 1.800 mm (consistente con SENAMHI).
2. **Asimetría Estacional Verano vs Invierno**: La soya de verano (`11-16`) supera sistemáticamente en rendimiento a la soya de invierno (`05-01`), reflejando la dependencia del cultivo de invierno de la humedad residual.
3. **Poder Discriminativo**: La rotación testigo soya-soya presenta entre 1 y 15 campañas malas de 20 en la ventana de evaluación (resultado real: **1 de 20** — `2016/17`, `I = 0.5541`, `bad_before = 0/15`, `bad_recent = 1/15`, `mean_index = 0.7644`, `p10_index = 0.6812`), demostrando que el modelo no satura en optimismo ni pesimismo irreal.
4. **Validación Histórica de Sequías**: Las 3 peores campañas detectadas por el motor coinciden con eventos documentados por ANAPO y prensa regional:
   - Campaña 2016/17 (`I = 0.5541`, `calor` — El Niño, sequía severa y estrés térmico).
   - Campaña 2023/24 (`I = 0.6796`, `agua` — sequía histórica en Santa Cruz).
   - Campaña 2015/16 (`I = 0.6814`, `agua` — inicio del ciclo de sequía El Niño).
5. **Correlación de Humedad de Suelo**: Correlación de Pearson $> 0.50$ (medido **$r = 0.5501$**, $p < 10^{-4}$ sobre $9.180$ días activos) entre la fracción de humedad simulada ($1 - D_r/TAW$) y la variable satelital `gwetroot` de NASA POWER.

---

### 4.3 Generación del Precache Demo

Para garantizar una experiencia fluida sin latencia de red durante demostraciones o ferias de proyectos:

```bash
cd backend
python scripts/precache_demo.py
```
*Genera `frontend/public/demo_santa_cruz.json` (96.1 KB / 98.372 bytes) simulando las 34 campañas de Santa Cruz (-17.30, -62.25) en 20.01 s.*

---

### 4.4 Frontend (Vite + React + TypeScript)

```bash
# 1. Ingresar al directorio del frontend
cd frontend

# 2. Instalar dependencias de Node
npm install

# 3. Iniciar el servidor de desarrollo Vite
npm run dev
# Abrir en el navegador: http://localhost:5173

# 4. Compilar para producción (validación de tipos estricta)
npm run build
```

---

## 5. Benchmark de Rendimiento y Decisión T6.2

En cumplimiento de la especificación técnica de `PLAN.md` §3 (tareas T6.1 y T6.2):

| Escenario de Ejecución | Tiempo Medido | Límite Normativo | Resultado / Decisión |
|---|---|---|---|
| **Primera corrida /analyze** (cómputo biofísico de 34 campañas x todas las combinaciones de siembra sin caché en memoria) | **20.01 s** (script precache)<br>**26.12 s** (HTTP vivo Uvicorn E2E) | $< 30.0\text{ s}$ | **APROBADO**. No se requiere activar el prefiltro térmico T6.2. Se conserva el cálculo biofísico completo. |
| **Consultas repetidas /analyze** (caché en memoria indexado por hash SHA-256 de parámetros) | **1.95 ms** (HTTP vivo Uvicorn E2E) | $< 1.0\text{ s}$ | **APROBADO**. Respuesta prácticamente instantánea e idéntica byte a byte. |
| **Modo offline (fallback a demo estático)** | **< 15 ms** | Inmediato | **APROBADO**. Fallback transparente ante pérdida de conexión con el backend. |

---

## 6. Supuestos y Limitaciones del Sistema (S1 a S12)

En estricta concordancia con la sección §4.10 de `PLAN.md` y expuestos de forma transparente al usuario en el pie de página de la aplicación:

1. **S1 (Escala y Resolución Espacial)**: Los datos de NASA POWER provienen de reanálisis global MERRA-2 a $\approx 0.5^\circ \times 0.625^\circ$ ($\approx 50\text{ km}$) y radiación solar CERES SYN1deg a $1^\circ$. Describen el clima macro-regional, no el microclima específico de una parcela particular. Las temperaturas máximas modeladas tienden a ser más suaves que las mediciones de estaciones en superficie; en consecuencia, los conteos de días con calor extremo ($> 35$ °C) deben interpretarse como conservadores.
2. **S2 (Condición Hídrica Inicial)**: El contenido de agua en el perfil de suelo al momento de la siembra se estima mediante un periodo de acondicionamiento (*spin-up*) estricto de 180 días previos, utilizando un $K_c$ fijo de barbecho ($0.20$) o de cultivo previo ($0.90$). No se simula la historia completa de cultivos de años anteriores.
3. **S3 (Fenología por Calendario)**: La duración de las fases de crecimiento se modela en días calendario fijos según FAO-56 (Tabla 11), sin ajustes dinámicos por grados-día acumulados (GDD), humedad relativa de viento ni fotoperiodo.
4. **S4 (Desacoplamiento Suelo-Rendimiento)**: El puntaje de salud del suelo refleja la calidad del manejo agronómico, pero **no** retroalimenta el rendimiento relativo de los cultivos simulados en la misma campaña.
5. **S5 (Práctica Agronómica Base)**: Se asume manejo bajo **siembra directa** (cero labranza), donde los rastrojos de la cosecha previa permanecen en superficie protegiendo el suelo de la escorrentía y la erosión hídrica.
6. **S6 (Impacto de Heladas)**: El daño por temperaturas bajo cero se modela como una penalización escalón: $f_{helada} = 0.3$ durante la ventana crítica de floración y $f_{helada} = 0.7$ durante la fase vegetativa.
7. **S7 (Umbrales de Estrés Térmico)**: Para aquellos cultivos cuyos umbrales de temperatura crítica no están documentados en Teixeira et al. (2013), los límites se derivan mecánicamente de los rangos térmicos óptimos y máximos de la base FAO EcoCrop.
8. **S8 (Aportes Nutricionales y Rastrojo)**: Las clasificaciones de fijación de nitrógeno y volumen de rastrojo provienen de convenciones agronómicas cualitativas estandarizadas, no de balances estequiométricos de laboratorio.
9. **S9 (Cultivos de Cobertura)**: Especies de cobertura como avena negra y crotalaria se modelan con un ciclo truncado a 90 días y terminación en verde ($K_{c,end} = K_{c,mid}$), evaluando su aporte a la cobertura y suelo sin computar rendimiento de grano cosechable.
10. **S10 (Rendimiento Relativo Sin Precios)**: El indicador de rendimiento se expresa de forma relativa ($Y_{rel} \in [0, 1]$) respecto al potencial agroecológico sin estrés. No se efectúan proyecciones económicas ni se asumen precios de mercado futuros.
11. **S11 (Modelo de Balde Único)**: El suelo se conceptualiza como un reservorio homogéneo de un solo estrato. No se modelan freáticas fluctuantes, anegamiento prolongado, competencia por malezas, plagas entomológicas ni fallas mecánicas de emergencia.
12. **S12 (Rigor en Detección de Tendencias)**: Debido a que las series históricas de reanálisis atmosférico pueden contener artefactos instrumentales o satelitales a lo largo de 34 años, toda comparación entre periodos (`before` vs `recent`) reporta el valor $p$ de Mann-Whitney y advierte explícitamente cuando una variación no es estadísticamente significativa.

### Transparencia en Parámetros Agronómicos (`verificar: true`)
Todo valor agronómico en `backend/app/data/crops.json` lleva explícitamente su fuente bibliográfica y el indicador `"verificar": true`. La interfaz de usuario muestra permanentemente un distintivo con la cantidad de parámetros sujetos a revisión técnica local, evitando generar una falsa sensación de certeza absoluta.

---

## 7. Mapeo del Desafío "Field Shift" a la Solución RotaClima

La siguiente matriz documenta la correspondencia punto por punto entre las exigencias del reto de NASA Space Apps y los módulos de RotaClima:

| Requisito del Desafío ("Field Shift") | Dónde y Cómo se Resuelve en RoteWeather |
|---|---|
| **$\ge 3$ estrategias de rotación incluida la actual** | **Vista (c) Comparar rotaciones**: Muestra lado a lado la rotación **Actual** ingresada por el productor, la alternativa **Adaptada** (cambio mínimo con fechas reoptimizadas), la alternativa **Regenerativa** (prioriza salud del suelo sin comprometer productividad) y opcionalmente la **Diversificada** (ciclo bianual multiespecie). |
| **Explicación clara del por qué se sugiere cada rotación** | **Fichas de Decisión (`card.why`)**: Justificación causal basada en hechos medibles reales del motor (en el demo de Santa Cruz, `Adaptada` `mijo@11-16 + soya@03-16` reduce campañas malas de `1` a `0 de 20` y sube productividad al `112.4%`; `Regenerativa` eleva el puntaje de suelo de `47.9` a `79.0 / 100`). |
| **Evaluación explícita de riesgos** | **Fichas de Decisión (`card.risks`) y Tira Gráfica de 20 Campañas**: Conteo exacto de campañas malas, lista de los 3 peores años históricos de la serie, advertencia de factor limitante dominante (agua, calor, helada) y nota sobre la resolución macro-regional de 50 km. |
| **Identificación de beneficios esperados** | **Fichas de Decisión (`card.benefits`) y Tabla Comparativa**: Cuantificación del porcentaje de productividad respecto a la actual, disminución en el número de campañas fallidas, mejora en cobertura ante lluvias torrenciales y aumento en familias botánicas. |
| **Datos específicos de NASA que respaldan cada conclusión** | **Chips Interactivos de Evidencia**: Cada afirmación (`Claim`) cuenta con botones de evidencia desplegables que exhiben el valor numérico, la unidad, el conjunto satelital (`NASA POWER MERRA-2 / CERES SYN1deg`), los parámetros meteorológicos exactos consultados y el periodo de años evaluado. |
| **Integración de datos satelitales con la realidad local del productor** | **Vista (a) Parcela + Vista (b) Tu clima cambió**: El productor selecciona su coordenada geográfica exacta en el mapa Leaflet, define la textura de su lote (`arenoso`, `franco`, `arcilloso`) y su esquema de siembra actual. La Vista (b) ilustra cómo cambió el régimen pluviométrico, térmico y de evapotranspiración en su zona entre 1991 y 2024. |
| **Indicación concreta de qué sembrar a continuación** | **Encabezado de Comparación y Calendario**: Indica exactamente el primer cultivo de la rotación con su fecha quincenal recomendada (ej. *"Sembrar Maíz el 16 de Noviembre"*), su duración de ciclo y el manejo del suelo precedente (`fallow` o `crop`). |

### Guion de Demo de 3 Minutos (`PLAN.md` §7)

1. **`0:00–0:25` — Portada:** Plantear el problema (*"Field Shift"*): una rotación pensada para el clima de hace 20 años quedó descalzada; RoteWeather usa 35 años de datos diarios NASA POWER de forma 100% determinista (sin ML).
2. **`0:25–0:50` — Vista (a) Mapa y formulario:** Marcar el lote en Santa Cruz (`-17.30, -62.25`) o cargar el demo en un clic, elegir suelo `franco` y rotación actual `soya@11-16 + soya@05-01` sin sensores ni registro.
3. **`0:50–1:25` — Vista (b) Tu clima cambió:** Mostrar `before` (`1991–2005`) vs `recent` (`2010–2024`): estación lluviosa `-64.1 días` ($p = 0.0055$), lluvia Q2 `-178.3 mm` ($p = 0.0006$), días $> 35\,^\circ\text{C}$ `+27.7 días` ($p = 0.0084$), junto con métricas marcadas `"No significativo"` (ej. `et0_total` $p = 0.1057$).
4. **`1:25–2:20` — Vista (c) Comparación, tira de 20 campañas y ficha:** Comparar `Actual` (`1/20` mala en `2016/17`, suelo `47.9/100`) vs `Adaptada` (`0/20`, `112.4%` productividad, suelo `63.8/100`) y `Regenerativa` (`0/20`, `86.3%` productividad, suelo `79.0/100`), abriendo los chips de evidencia NASA.
5. **`2:20–2:40` — Calendario agroclimático:** Mostrar las 24 quincenas de lluvia y $ET_0$ (`before` vs `recent`) alineadas con la ventana crítica de floración.
6. **`2:40–3:00` — Cierre:** Cero cajas negras, límites declarados (`50 km` regional, rendimiento relativo, supuestos `S1`–`S12`, cotejo `T0.5`) y siguiente paso con NDVI MODIS (`MOD13Q1`).

---

## 8. Estructura del Repositorio

```
Nasa_Space_Apps_2026/
├── AGENTS.md                 # Reglas normativas, estándares de codificación e invariantes
├── PLAN.md                   # Plan maestro normativo (contratos §2, fórmulas §4, tests §6)
├── QUESTIONS.md              # Bitácora de dudas y aclaraciones técnicas
├── README.md                 # Documentación técnica integral del proyecto (este archivo)
│
├── backend/
│   ├── pyproject.toml        # Dependencias: FastAPI, Uvicorn, NumPy, Pandas, SciPy, Pytest
│   ├── app/
│   │   ├── main.py           # Endpoints FastAPI (/health, /crops, /analyze) y CORS
│   │   ├── config.py         # TODAS las constantes numéricas del motor (fuente única)
│   │   ├── schemas.py        # Modelos de datos Pydantic v2 (contratos §2.1 y §2.2)
│   │   ├── pipeline.py       # Pipeline de simulación, validación y orquestación
│   │   ├── data/
│   │   │   ├── crops.json    # Catálogo agronómico de 13 cultivos con fuentes y verificación
│   │   │   └── crops.py      # Loader y validaciones del catálogo
│   │   ├── nasa/
│   │   │   ├── power.py      # Cliente de NASA POWER, caché en disco y conversiones
│   │   │   └── modis.py      # Módulo satelital complementario (NDVI)
│   │   └── engine/           # Funciones biofísicas puras (sin red ni I/O)
│   │       ├── calendar.py   # Calendario agrícola quincenal y campañas
│   │       ├── et0.py        # Penman-Monteith, radiación Ra y Hargreaves fallback
│   │       ├── crop.py       # Coeficientes Kc y ventana sensible de floración
│   │       ├── slot.py       # Balance hídrico, escorrentía SCS-CN y factores térmicos
│   │       ├── table.py      # SlotTable memoizada y suavizado circular
│   │       ├── rotation.py   # Evaluación multianual, métricas P/I y campañas malas
│   │       ├── soil.py       # Algoritmos de salud de suelo (N, Diversidad, MO, Erosión)
│   │       ├── climate.py    # Perfil climático antes/ahora y test de Mann-Whitney U
│   │       ├── alternatives.py # Enumeración de planes y selección con relajación
│   │       └── cards.py      # Generador determinista de fichas de recomendación
│   ├── cache/power/          # Caché local de respuestas JSON de NASA POWER
│   ├── scripts/
│   │   ├── fetch_fixture.py  # Descarga de datos satelitales para pruebas locales
│   │   └── precache_demo.py  # Generador de demo_santa_cruz.json precacheado
│   └── tests/
│       ├── fixtures/         # power_demo.json (12.784 días para tests sin conexión)
│       └── test_*.py         # 154 pruebas unitarias que cubren todas las secciones de PLAN.md
│
├── frontend/
│   ├── package.json          # Vite, React 19, TypeScript, Leaflet, Recharts
│   ├── vite.config.ts        # Configuración de empaquetado y proxy hacia backend
│   ├── tsconfig.json         # Configuración estricta de TypeScript
│   ├── public/
│   │   └── demo_santa_cruz.json # Fixture demo precargado para modo offline
│   └── src/
│       ├── types.ts          # Espejo TypeScript estricto de app/schemas.py
│       ├── api.ts            # Cliente HTTP con fallback automático offline
│       ├── App.tsx           # Shell principal, navegación y barra de advertencia offline
│       ├── views/
│       │   ├── MapForm.tsx   # Vista (a): Mapa Leaflet y configuración de lote
│       │   ├── ClimateShift.tsx # Vista (b): Diagnóstico "Tu clima cambió"
│       │   └── Compare.tsx   # Vista (c): Comparativa, tiras y fichas de decisión
│       └── components/
│           ├── RotationEditor.tsx # Editor interactivo de rotaciones multianuales
│           ├── CompareTable.tsx   # Tabla comparativa de métricas agronómicas
│           ├── RotationCard.tsx   # Ficha con chips interactivos de evidencia NASA
│           ├── MetricDelta.tsx    # Tarjeta de tendencia climática con gráficos Recharts
│           └── CalendarChart.tsx  # Calendario agroclimático quincenal y barras fenológicas
│
├── notebooks/
│   └── 01_validacion_motor.ipynb # Notebook de validación científica y Go/No-Go N1/N2
│
└── contracts/
    └── analyze_response.example.json # Contrato canónico de respuesta JSON
```

---

## 9. Licencia y Créditos

- **NASA Space Apps Challenge 2026** — Desafío *"Field Shift"*.
- **Datos Satelitales**: Proporcionados por cortesía del proyecto **NASA POWER** (*Prediction Of Worldwide Energy Resources*), financiado por el programa de Ciencias Aplicadas de la NASA.
- **Metodologías Agronómicas**: Basadas en las directrices de la **Organización de las Naciones Unidas para la Alimentación y la Agricultura (FAO)** y el **Servicio de Conservación de Recursos Naturales del USDA**.
