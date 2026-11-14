# RotaClima — Evaluación de Jurado Experto, Guion de Defensa (3 min) y Q&A Técnico

> [!NOTE]
> Documento construido **100% con código, contratos y salidas reales verificadas en disco** sobre el punto demo de Santa Cruz (`-17.30°, -62.25°`, elevación `280.15 m`) usando [power_demo.json](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/tests/fixtures/power_demo.json) (`12,784` días, `1991-01-01` a `2025-12-31`) y [01_validacion_motor.ipynb](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/notebooks/01_validacion_motor.ipynb).
> Las cifras de alternativas (`Adaptada` / `Regenerativa`) no se guionan ni se inventan aquí porque su módulo (`T4.1`–`T4.5`) está actualmente en ejecución por Teamwork; en el guion se dejan marcadas para leerse directamente de la salida real de `/analyze`.

---

## Parte I — Evaluación de Jurado Experto (Rúbrica NASA Space Apps)

### 1. Diagnóstico por criterio de evaluación

| Criterio NASA Space Apps | Veredicto técnico observado | Puntos fuertes reales del proyecto | Riesgo / brecha honesta a vigilar |
|---|---|---|---|
| **Validity (Rigor científico y trazabilidad)** | **Muy Alto (diferenciador principal)** | Motor biofísico determinista basado en **FAO-56** (Penman-Monteith + Hargreaves fallback, curva $K_c$ de 4 etapas, agotamiento $p$ dinámico), **USDA TR-55** (escorrentía SCS-CN), **FAO ECOCROP** y contraste **Mann-Whitney U** bilateral ($\alpha = 0.10$). Cero cajas negras de ML o alucinaciones de LLM: cada cifra sale de fórmulas en `backend/app/engine/` con `135` tests en verde. | [crops.json](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/data/crops.json) conserva `verificar: true` en todos los parámetros semilla hasta completar el cotejo humano (`T0.5`). |
| **Use of NASA Data (Uso sustantivo de datos NASA)** | **Muy Alto** | Ingesta directa de **10 variables diarias** de NASA POWER (`PRECTOTCORR`, `T2M`, `T2M_MAX`, `T2M_MIN`, `RH2M`, `ALLSKY_SFC_SW_DWN`, `WS2M`, `GWETTOP`, `GWETROOT`, `PS`) en [power.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/nasa/power.py). En el punto demo (`12,784/12,784` días sin `NaN`), Penman-Monteith corre en el **100%** de los días (`et0_hargreaves_share = 0.0`). Validación de cordura física contra `gwetroot` (MERRA-2): Pearson $r = 0.5501$ ($p = 0.00$). | Resolución nativa POWER $\approx 0.5^\circ \times 0.625^\circ$ ($\approx 50\text{ km}$): captura clima regional, no microclima de lote ni eventos convectivos puntuales. |
| **Impact & Relevance ("Field Shift")** | **Alto** | Demuestra cuantitativamente por qué la rotación diseñada hace 20 años quedó descalzada en Santa Cruz: la estación lluviosa se acortó **`64.1` días** ($p = 0.0055$), el inicio de lluvias se retrasó **`+27.6` días** ($p = 0.0016$) y las lluvias Q2 cayeron **`-178.3` mm** ($p = 0.0006$). Muestra sin maquillar incluso las métricas **no significativas** (`rain_q1`, `rain_q3`, `rain_q4`, `et0_total`). | El demo principal cubre un punto; la comparación regional requiere consultar el endpoint `/analyze` por coordenada (o usar caché de demo si falla la red). |
| **Creativity & UX de decisión** | **Alto (en diseño normativo)** | Traduce variables satelitales técnicas en riesgo comprensible para un productor: *"campaña mala en X de 20"* ($I_y < 0.60$), desglose de salud de suelo en 4 ejes (`0–100`) y contrato de fichas explicables con **invariante testeado**: todo número en el texto debe existir en `evidence[].value` trazado a su parámetro POWER. | F4 (`alternatives.py`, `cards.py`, `pipeline.py`) y F5 (`frontend/`) aún deben cerrarse e integrarse para exhibir la UX completa en vivo. |

---

### 2. Vulnerabilidades reales (para no ser sorprendidos por el jurado)

> [!WARNING]
> Un jurado técnico (agrónomo, hidrólogo o científico de datos) detecta en 30 segundos si el equipo oculta limitaciones. RotaClima ya las declara formalmente en `PLAN.md` §4.10 (`S1`–`S12`) y en `Meta.assumptions`. Úsalas a favor como señal de madurez científica:

