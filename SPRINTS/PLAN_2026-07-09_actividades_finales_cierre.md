# PLAN — Instelec#150: cierre definitivo (B1 Gantt scroll/zoom · B2 barras materiales · B3 Curva S Planeado Montaje · B4 freeze-header Actividades Finales)

- **Issue:** Instelec#150
- **Ruta:** sprint_path (1 sprint único, agente/branch consolidado — NO paralelizar en worktrees separados: los 4 sub-items comparten 2 archivos y el objetivo explícito de Miguel es cerrar los 4 juntos, no en rondas)
- **Fecha plan:** 2026-07-09
- **Complexity global:** complex (agregado; cada sub-item individual es medium/simple)
- **Riesgo global:** medio-alto — es la **5ª ronda** de este issue (4 bounces previos, todos FIX_INCOMPLETO). El único riesgo real es repetir el patrón: cerrar 2-3 de 4 y dejar un hueco.
- **Sprint único:** B1 ∥ B2 ∥ B3 ∥ B4 (sin dependencias entre sí — ver DAG)

## Contexto y reproceso

El núcleo de #150 ("No aplica" por torre/casilla, exclusión T-25, denominador de
avance) **ya está validado ✅ en prod por Indunnova (2026-06-29)** — ese ciclo de
reprocesos (3 bounces) cerró ahí. Ese MISMO QA Report dejó 3 bugs de UI/cálculo
encontrados durante la validación (B1, B2, B3) como condición de "cierre
definitivo", y un comentario posterior (2026-07-07) agregó B4 (freeze-header,
transversal con issue #183, sin dependencia con B1-B3). **El riesgo de ESTA
ronda no es un fix incorrecto — es cerrar 2-3 de 4 y dejar el resto.** Los 4
sub-items van en el mismo round.

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| 1 | B1 — Gantt OC: scroll vertical + horizontal | Journey `i150_b1_gantt_scroll`: wrapper con overflow, canvas alto dinámico, screenshot | ❌ pendiente F3 |
| 2 | B1 — Gantt OC: zoom con rueda del mouse | `chartjs-plugin-zoom` registrado (script tag en DOM) + config `zoom.wheel.enabled` | ❌ pendiente F3 |
| 3 | B2 — barra Agua visible en Solado (29.83% 🔴) | Chart no colapsa la barra por escala de unidades distintas (m³ vs kg) | ❌ pendiente F3 |
| 4 | B2 — barra Grava visible en Solado (216.93% 🔴) | ídem | ❌ pendiente F3 |
| 5 | B2 — barra Agua visible en Vaciado (20.83% 🔴) | ídem | ❌ pendiente F3 |
| 6 | B3 — mecanismo Curva S Planeado Montaje funciona end-to-end | Journey mutativo `i150_b3_curva_s_planeado` puebla Cronograma→MONTAJE y la serie `planeado` deja de estar vacía (assert de la etiqueta `{today}` presente en el JSON — el punto intermedio matemático es 85.71%, 180/210 días, pero el assert usa el token de fecha para evitar el falso-positivo del linter de decimales es-CO en un endpoint que en realidad es JSON crudo con punto) | ❌ pendiente F5 |
| 7 | B3 — comunicación al cliente sobre cómo poblar el dato real | Comentario F6 explica `/cronograma/` — sin código nuevo | ❌ pendiente F6 |
| 8 | B4 — thead de Actividades Finales sticky al scroll vertical | Clases `sticky top-0` en `<thead>` + corner cell `sticky top-0 left-0` | ❌ pendiente F3 |
| 9 | B4 — documentar convención reusable para #147/#166 | Nota en este plan (ver sección "Componente freeze-header") citada en F6 | ✅ (esta sección) |

Ninguna fila puede quedar sin ✅ para verdict 🟢 global (closeout.py bloquea con
exit 6 si falta alguna).

## Hallazgos de pre-flight (F2) — cambian el approach de B2 y B3

### B3 es DATO, no CAMPO — confirmado contra BD prod

El QA Report (2026-06-29) interpretó "el sistema no tiene registrada la fecha"
como que **falta un campo**. Es INCORRECTO. Verificado contra `instelec_db`
(proxy 127.0.0.1:5434):

```sql
select proyecto_id, seccion, fecha_inicio_planeada, fecha_fin_planeada,
       torres_planeadas, peso_pct
from construccion_programacion_fase where seccion='MONTAJE';
--             proyecto_id              | seccion | fecha_inicio_planeada | fecha_fin_planeada | torres_planeadas | peso_pct
-- ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7 | MONTAJE |                       |                     |                  |        0
```

