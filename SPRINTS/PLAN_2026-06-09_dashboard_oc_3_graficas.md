# PLAN — Dashboard Obra Civil: 3 gráficas de seguimiento gerencial (issue #141)

**Fecha:** 2026-06-09
**Issue:** [Indunnova16/instelec#141](https://github.com/Indunnova16/instelec/issues/141)
**Estado:** Planning completado, listo para ejecución
**Scope de ESTE issue:** las 3 gráficas dentro del Dashboard de Obra Civil
existente (`DashboardObraCivilView` → `dashboard_curva_s.html`).
**Fuera de scope:** `DashboardTendidoView` / dashboard de Tendido = issue #139
(diferido). Este plan es base de ambos, pero #141 NO crea el dashboard de
Tendido.

## Contexto

El cliente pidió 3 visualizaciones gerenciales. La estructura EXACTA de cada
una quedó fijada contra los archivos de referencia del cliente
(`Documentacion/Dahboard obra civil.xlsx`, hoja `OOCC` con sus 2 LineCharts +
`CANT OOCC` con la matriz fuente; y `Documentacion/dashboard_propuesto.html` /
`PROPUESTA_DASHBOARD.md`, el mockup Chart.js del propio cliente). NO se inventó
nada: todas las decisiones de tipo de gráfica / agregado / eje provienen de esos
archivos.

| # | Gráfica | Tipo (de la referencia) | Eje X | Eje Y | Series | Fuente de datos |
|---|---------|-------------------------|-------|-------|--------|-----------------|
| G1 | Curva S Planeado vs Ejecutado | **LÍNEA** (xlsx OOCC LineChart + mockup `type:'line'`) | Semanas/fechas | % avance **ACUMULADO** | 2: Planeado (D/E acum) + Ejecutado (N/O acum) | `DashboardAvanceSemanal` (ya existe) |
| G2 | Avance por etapa OC | **BARRAS** (mockup `type:'bar'` agrupado) | Las 5 etapas | % torres completas por etapa | 1 serie de % (o Planeado/Ejecutado si hay meta) | `PataObra.*_ok` agregado por torre |
| G3 | Desviación materiales (vaciado) | **BARRAS / indicador con semáforo** (issue: "sin necesidad de gráfica compleja… alerta roja si supera un umbral") | 4 materiales | desviación % (real vs calc) | calc vs real por material | `VaciadoDetalle.{agua,arena,grava}_{calc,util}_m3` + `cemento_{calc,util}_bultos` |

### Hallazgos de grounding (código real ya inspeccionado)

- **G1 ya existe parcialmente.** `dashboard_curva_s.html` tiene `<canvas id="curva-s-chart">`,
  el endpoint `DashboardChartDataView` (`name='dashboard_chart_data'`) y filtro
  `?fase=`. La Curva S OC ya grafica Planeado (`pct_programado`) vs Ejecutado
  (`pct_construido`) acumulado. **#141 sobre G1 = agregar la serie/curva
  CONSOLIDADA** (todo el proyecto, no solo OOCC) que el issue pide explícitamente
  ("una consolidada con todo el proyecto").
- **G2 tiene la lógica de negocio lista.** `ProyectoConstruccion.porcentaje_avance_civil_ponderado`
  (models.py L138) ya recorre torres × patas contando `bloques_estado[bloque]`
  por etapa. Falta exponer el **desglose por etapa** (no solo el ponderado total)
  y el conteo torres_completas/torres_totales que pide el ejemplo del issue
  ("68 torres con excavación, 66 completadas → ~97%").
- **G3 tiene los campos exactos.** `VaciadoDetalle` (models.py L2502) ya guarda
  `agua_calc_m3/agua_util_m3`, `arena_calc_m3/arena_util_m3`,
  `grava_calc_m3/grava_util_m3`, `cemento_calc_bultos/cemento_util_bultos`.
  Falta una property `desviacion_pct` y un agregador por proyecto/torre.
- **Pesos de etapa configurables ya existen** (`peso_excavacion_pct`, …): se
  reusan para la versión ponderada de G2.
- **Patrón APIView/JSON ya establecido** en `views_b3_dashboard_indicadores.py`
  (clase `IndicadoresAggregator`, view `DashboardIndicadoresGeneralesView` que
  responde JSON cuando `?format=json`). Se replica el mismo patrón.

## Sub-items por sprint

> No se parte en "MVP + mejoras". Sprint único A = la versión 1.0 completa que
> el cliente valida al cierre. El orden es un DAG por dependencias de datos, no
> una partición de scope.

### Sprint A (deployable_solo del bundle completo: true)

| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|----------|----------|-------|--------------|--------|
| A1 | **Backend agregadores etapas + materiales.** `desviacion_pct` property en `VaciadoDetalle`; función `avance_por_etapa_oc(proyecto)` → `{Excavacion:{completas,totales,pct}, …}`; función `desviacion_materiales_vaciado(proyecto, umbral=10)` → por material `{calc, real, desv_pct, semaforo}` (sum patas agrupadas por torre). Curva S consolidada: `curva_s_consolidada(proyecto)` = unión OC+Montaje+Tendido por semana. | `apps/construccion/calculators.py`, `apps/construccion/models.py` (property `desviacion_pct` en VaciadoDetalle) | unit: pct etapa, desv material, semáforo umbral | — | ⏳ pendiente |
| A2 | **Endpoint JSON datos-graficas.** `DashboardGraficasDataView` GET → `{curva_s:{labels,planeado,ejecutado,consolidada}, avance_etapas:[{etapa,pct,completas,totales}], desviacion_materiales:[{material,calc,real,desv_pct,semaforo}]}`. Ruta `<uuid>/dashboard-obra-civil/datos-graficas/`. Filtro `?umbral=`. | `apps/construccion/urls.py` (ruta nueva), `apps/construccion/views.py` (view nueva, reusa `_DashboardCurvaSBase`/aggregator pattern) | unit: 200 + shape JSON; edge proyecto sin torres → arreglos vacíos; edge torre sin vaciado → material omitido/0 | A1 | ⏳ pendiente |
| A3 | **G2 Avance por etapa (barras Chart.js).** `<canvas id="avance-etapas-chart">` + init Chart.js `type:'bar'`, labels = 5 etapas, datos del endpoint A2. Colores por etapa, tooltip muestra completas/totales. | `templates/construccion/dashboard_curva_s.html` (sección nueva + JS init dentro del `x-data`), opcional `static/js/dashboard_oc_charts.js` | E2E render canvas | A2 | ⏳ pendiente |
| A4 | **G3 Desviación materiales (barras + semáforo).** `<canvas id="desviacion-materiales-chart">` calc vs real por material + fila/badge de alerta roja (`[data-semaforo='rojo']`) si `|desv_pct|>umbral`. Texto explicativo del caso "+1 bulto cemento 42.5 kg justificado". | `templates/construccion/dashboard_curva_s.html` (sección nueva + JS init) | E2E render canvas + assert semáforo | A2 | ⏳ pendiente |
| A5 | **G1 serie consolidada + flag `data-charts-ready`.** Agregar dataset consolidado a la Curva S existente; selector de fase OC/Montaje/Tendido/Consolidada; setear `[data-charts-ready='true']` cuando los 3 charts instancian (para el probe E2E). | `templates/construccion/dashboard_curva_s.html`, `apps/construccion/views.py` (DashboardChartDataView amplía `fase=CONSOLIDADA`) | E2E: 3 canvas presentes + ready flag | A2, A3, A4 | ⏳ pendiente |
| A6 | **Tests + smoke E2E + comentario cliente.** 3 test cases unit (`test_grafica_etapas`, `test_grafica_desviacion`, `test_curva_consolidada`) cubriendo happy + edge (proyecto sin torres, torre sin vaciado, desviación dentro de umbral = verde). Journey `instelec_141.yaml` (ya escrito por F2). Comentario con URL + pasos numerados de validación. | `apps/construccion/tests_b3_dashboard.py`, journey YAML (run dir) | los 3 unit + 2 journeys verdes | A3, A4, A5 | ⏳ pendiente |

## DAG dependencias

```
A1 (agregadores)
 └─> A2 (endpoint JSON)
       ├─> A3 (G2 barras etapas)
       ├─> A4 (G3 desviación materiales)
       └─> A5 (G1 consolidada + ready flag)   [requiere A3,A4 para el flag global]
              └─> A6 (tests + E2E + comentario)
```

Ruta de ejecución sugerida: A1 → A2 → (A3 ∥ A4) → A5 → A6.
Primer sub-conjunto deployable real = el bundle A1..A6 (las gráficas no aportan
valor a medias; se entrega la v1.0 completa).

## Riesgos y mitigaciones

- **R1 — Inventar tipo/agregación de gráfica.** Mitigado: estructura fijada
  contra el xlsx del cliente (G1 línea acumulada, G2 barras por etapa, G3
  calc-vs-real con semáforo) y el mockup `dashboard_propuesto.html`. No improvisar.
- **R2 — Número localizado es-CO rompe JS inline** (memoria recurrente del
  portafolio). Los % y desviaciones van al `<canvas>` vía JSON del endpoint
  (no interpolados con `{{ float }}` en `<script>`). Si algún valor entra al
  template, usar `json_script` / `|stringformat:"g"`. **No** meter floats crudos
  en `x-data`.
- **R3 — Etapa "Acero": el modelo usa `acero_refuerzo_ok`** (no `acero_ok`).
  A1 debe mapear el label "Acero" al campo real `acero_refuerzo_ok` y
  "Compactación" a `relleno_compactacion_ok`. Verificar nombres exactos en
  `PataObra.bloques_estado` antes de codear.
- **R4 — Proyecto sin vaciado** → G3 vacío. El agregador devuelve material con
  `calc=real=0` o lo omite; el template muestra "sin datos de vaciado", no rompe.
- **R5 — Canvas no renderiza pero el HTML pasa** (Chart.js falla silencioso).
  Mitigado con `[data-charts-ready='true']` seteado solo tras instanciar los 3
  charts; el journey E2E lo assertea (no basta `assert_selector` del canvas).
- **R6 — Deploy NO promueve tráfico** (gotcha del portafolio). Tras `gh run watch`,
  verificar `--to-latest`. La vía `/multiagente` ya lo promueve automático.

## Validación esperada (qa_claude smoke + journey)

Journey `RUN_*/journeys/instelec_141.yaml` (2 journeys, ya escrito):

1. `i141_dashboard_oc_tres_graficas` — abre
   `/construccion/ec2a68aa-…/dashboard-obra-civil/`, assert 200, verifica los 3
   `<canvas>` (`#curva-s-chart`, `#avance-etapas-chart`,
   `#desviacion-materiales-chart`), las 5 etapas y los 4 materiales como labels,
   y `[data-charts-ready='true']`. 2 screenshots.
2. `i141_endpoint_datos_graficas_json` — golpea
   `…/dashboard-obra-civil/datos-graficas/`, assert 200 + JSON con
   `avance_etapas` y `desviacion_materiales`.

Smoke maestros adicional: lista de proyectos + dashboard OC + 1 detalle de torre
(HTTP 200). Proyecto legacy probado: `ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`
(el mismo de #136/#132, tiene torres con patas + vaciado real).

Validación cliente (para el comentario):
1. Abrir el proyecto → Dashboard Obra Civil.
2. G1: ver Curva S con Planeado vs Ejecutado + selector Consolidada.
3. G2: ver barras de % por etapa (Excavación/Solado/Acero/Vaciado/Compactación).
4. G3: ver desviación calc vs real de agua/cemento/arena/grava; confirmar que
   una desviación > umbral sale en rojo (caso "+1 bulto cemento justificado").