1. **Parámetros de cultivo pendientes de cotejo (`T0.5`):** Todos los cultivos de [crops.json](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/data/crops.json) tienen `verificar: true`. *Respuesta correcta:* antes de presentar, ejecutar manualmente el cotejo de los 5 cultivos principales (`soya`, `maiz`, `sorgo`, `trigo`, `girasol`) contra FAO-56 (Tablas 11/12/22/24) y ECOCROP y documentar los supuestos `S6`–`S9` (helada escalón, calor fuera de Teixeira 2013, coberturas).
2. **Solo 1 de 20 campañas por debajo de `I < 0.60` en el demo (`2016/17`):** Aunque el modelo pasa el criterio (`1 <= bad_seasons <= 15`), `2023/24` (`I = 0.6796`, peor sequía invernal reportada por ANAPO) y `2015/16` (`I = 0.6814`) quedan justo arriba del umbral `0.60`. *Por qué ocurre:* en nuestra rotación base `soya@11-16 + soya@05-01`, la soya de verano tuvo alto rendimiento en varios años y compensó parcialmente al invierno en el índice medio anual $I_y$, **y** POWER `0.5°` suaviza picos extremos locales (`S1`). Es honesto señalar que en el ranking relativo esas **3 peores campañas del modelo (`2016/17`, `2023/24`, `2015/16`) coinciden exactamente** con las 3 grandes emergencias agrícolas registradas en Santa Cruz.
3. **El puntaje de suelo no retroalimenta el rendimiento (`S4`):** En [soil.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/soil.py) el suelo mide nitrógeno, diversidad, materia orgánica y erosión (`47.90/100` en monocultivo de soya), pero no altera el balance hídrico de [slot.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/slot.py). Se decidió así para mantener un modelo explicable de un balde sin acoplar parámetros empíricos no calibrados localmente.
4. **Reanálisis vs observaciones de estación (`S1`, `S12`):** POWER combina MERRA-2 (`0.5°×0.625°`) y CERES (`1°`); las tendencias pueden arrastrar inhomogeneidades observacionales y subestimar picos diarios locales de `Tmax`. Por eso cada tendencia reporta el `p-valor` bilateral de Mann-Whitney U y etiqueta explícitamente `"no significativo"` cuando $p \ge 0.10$.

---

## Parte II — Guion de Defensa Cronometrado (3 Minutos — `PLAN.md` §7)

**Escenario demo verificado:** Lote agrícola en la zona de expansión este de Santa Cruz (Cuatro Cañadas / Pailón, `-17.30°, -62.25°`, `280.15 m`), suelo `franco` (`AWC = 155 mm/m`, `CN = 78`), rotación actual: **Soya verano (`11-16`) + Soya invierno (`05-01`)**.

### `0:00 – 0:25` · Portada — El problema ("Field Shift")
* **En pantalla:** Portada / Vista inicial de RotaClima cargada sobre Santa Cruz.
* **Qué decir:**
  > *"Un agricultor en Santa Cruz sigue sembrando hoy con el calendario que funcionaba hace 20 años: soya de verano en noviembre y soya de invierno en mayo. El problema es que el campo ya no está bajo el mismo clima. **RotaClima** usa 35 años de datos diarios reales de **NASA POWER** — sin cajas negras ni IA inventando números — para mostrar cómo se desplazó su clima y qué rotación alterna resiste mejor los próximos años."*

### `0:25 – 0:50` · Vista `(a)` Mapa y Formulario
* **En pantalla:** Clic en el lote (`-17.30°, -62.25°`) / botón `"Cargar demo Santa Cruz"`, textura `franco`, rotación `soya@11-16` + `soya@05-01` en 3 selecciones, clic en Analizar.
* **Qué decir:**
  > *"Sin registro ni sensores en parcela: el productor marca su lote en el mapa, elige su textura de suelo y carga su rotación actual en 3 clics. En este lote del este cruceño, cargamos la doble soya tradicional sobre suelo franco y consultamos **12.784 días continuos de NASA POWER** entre 1991 y 2025."*

