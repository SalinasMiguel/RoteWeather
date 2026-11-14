# AGENTS.md — RotaClima

Leé esto completo al iniciar cada sesión. Después leé en `PLAN.md` la fila de tu tarea (§3) y las secciones que cita.

## Qué es

Herramienta de soporte de decisión para NASA Space Apps ("Field Shift"). Simula la rotación de cultivos del agricultor y 2-3 alternativas contra ~34 campañas reales de NASA POWER y devuelve rendimiento relativo, riesgo ("campaña mala en X de 20") y salud de suelo, con el dato NASA detrás de cada afirmación. **No hay ML ni chatbot.** Todo es determinista.

## Protocolo de trabajo

1. Una tarea por sesión. El ID (ej. `T2.4`) define objetivo, archivos y comando de aceptación.
2. Tocá **solo** los archivos listados en la tarea. Si necesitás otro, pará y escribilo en `QUESTIONS.md`.
3. Antes de terminar: corré el comando de aceptación y pegá la salida real. Si falla, decilo; no marques la tarea como hecha.
4. Si una fórmula, contrato o valor te parece incorrecto o ambiguo: **no lo arregles ni lo interpretes**. Escribí la duda en `QUESTIONS.md` (tarea, sección, qué no cierra) y detenete.
5. No agregues dependencias fuera de las de `pyproject.toml` / `package.json` sin pedirlo.

## Reglas duras

- `PLAN.md` §2 (contratos) y §4 (fórmulas) son normativos. Se copian, no se parafrasean ni se "mejoran".
- Toda constante numérica del motor vive en `backend/app/config.py`. Prohibido un literal mágico en `engine/`.
- Prohibido inventar valores agronómicos. Todo valor en `crops.json` lleva `fuente` y `verificar`. Solo un humano cambia `verificar` a `false`.
- Prohibido inventar cifras en textos. Las fichas salen de plantillas (§4.9) y cada número del texto existe en `evidence`.
- Determinismo: sin `random` sin semilla, sin `datetime.now()` en el motor, sin depender del orden de un `dict`/`set` para desempatar. Los desempates están definidos en §5.
- Nunca agrupar por año calendario. La unidad de tiempo es la **campaña agrícola** (§4.1): empieza el 1-jul si lat < 0, el 1-ene si lat ≥ 0.
- El valor `-999` de POWER se convierte a `NaN` en `nasa/power.py` y en ningún otro lugar. Nunca entra a una suma.
- Los nombres de parámetros POWER (`PRECTOTCORR`, `T2M_MAX`, …) aparecen solo en `nasa/power.py` y en `Source.parameters`. El resto del código usa las columnas renombradas.
- El motor no hace red. Solo `nasa/` y `scripts/` llaman a APIs. Los tests nunca tocan la red (usan `tests/fixtures/` o `httpx.MockTransport`).

## Nombres y unidades canónicas

| Nombre | Significado | Unidad |
|---|---|---|
| `prec`, `et0` | lluvia, evapotranspiración de referencia | mm/día |
| `tmax`, `tmin`, `t2m` | temperatura a 2 m | °C |
| `rh` | humedad relativa | % |
| `rs` | radiación solar en superficie | MJ/m²/día |
| `ws` | viento a 2 m | m/s |
| `ps` | presión en superficie | kPa |
| `season` | campaña agrícola, entero = año de inicio | — |
| `offset` | días desde el inicio de campaña | días |
| `slot` | (cultivo, fecha de siembra, modo) | — |
| `Dr`, `TAW`, `RAW` | agotamiento, agua total y fácilmente disponible | mm |
| `y_rel` | rendimiento relativo de un slot | 0..1 |
| `P`, `I` | productividad e índice de una rotación en una campaña | — , 0..1 |
| latitud en fórmulas de radiación | **radianes**, negativa al sur | rad |