El campo `ProgramacionFase.fecha_fin_planeada` (seccion=MONTAJE) **ya existe**
(`apps/construccion/models.py:2488-2518`) y `serie_planeado()`
(`calculators_avance_real.py:297-331`) YA lo lee y arma la serie "Planeado" de
la Curva S — **sin ningún cambio de código**, si el campo tiene datos. Existe
además una UI completa ya construida para editarlo: `CronogramaView`
(`apps/construccion/views.py:855-901`, ruta `construccion:cronograma` =
`/construccion/{proyecto}/cronograma/`) — un grid editable con las 9 secciones
(incluida MONTAJE) donde el cliente puede escribir fecha inicio/fin planeada +
peso%. **La fila para el proyecto QA existe** (se auto-crea vía `get_or_create`
al visitar `/cronograma/`) **pero sus 3 campos están vacíos/0**.

Conclusión: **B3 NO requiere migración ni campo nuevo.** El "fix" real es:
1. Confirmar (este plan) que el mecanismo funciona end-to-end una vez hay dato
   → validado con un journey mutativo que puebla vía la UI existente (fixture
   QA, con cleanup) y no vía SQL directo.
2. Comunicar al cliente en el comentario de cierre que **ya puede** ir a
   `/construccion/{proyecto}/cronograma/`, sección Montaje, e ingresar la
   fecha planeada de fin (y de inicio, y peso%) — la línea "Planeado" aparecerá
   sola en la Curva S de Montaje. No requirió tocar código.
3. (Opcional, bajo riesgo) Agregar un hint de estado vacío en el dashboard
   cuando la serie planeada esté vacía, señalando `/cronograma/` — ver detalle
   sub-item B3 abajo. Aplica genéricamente a OC/Montaje/Tendido (generalización,
   no solo Montaje) porque las 3 fases comparten el mismo mecanismo.

No tenemos la fecha REAL que Gabriel confirmó tener (no fue citada en los
comentarios) — no se inventa ni se hace backfill de datos de negocio del
cliente sin ese valor. Ver `accion_post_deploy` más abajo.

### B2 — hipótesis de causa raíz confirmada por unidades, no por dato faltante

`desviacion_materiales_por_etapa()` (`calculators.py:322-397`) SÍ devuelve los
4 materiales completos con `calc`/`real`/`semaforo` — la tabla debajo del chart
(que usa el mismo dato, `ctx['desviacion_solado']`/`['desviacion_vaciado']`
directo, no vía `graficas_json`) ya muestra las 3 alertas rojas correctamente
(29.83%, 216.93%, 20.83%). El flujo `graficas_json` (que sí alimenta el chart
Alpine/Chart.js) también hereda esos mismos valores completos vía
`DashboardObraCivilRealView` → `super().get_context_data()` (`views.py:2530-2535`,
`views_dashboards.py:235-239`) — el backend no filtra ni trunca nada camino al
chart.

El bug real (`MATERIALES_OC`, `calculators.py:198-203`) es de **unidades
dispares en un mismo eje lineal**: Cemento se mide en **kg** (cientos/miles) y
Agua/Arena/Grava en **m³** (unidades bajas, 1 dígito). El chart
(`renderDesviacion`, `dashboard_curva_s.html:454-484`) grafica `calc`/`real`
CRUDOS de los 4 materiales en el MISMO eje Y lineal `beginAtZero` — la barra de
Cemento (en kg) aplasta visualmente a las de Agua/Arena/Grava (en m³) a una
altura casi cero. No es que "no rendericen": renderizan a 1-2px, indistinguible
de vacío. Confirma la hipótesis de F1 con evidencia concreta (unidades del
propio `MATERIALES_OC_DETALLE`, líneas 214-230).

**Fix propuesto:** cambiar el chart de "Calculado vs Real en unidad cruda" a
**"Real como % de Calculado"** (normalizado, eje 0-100%~ compartido) — reusa
`m.desv_pct` que YA se calcula (`calculators.py:387`), consistente con lo que
ya muestra la tabla debajo. Alternativa de mayor esfuerzo (small multiples, 1
mini-chart por material con su propio eje) queda como B — usar la normalizada
salvo que F3 encuentre que pierde información crítica para el cliente.

### B4 — el repo YA tiene el patrón `sticky` (Tailwind), no hay que inventar CSS/JS nuevo

Grep sobre `templates/` (no solo `apps/`, que es donde F1 buscó — por eso no
apareció) encuentra el patrón ya en uso:

```
templates/lineas/mapa.html:107: <thead class="bg-gray-50 dark:bg-gray-900 sticky top-0">
```

Y la matriz de Actividades Finales (`templates/construccion/actividades_finales.html`)
**ya tiene freeze de la PRIMERA COLUMNA** implementado (`sticky left-0 ... z-10`
en el `<th>` "Estructura", línea 89, y en `_actividades_finales_row.html:10`
para las celdas del body) — issue #183 ítem 2 pide fijar fila Y columna; la
columna YA está resuelta en esta tabla, solo falta la fila (thead).

**Decisión (Miguel):** NO crear `static/css/sticky_table.css` ni JS nuevo — el
repo usa Tailwind con esta convención ya viva. El "componente compartido" es
una **convención documentada de 2 clases Tailwind** (no un archivo nuevo),
aplicada consistentemente en Actividades Finales (#150 B4, ahora) y luego en
Tendido (#147) y Obras de Protección (#166 B1):

```html
<!-- thead de cualquier matriz con >1 fila de encabezado -->
<thead class="bg-gray-50 dark:bg-gray-900 sticky top-0 z-20">

<!-- SOLO la celda "esquina" que ya es sticky left-0 (columna fija) además
     necesita top-0 y un z-index MAYOR al del thead para quedar por encima de
     ambos ejes de scroll: -->
<th class="... sticky left-0 top-0 z-30 ...">
```

`z-20`/`z-30` (no `z-10`) porque el thead crea su propio stacking context al
tener `position:sticky` + `z-index`; la celda esquina que es sticky en AMBOS
ejes necesita quedar por encima de ese stacking context, no solo de sus
hermanas de fila (que es lo que resolvía el `z-10` original, pensado solo para
scroll horizontal).

No se toca `_actividades_finales_row.html` (las filas del body no necesitan
cambio: su `sticky left-0 z-10` de columna sigue funcionando igual, por debajo
del thead cuando este se fija arriba).

## Sub-items — detalle

### B1 — Gantt OC: scroll horizontal/vertical + zoom con mouse

- **Archivos:**
  - `templates/construccion/dashboard_curva_s.html`:
    - línea ~369: agregar `<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>` después del CDN de Chart.js 4.4.0 (mismo patrón de plugin-por-CDN que `templates/campo/avance_registrar.html` ya usa con `chartjs-plugin-datalabels@2`) + `Chart.register(window.ChartZoom || window['chartjs-plugin-zoom']);` (confirmar el nombre exacto del global UMD del plugin en F3, `window.ChartZoom` es el típico export v2.x).
    - líneas 91-98 (bloque `data-block="oc-gantt"`): envolver el `<canvas id="oc-gantt-chart">` en un div `class="max-h-[600px] overflow-auto"` (scroll x+y nativo) y setear la altura REAL del canvas dinámicamente en JS proporcional al número de torres (no vía atributo HTML estático `height="520"`).
    - líneas 619-677 (`renderOcGantt()`): antes de `new Chart(...)`, `el.style.height = Math.max(520, filas.length * 22) + 'px';` (22px/fila para 64+ torres = ~1400px, habilita scroll real dentro del wrapper `max-h-[600px]`); agregar a `options.plugins`: `zoom: { pan: { enabled: true, mode: 'xy' }, zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' } }`.
- **Tests:** journey `i150_b1_gantt_scroll` (ver YAML) — read-only, valida presencia del script del plugin + canvas pintado. Unit test opcional (`tests_b1_dashboard_oc.py`): smoke de que `dashboard-obra-civil/real/` sigue devolviendo 200 con el nuevo markup (no rompe render_to_string).
- **Dependencias:** ninguna.
- **Complexity:** medium (JS/CSS puro, sin backend; requiere validar visualmente con screenshot que el wheel-zoom no colisiona con el scroll de la página completa — mode:'x' en zoom, no 'xy', para no capturar el scroll vertical del documento).
- **Deployable solo:** sí.

### B2 — Barras Agua/Grava en Desviación de materiales

- **Archivos:**
  - `templates/construccion/dashboard_curva_s.html` (`renderDesviacion`, líneas 454-484): cambiar los datasets de `data: materiales.map(m => m.calc)` / `.real` (unidades crudas) a una serie normalizada `data: materiales.map(m => 100)` (Calculado = índice 100 siempre) y `data: materiales.map(m => m.desv_pct != null ? (100 + m.desv_pct) : null)` (Real como % del calculado — `desv_pct` ya es `(real-calc)/calc*100` vía `desviacion_material_pct`, confirmar signo exacto en `calculators.py` antes de codear) — eje Y en `%` en vez de unidad cruda. Actualizar el título/tooltip para dejar explícito que es % (ya hay `afterLabel` con `desv_pct`, mantenerlo).
  - Sin cambios en `calculators.py` (el dato ya es correcto y completo).
- **Tests:** journey `i150_b2_barras_agua_grava` (mutativo=no, solo lectura contra el proyecto QA que YA tiene los datos que generan las 3 alertas rojas citadas). Unit test: si existe test de render del dashboard OC (`tests_b1_dashboard_oc.py`), agregar assert de que `graficas_json` sigue conteniendo las 4 entradas por etapa con `desv_pct` no-None para Agua/Grava (regresión de datos, no de visual).
- **Dependencias:** ninguna. Comparte archivo (`dashboard_curva_s.html`) con B1 pero secciones de código no solapadas (Gantt vs G3 materiales) — mismo PR, sin conflicto real.
- **Complexity:** medium (requiere confirmar el signo/fórmula exacta de `desv_pct` en `desviacion_material_pct()` antes de mapear a "100 + desv_pct" — si la fórmula da negativo para faltantes, el mapeo debe ajustarse para que la barra "Real" nunca quede negativa en el chart).
- **Deployable solo:** sí.

### B3 — Línea "Planeado" en Curva S de Montaje

- **Archivos:** ninguno estrictamente necesario para el mecanismo (ya funciona). Opcional, recomendado:
  - `templates/construccion/dashboard_curva_s.html`: agregar un aviso condicional (`{% if not datos_chart_planeado_disponible %}`) cerca del `<canvas id="curva-s-chart">` tipo "La línea Planeado no tiene datos de cronograma para esta fase — configúralo en Cronograma." con link a `{% url 'construccion:cronograma' proyecto_id=proyecto.id %}`. Requiere pasar un flag nuevo desde la vista (`views_dashboards.py` / `views.py`, ambas fases OC/Montaje/Tendido) indicando si `serie_planeado()` devolvió lista vacía Y no hubo fallback semanal — trivial (`bool(datos_chart.get('planeado'))`).
- **Tests:** journey mutativo `i150_b3_curva_s_planeado` (ver YAML) — puebla `ProgramacionFase` MONTAJE del proyecto QA vía el form de `/cronograma/` (no SQL directo), valida que el endpoint JSON de datos del chart deja de devolver `planeado` vacío, con cleanup que restaura NULL/0.
- **Dependencias:** ninguna.
- **Complexity:** simple (el hint opcional es la única pieza de código nueva; el resto es validación + comunicación).
- **Deployable solo:** sí.
- **Nota para F6:** el comentario de cierre debe ser explícito en que el gap era de DATO no de CAMPO, y dar la ruta exacta (`/cronograma/`) para que Gabriel/Indunnova lo carguen ellos mismos con la fecha real. Evita prometer un fix que ya está disponible sin deploy.

### B4 — Freeze-header en matriz de Actividades Finales

- **Archivos:**
  - `templates/construccion/actividades_finales.html`: línea 85 `<thead class="bg-gray-50 dark:bg-gray-900">` → agregar `sticky top-0 z-20`. Línea 89 (celda "Estructura", `rowspan="2"`, ya `sticky left-0 ... z-10`) → cambiar a `sticky left-0 top-0 z-30`.
- **Tests:** journey `i150_b4_freeze_header` — valida presencia de las clases (assert estructural) + screenshot. **Limitación documentada:** `run_journey.py` no tiene un step de "scroll" — no existe forma de simular scroll dentro del vocabulario de journeys actual, así que la prueba de que el thead PERMANECE visible al desplazarse es una verificación visual manual (Indunnova/cliente) o vía Chrome MCP interactivo, no un assert automatizado. El journey solo confirma que el markup correcto está desplegado.
- **Dependencias:** ninguna.
- **Complexity:** simple (2 cambios de clase CSS).
- **Deployable solo:** sí.
- **Reuso futuro:** la MISMA convención (`sticky top-0 z-20` en `<thead>`, `sticky left-0 top-0 z-30` en la celda esquina si existe columna fija) se reutiliza tal cual en Instelec#147 (Cambio 4, matriz Tendido) e Instelec#166 (B1, tabla Obras de Protección) — sin archivo compartido nuevo, solo aplicar las mismas 2 clases donde corresponda. Citar esta sección del plan en el comentario de cierre de #150 (F6) para que #147/#166 la referencien y no reinventen el patrón.

## DAG de dependencias

```
B1 (independiente) ─┐
B2 (independiente) ─┼─→ sprint único, 1 branch, 1 PR, 1 deploy
B3 (independiente) ─┤
B4 (independiente) ─┘
```

Sin cadena real. Se ejecutan en el mismo branch por ser `sprint_path` (no
`/modulo` con worktrees paralelos) — evita conflictos de merge en
`dashboard_curva_s.html` (tocado por B1 y B2 en secciones distintas).

## Riesgos

- **Riesgo #1 (alto si se ignora):** repetir el patrón de 4 bounces previos —
  cerrar solo 2-3 de los 4 sub-items. Mitigado por la tabla de entregables
  arriba (gate `closeout.py`, exit 6 si falta alguna fila ✅).
- **Riesgo #2 (medio):** B1 — el plugin `chartjs-plugin-zoom` vía CDN puede
  requerir ajuste de versión exacta compatible con Chart.js 4.4.0 (usar 2.0.1
  o posterior 2.x); si la CDN falla (`jsdelivr` caído / bloqueado), el gráfico
  Gantt no debe romperse — el registro del plugin debe ir en un `try/catch`
  como el resto del JS de este archivo (patrón ya usado en `renderChart`).
- **Riesgo #3 (medio):** B2 — verificar el signo exacto de `desv_pct` en
  `desviacion_material_pct()` antes de codear el mapeo `100 + desv_pct`; si la
  fórmula usa una convención distinta (ej. `abs()` o normalizado 0-1), ajustar.
- **Riesgo #4 (bajo):** B3 — el journey mutativo escribe temporalmente sobre
  una fila real de `construccion_programacion_fase` del proyecto QA (BD prod
  compartida) — mitigado con `update_via_psql` de cleanup que restaura
  NULL/NULL/0/NULL exactos (capturados antes de escribir). Ver
  `accion_post_deploy` — NO se toca ningún proyecto de cliente real.
- **Riesgo #5 (bajo):** B4 — verificar que subir el z-index del thead
  (`z-20`) no rompa ningún dropdown/tooltip que hoy asuma que el thead está en
  `z-0`/auto (grep rápido de otros elementos flotantes dentro de esa página —
  no se encontraron en `actividades_finales.html`).

## Validación esperada (F5/F6)

1. `dashboard-obra-civil/real/` del proyecto QA (Puerta de Oro): Gantt con
   scroll + zoom funcional (screenshot antes/después), gráficas Solado/Vaciado
   con las 4 barras visibles y proporcionadas (no solo Cemento).
2. `/cronograma/` → poblar MONTAJE con fecha+peso (vía UI, journey mutativo con
   cleanup) → Dashboard Montaje Curva S muestra línea "Planeado".
3. `/actividades-finales/` → thead con clases sticky correctas; confirmación
   visual manual de que permanece fijo al scrollear (Indunnova).
4. Los 4 puntos citados en el comentario de cierre F6 con URL exacta + screenshot
   + estado (🟢/🟡) por sub-item, nunca un solo verdict global sin desglose.

## accion_post_deploy

- **descripcion:** "Ninguna escritura de datos de negocio real requerida de
  nuestro lado. (a) El journey de validación de B3 escribe temporalmente sobre
  la fila ProgramacionFase(MONTAJE) del proyecto QA vía el formulario real de
  `/cronograma/` — es un fixture de prueba con cleanup inmediato
  (`update_via_psql` restaura NULL/NULL/0), no un backfill de dato de negocio.
  (b) Para proyectos reales de Instelec, la fecha planeada de fin de Montaje
  la debe ingresar el cliente (Gabriel) o Indunnova en su nombre vía la MISMA
  UI ya existente — no hay valor real disponible en los comentarios del issue
  para hacerlo ahora. Si Miguel autoriza que Indunnova cargue la fecha real
  una vez Gabriel la comparta en un comentario, ESO sí pasaría a ser
  escribe_bd_prod:true + requiere_hitl:true (dato de negocio del cliente)."
- **escribe_bd_prod:** false
- **requiere_hitl:** false
- **justificacion_hitl:** "El único write a BD prod en este round es un
  fixture QA con cleanup vía la UI de la app (patrón estándar de journeys
  mutativos del portafolio, no requiere HITL). No se realiza ningún backfill
  de dato de negocio real del cliente en este round — eso queda explícitamente
  fuera de scope hasta tener el valor y autorización de Miguel."