### `0:50 – 1:25` · Vista `(b)` "Tu clima cambió" (Cifras reales verificadas)
* **En pantalla:** Tarjetas `before` (`1991/92–2005/06`) vs `recent` (`2010/11–2024/25`) con prueba Mann-Whitney U y series por campaña.
* **Qué decir:**
  > *"En vez de hablar de promedios vagos, agrupamos por **campaña agrícola** del hemisferio sur, de julio a junio, y comparamos las primeras 15 campañas contra las últimas 15:*
  > *- La lluvia total cayó **`195.9` mm** por campaña (de `1342.2` a `1146.3` mm, $p = 0.0114$), concentrado en el trimestre crítico de siembra de verano Q2 (`-178.3` mm, $p = 0.0006$).*
  > *- La estación lluviosa se encogió **`64.1` días** ($p = 0.0055$): las lluvias arrancan **`27.6` días más tarde** y terminan **`38.1` días antes**.*
  > *- Y los días con calor extremo por encima de 35 °C subieron de **`52.7` a `80.5` días por campaña** (`+27.7` días, $p = 0.0084$).*
  > *Pero fíjense en la tarjeta de **ET0 total** (`+65.0` mm, $p = 0.1057$) o **lluvia Q1** ($p = 0.9669$): aparecen marcadas como **no significativo**. RotaClima no exagera ni vende ruido como tendencia."*

### `1:25 – 2:20` · Vista `(c)` Comparación, Tira de Campañas y Ficha con Evidencia
* **En pantalla:** Tabla comparativa (`Actual` vs `Adaptada` vs `Regenerativa`), tira de 20 campañas de la actual (`2005/06–2024/25`) y apertura de una `RotationCard` con chips de evidencia NASA.
* **Qué decir:**
  > *"¿Qué le pasa a la doble soya actual bajo estas condiciones? En nuestras 20 campañas de evaluación (`2005/06–2024/25`), el índice medio queda en **`0.7644`**, pero la soya de invierno rinde mucho menos (`0.6584`) que la de verano (`0.8704`) porque sobrevive con humedad residual en estación seca.*
  > *Cuando miramos el ranking de riesgo histórico en la tira de campañas, las 3 peores campañas simuladas son exactamente las 3 grandes crisis documentadas en Santa Cruz: **`2016/17`** (`I = 0.5541`, marcada en rojo por **calor**), **`2023/24`** (`I = 0.6796`, limitante **agua**) y **`2015/16`** (`I = 0.6814`, **agua**). Además, en suelo saca apenas **`47.90 / 100`** (castigada con `15/100` en diversidad por repetir leguminosa).*
  > *Aquí al lado vemos las alternativas seleccionadas determinísticamente por el motor — **`Adaptada`** (cambio mínimo en fechas o a lo sumo 1 cultivo) y **`Regenerativa`** (mejora de suelo con pérdida acotada) — **[leer aquí las cifras exactas de `mean_productivity`, `bad_seasons` y `soil.total` devueltas por `/analyze` al cerrar F4]**. Al abrir cada ficha, cada afirmación tiene un chip verificable con el dataset NASA, los parámetros exactos (`PRECTOTCORR`, `T2M_MAX`...) y el periodo evaluado."*

### `2:20 – 2:40` · Calendario Agrícola Quincenal (`24` quincenas)
* **En pantalla:** `CalendarChart` con lluvia/ET0 (`before` tenue vs `recent`) y ventanas de floración resaltadas.
* **Qué decir:**
  > *"En el calendario de 24 quincenas vemos físicamente el descalce: la curva de lluvias recientes se corre casi un mes hacia adelante, exponiendo la floración de los esquemas tradicionales a golpes de calor o déficit hídrico, y mostrando cómo el ajuste de fechas en las rotaciones sugeridas vuelve a alinear la ventana sensible con la recarga hídrica."*

### `2:40 – 3:00` · Cierre — Determinismo, Validación y Próximo Paso
* **En pantalla:** Cierre con arquitectura / fuentes NASA / límites.
* **Qué decir:**
  > *"Todo en RotaClima es **100% determinista y auditable**: balance hídrico diario FAO-56 + SCS-CN, estrés térmico ECOCROP y 180 días de spin-up previo a cada siembra. Contrastado contra humedad radicular MERRA-2 (`gwetroot` de NASA POWER), nuestro balde alcanza una correlación de **`r = 0.5501`** ($N = 9.180$ días activos, $p < 10^{-4}$). Decimos nuestros límites en voz alta — resolución regional de 50 km y rendimiento relativo sin precios — y nuestro siguiente paso natural es la validación offline contra series de **NDVI MODIS (`MOD13Q1`)**."*

### Mapeo Requisito del Challenge → Motor y UI (`PLAN.md` §7)