Fechas de siembra: string `"MM-DD"` con día `01` o `16`. IDs de cultivo: minúsculas sin tildes (`soya`, `maiz`, `sorgo`…). Perfiles: `actual`, `adaptada`, `regenerativa`, `diversificada`. Factores limitantes: `agua`, `calor`, `helada`, `temperatura`, `ninguno`.

## Errores típicos a evitar (cada uno ya tiene test en PLAN.md §6)

1. Usar `t2m` como temperatura media en ET0 → se usa `(tmax + tmin)/2`.
2. Pasar la latitud en grados a `sin/cos/tan`.
3. Olvidar el `0.408` en Hargreaves (Ra está en MJ, no en mm).
4. Calcular el estrés antes de sumar la lluvia del día (§4.4: la lluvia entra primero).
5. Promediar `ETa/ETc` diario en vez de dividir las sumas.
6. Empezar el balance el día de siembra sin los 180 días de spin-up.
7. Evaluar rotaciones sobre listas de campañas distintas.
8. En rotaciones de 2+ años, simular una sola fase en vez de promediar todas.
9. Sumar cultivos de cobertura a la productividad.
10. Elegir fechas con la tabla suavizada y **reportar** métricas con la suavizada (se reportan sin suavizar).
11. Partir en el 31-dic un cultivo que cruza de año (hemisferio sur).
12. Rellenar datos faltantes con ceros o medias en silencio.

## Convenciones de código

- Backend: Python ≥ 3.11, type hints, funciones puras en `engine/` (entradas → salidas, sin estado global ni I/O). numpy vectorizado sobre campañas; el bucle explícito es sobre días.
- Docstring de una línea con la sección de PLAN.md que implementa: `"""PLAN §4.4 — paso diario del balance hídrico."""`
- Tests con pytest, nombre `test_<id>_<qué>` (ej. `test_W1_runoff_cn78`). Tolerancias con `pytest.approx`.
- Frontend: Vite + React + TS estricto, componentes de función, sin estado global externo. `src/types.ts` es espejo manual de `schemas.py`: si cambia uno, cambia el otro en la misma tarea.
- Textos de UI y mensajes de error en español. Identificadores de código en inglés, salvo las claves de `crops.json` (en español, ver §2.4).
- Sin secretos en el repo. POWER y MODIS ORNL no requieren credenciales.

## Comandos

```bash
# backend
cd backend && pip install -e ".[dev]"
pytest -q                              # todo
pytest -q tests/test_et0.py            # una tarea
uvicorn app.main:app --reload --port 8000
python scripts/fetch_fixture.py        # requiere red
python scripts/precache_demo.py

# frontend
cd frontend && npm install
npm run dev                            # http://localhost:5173
npm run build                          # debe pasar sin errores de tipos
```

## APIs externas (verificadas el 2026-11-12)

- POWER: `GET https://power.larc.nasa.gov/api/temporal/daily/point?parameters=...&community=AG&longitude=..&latitude=..&start=YYYYMMDD&end=YYYYMMDD&format=JSON`. Datos en `properties.parameter[PARAM][YYYYMMDD]`; faltante = `-999.0`; elevación en `geometry.coordinates[2]`. 35 años × 10 parámetros ≈ 2 MB en ≈ 3 s.
- MODIS (solo extra E1): `GET https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset?latitude=..&longitude=..&startDate=AYYYYDDD&endDate=AYYYYDDD&kmAboveBelow=0&kmLeftRight=0&band=250m_16_days_NDVI` con `Accept: application/json`. Máximo 10 fechas por request (más → HTTP 400). NDVI = `data[0] × 0.0001`. Lento: nunca en el camino de `/analyze`.

## Definición de terminado

Comando de aceptación en verde con salida pegada · solo archivos de la tarea modificados · ninguna constante fuera de `config.py` · ninguna fórmula distinta de §4 · `QUESTIONS.md` actualizado si hubo dudas.