| Requisito del challenge | Cómo responde RotaClima (verificado) | Módulo / Pantalla |
|---|---|---|
| `>= 3` estrategias incluida la actual | Orden fijo `actual`, `adaptada`, `regenerativa` (`+ diversificada` opcional) | [rotation.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/rotation.py) · [alternatives.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/alternatives.py) (F4) · Vista `Compare` (F5) |
| Por qué se sugiere | `RotationCard.why` por plantillas deterministas | `cards.py` (F4) · `RotationCard` (F5) |
| Riesgos | `RotationCard.risks` + tira de 20 campañas con factor limitante | `cards.py` (F4) · `Compare.tsx` (F5) |
| Beneficios | `RotationCard.benefits` + deltas de suelo y productividad | `cards.py` (F4) · `CompareTable.tsx` (F5) |
| Datos NASA específicos que respaldan | `Evidence.source` (`dataset`, `parameters` exactos de POWER, `period`) | [power.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/nasa/power.py) · [schemas.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/schemas.py) |
| Satélite + realidad local del productor | Perfil NASA (`before/recent`) + lat/lon, textura y rotación del usuario | [climate.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/climate.py) · `MapForm.tsx` (F5) |
| Qué sembrar a continuación | Primer slot de la rotación recomendada + `sow_date` y `prev_mode` | `SlotOut` en [schemas.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/schemas.py) |

---

## Parte III — Banco de Q&A Técnico y Agronómico (12 Preguntas Difíciles)

### 1. *"¿Por qué no usaron Machine Learning o un LLM para recomendar rotaciones y redactar explicaciones?"*
* **Respuesta técnica:** Porque un agricultor no puede tomar decisiones de capital sobre una caja negra que alucina cifras o sobreajustar un modelo a 34 observaciones históricas por punto. En RotaClima **todo es determinista y reproducible byte a byte**: cada fórmula biofísica está fijada en código ([PLAN.md](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/PLAN.md) §4), cada constante numérica está centralizada en [config.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/config.py) y cada frase de la ficha se genera desde plantillas con un invariante testeado: toda cifra en `text` existe literalmente en `evidence[].value` trazada a los parámetros POWER que la produjeron.

### 2. *"Si usan datos de NASA POWER a ~50 km (`0.5° × 0.625°`), ¿cómo aseguran que sirve para un lote específico?"*
* **Respuesta técnica:** No fingimos que sirve como sensor de parcela: lo declaramos explícitamente en `Meta.resolution_note` (*"POWER ≈ 0.5°×0.625° (≈50 km): clima regional, no de parcela"*). Lo que **sí** captura bien esa grilla es el **régimen agroclimático regional y su desplazamiento interanual**, combinado con datos locales reales que provee el productor: **textura de suelo** (`AWC` 80/155/160 mm/m y `CN` 67/78/85) y **rotación/calendario exacto**. Por eso todos los resultados se expresan en **rendimiento relativo ($Y_{\text{rel}} \in [0, 1]$)** y en comparación justa sobre las mismas 20 campañas, no en toneladas absolutas por hectárea.

### 3. *"¿Por qué usan un balance hídrico de un solo balde (`TAW`) en vez de un modelo multicapa tipo DSSAT/APSIM?"*
* **Respuesta técnica:** Por parsimonia paramétrica y auditabilidad (`S11`). DSSAT/APSIM exigen decenas de parámetros de suelo por horizonte (retención van Genuchten, conductividad hidráulica saturada, densidad aparente por capa) y calibración varietal que no existen en campo abierto para pequeños y medianos productores. El balde único FAO-56 con escorrentía SCS-CN diaria ([slot.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/slot.py)) necesita solo `AWC`, `CN` y `zr_max_m`, respeta **cierre exacto de masa** ($D_{r,t} = D_{r,t-1} - P_{e,t} + ET_{a,t} + DP_t$ verificado a $\pm 10^{-6}\text{ mm}$ en `test_wb.py`), y mostró una correlación de **`r = 0.5501`** ($N = 9.180$ días) contra `gwetroot` de MERRA-2 sin ningún parámetro ajustado al sitio.

### 4. *"¿Cómo manejan el estado hídrico inicial del suelo antes de sembrar cada cultivo?"*
* **Respuesta técnica:** Nunca arrancamos el balance el día de siembra con un número arbitrario. Implementamos un **spin-up de 180 días** (`SPINUP_DAYS = 180`) antes de cada fecha de siembra, partiendo de `DR0_FRAC = 0.5` ($50\%$ de agotamiento de `TAW`). Y distinguimos el manejo previo de forma cíclica ([rotation.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/rotation.py)): si el slot anterior terminó hace `<= 30` días (`GAP_CROP_MAX_DAYS`), los últimos `120` días del spin-up simulan consumo de cultivo previo con `KC_PRE_CROP = 0.90` (`mode="crop"`); si hubo barbecho largo (`> 30` días), todo el spin-up usa `KC_FALLOW = 0.20` (`mode="fallow"`). En el demo, eso hace que soya de invierno tras cosecha reciente arranque más seca que soya de verano tras barbecho.

### 5. *"¿Cuál fue un detalle sutil en la física de su balance hídrico que suelen errar otros modelos simples?"*
* **Respuesta técnica:** Cuatro decisiones normativas verificadas en [et0.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/et0.py) y [slot.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/slot.py):
  1. **Orden lluvia → estrés (`wb_step`):** la lluvia efectiva entra al suelo **antes** de evaluar el umbral `RAW` y el coeficiente `Ks` del día (no al revés).
  2. **Lluvia pequeña (`< 0.2 * ET0`):** se ignora como intercepción/evaporación directa superficial (`SMALL_RAIN_FRAC = 0.2`, FAO-56 cap. 8).
  3. **Factor hídrico por ratio de sumas (`f_agua`):** dividimos $\sum ET_a / \sum ET_c$ en todo el ciclo antes de aplicar FAO-56 ec. 90 ($1 - K_y(1 - \text{ratio})$), nunca promediando ratios diarios (que infla falsamente días de baja demanda).
  4. **ET0 con temperatura media `(tmax + tmin)/2`:** tal como exige FAO-56 ec. 6 (en vez de `t2m`), y en Hargreaves aplicamos el factor **`0.408`** para convertir $R_a$ de $\text{MJ/m}^2/\text{día}$ a $\text{mm/día}$.

### 6. *"¿Por qué en Santa Cruz la campaña `2023/24` dio índice `0.6796` (no alcanzó el corte `< 0.60` de campaña mala) si fue tan severa?"*
* **Respuesta técnica:** Precisamente porque la validación F3 exige transparencia: en la rotación base anual `soya@11-16 + soya@05-01`, $I_y$ promedia el rendimiento relativo de **los dos slots** de la campaña. En `2023/24`, el déficit hídrico castigó fuertemente un slot mientras el otro amortiguó el promedio anual hasta `0.6796`, dejándola como **#2 peor de 20 campañas** (solo detrás de `2016/17`, que sí rompió el umbral con **`0.5541`** por golpe de calor en floración). También influye el suavizado espacial de `0.5°` en POWER (`S1`). Además, reportamos tanto `bad_seasons` como `p10_index` (`0.6812`) y las fallas individuales por slot (`failures` con `Y_rel < 0.50`: `1/20` en verano y `2/20` en invierno) para que no se oculte el riesgo específico de cada cultivo.

### 7. *"¿Cómo evitan sesgos cuando un cultivo se siembra en diciembre (hemisferio sur) y se cosecha en abril del año siguiente?"*
* **Respuesta técnica:** En [calendar.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/calendar.py) **nunca agrupamos por año calendario**. Para latitud $< 0$, la campaña agrícola arranca el **`07-01`** y se verifica elegibilidad exigiendo `inicio(y) - 180 días >= DATA_START` y `inicio(y) + 365 + 183 días <= DATA_END`, dando `34` campañas continuas en Sur (`1991–2024`) y `33` en Norte (`1992–2024`). Así un ciclo estival de 135 días sembrado el `11-16` en campaña `2015` corre continuo hasta `2016-03-31` sin partirse en diciembre, y cada rotación compara exactamente la **misma lista ordenada de campañas**.

### 8. *"En rotaciones de 2 años (por ejemplo Soya–Maíz), ¿qué pasa si justo los años pares de POWER fueron más húmedos que los impares?"*
* **Respuesta técnica:** Eliminamos ese sesgo de fase en [rotation.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/rotation.py): para **cada campaña histórica $y$**, aplicamos el clima de esa campaña $y$ a **todas las fases $k = 1..L$** de la rotación y promediamos sobre $L$:
  $$P_y = \frac{1}{L} \sum_{k=1}^{L} \sum_{s \in \text{año } k, \text{ cosechable}} w_s \cdot Y_{\text{rel}}(s, y)$$
  Así se evalúa la rotación equilibrada a largo plazo independiente de en qué año arranque el productor, y los cultivos de cobertura (`cosechable=false`, como `avena_cob` o `crotalaria`) **no inflan `P` ni `Pot`**, aunque sí aportan al modo hídrico previo, a la validez temporal y al puntaje de suelo.

### 9. *"¿Cómo eligen fechas óptimas de siembra sin caer en sobreajuste ('overfitting' al pasado)?"*
* **Respuesta técnica:** Con dos mecanismos en [table.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/table.py) y `PLAN.md` §5:
  1. Para **elegir fechas de siembra** en alternativas, promediamos el rendimiento sobre una ventana **suavizada circular de 3 quincenas** (`(g-1, g, g+1) mod 24`), evitando elegir fechas pico aisladas que fallen ante una variación de 15 días en el clima real.
  2. Para **reportar métricas al usuario**, volvemos a evaluar cada candidata elegida con la tabla **sin suavizar**, de modo que las cifras visibles (`mean_productivity`, `bad_seasons`, `p10_index`) son reales sin dilución artificial.

### 10. *"¿Qué garantizan los test de Mann-Whitney U y qué pasa cuando falta humedad, radiación o viento en NASA POWER?"*
* **Respuesta técnica:**
  - En [climate.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/climate.py), comparamos `before` (primeras 15 campañas) vs `recent` (últimas 15) con **Mann-Whitney U bilateral** (no paramétrica, sin asumir normalidad en lluvia ni conteos), exigiendo al menos `5` observaciones válidas por periodo y marcando `significant = (p < 0.10)`. En el demo, `10` de `14` métricas dieron significativas y `4` aparecen honestamente como no significativas.
  - En [et0.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/et0.py), si en algún día faltara `rh`, `rs` o `ws` (`-999` convertido a `NaN` únicamente en [power.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/nasa/power.py)), ese día usa **Hargreaves (`"hg"`)** y registra la fracción en `Meta.et0_hargreaves_share`. Si faltaran `prec`, `tmax` o `tmin` dentro de la ventana simulada de una campaña, el motor **no rellena en silencio**: marca la campaña como `NaN` y falla explícitamente (`AGENTS.md` regla #12). En el punto demo, los 12,784 días tienen 0 faltantes (`et0_hargreaves_share = 0.0`).

### 11. *"¿Cómo calculan el puntaje de suelo y por qué dicen que la erosión usa datos NASA?"*
* **Respuesta técnica:** En [soil.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/engine/soil.py) ponderamos 4 subpuntajes iguales (`0.25` cada uno): `nitrogen` (balance por clase N, penaliza extractivas y premia leguminosas), `diversity` (familias botánicas con penalización de `-50%` si se repite la misma familia en pares adyacentes cíclicos, como soya sobre soya = `15/100`), `organic_matter` (aporte de rastrojo + bono por cultivo de cobertura) y **`erosion`**: esta última calcula la escorrentía diaria media $W[o]$ de las 20 campañas `eval` usando lluvia diaria `PRECTOTCORR` de NASA POWER y el `CN` de la textura del lote, y mide qué fracción de esa escorrentía potencial cae cuando el suelo está protegido por cobertura viva del cultivo o rastrojo en superficie (siembra directa, `S5`). En la rotación base da **`63.26`**, arrastrando el suelo total a **`47.90 / 100`**.

### 12. *"¿Qué pasa si NASA POWER está caída en plena demostración o si la respuesta tarda más de 30 segundos?"*
* **Respuesta técnica:** Hay dos capas de resiliencia contempladas en arquitectura ([power.py](file:///home/huaritex/Escritorio/Nasa_Space_Apps_2026/backend/app/nasa/power.py) y `PLAN.md` §3/§8):
  1. En backend: redondeo de coordenadas a 2 decimales, caché en disco por punto (`cache/power/`) y caché de respuestas completas por hash de request (`T4.4`), además de reintentos exponenciales (2s / 4s / 8s, timeout 60s) que ante fallo total levantan `PowerUnavailable` (HTTP 503).
  2. En frontend y offline: precaché estático (`T4.5` -> `frontend/public/demo_santa_cruz.json`) con fallback automático y banner visible `"Modo demo offline"` (`T5.6`). Y si el primer cómputo completo superara los 30s (`T6.1`), el plan contempla el prefiltro térmico `T6.2` (`f_temp` climatológico $\ge 0.5$) con test de regresión garantizando selecciones idénticas.
