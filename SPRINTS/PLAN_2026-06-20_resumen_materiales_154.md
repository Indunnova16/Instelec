# PLAN — Resumen de materiales totales del proyecto (issue #154)

**Fecha:** 2026-06-20
**Issue:** [Indunnova16/Instelec#154](https://github.com/Indunnova16/Instelec/issues/154)
**Estado:** Planning completado, listo para ejecución
**Complejidad global:** LOW · **Riesgo deploy:** bajo · **Migración:** NO

## Contexto
Módulo NUEVO de consolidación (sin modelo nuevo, sin migración): vista de solo
lectura que agrega los materiales de obra de TODAS las torres del proyecto y los
presenta con un total del proyecto + desglose por torre, en tabla + gráfico, con
entrada en el menú de construcción. El cliente confirmó el scope completo
(comentario @Indunnova 2026-06-20): todas las etapas con materiales, ambos
niveles (total + por torre), tabla + gráfico, columnas según la imagen adjunta.

## MATIZ DE COLUMNAS — RESUELTO (decisión explícita: opción b)

El wireframe (att_01.png) pide columnas **Torre · Agua (m³) · Arena (m³) ·
Grava (m³) · Cemento (kg) · Madera (un) · …**. Se inspeccionaron modelos + datos
reales (psql sobre `instelec_db`, proyecto QA Puerta de Oro
`ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`) y se concluyó:

1. **`PataObra` NO tiene materiales granulares.** Solo agregados en m³:
   `solado_m3`, `concreto_m3` / `concreto_solicitado_m3` / `concreto_instalado_m3`,
   `relleno_m3`, `excavacion_m3`, y `acero_kg`. No hay columnas de agua/arena/
   grava/cemento. **En el proyecto QA estos campos están TODOS NULL** (260 patas,
   0 con material cargado; tampoco hay datos en NINGÚN proyecto de la BD).
2. **NO existe ninguna tabla de dosificación / mezcla / proporción** en el repo
   (`grep -rniE "dosificacion|mezcla|proporcion|densidad"` → nada aplicable). Por
   tanto **es imposible derivar agua/arena/grava/cemento desde m³** sin inventar
   números → la opción (a) del matiz queda descartada.
3. **`TrinchoCuneta` es la ÚNICA fuente poblada y granular** de materiales, con
   columnas EXPLÍCITAS y datos reales en ≥2 torres (E33, E54, E55, E56, E60, E1…):
   - `cemento` — **bultos 50K** → normalizar a **kg = cemento × 50**
   - `arena` — **cuñetes** (NO m³)
   - `grava` — **cuñetes** (NO m³)
   - `alambre_galvanizado` — kg
   - `geotextil` — m
   - `tubo_metalico` — un
   - `malla_eslabonada` — un

### Mapeo final wireframe → dato real (se documenta tal cual en el comentario de cierre)

| Columna wireframe | Fuente real | Unidad mostrada | Nota |
|---|---|---|---|
| **Agua** | — (no existe) | — | **N/D** — ningún campo de agua en el modelo. Columna se OMITE (no se inventa). |
| **Arena** | `TrinchoCuneta.arena` | **cuñetes** | Se relabela a "Arena (cuñetes)" — el dato NO está en m³. |
| **Grava** | `TrinchoCuneta.grava` | **cuñetes** | Idem, "Grava (cuñetes)". |
| **Cemento (kg)** | `TrinchoCuneta.cemento` × 50 | **kg** | ✅ coincide con la unidad del wireframe (bultos 50K → kg). |
| **Madera** | — (no existe) | — | **N/D** — no hay captura de madera. Columna se OMITE. |
| Alambre galvanizado | `TrinchoCuneta.alambre_galvanizado` | kg | Material real adicional → se incluye. |
| Geotextil | `TrinchoCuneta.geotextil` | m | Real → se incluye. |
| Tubo metálico | `TrinchoCuneta.tubo_metalico` | un | Real → se incluye. |
| Malla eslabonada | `TrinchoCuneta.malla_eslabonada` | un | Real → se incluye. |
| Solado | `PataObra.solado_m3` (Σ por torre) | m³ | Agregado real (hoy vacío en QA, pero estructuralmente presente). |
| Concreto/Vaciado | `PataObra.concreto_instalado_m3` ∥ `concreto_m3` (Σ) | m³ | Agregado real. Usar `concreto_instalado_m3`, fallback `concreto_m3`. |
| Relleno/Compactación | `PataObra.relleno_m3` (Σ por torre) | m³ | Agregado real. |

**Regla de honestidad de datos (P-anti-invención):** la columna se muestra con
la unidad REAL del modelo (cuñetes, no m³). NO se fabrican litros de agua ni
unidades de madera. Las columnas sin respaldo (Agua, Madera) NO se renderizan;
en su lugar el template lleva una nota al pie explicando que esos materiales no
se capturan hoy en el sistema. El comentario de cierre al cliente incluye esta
tabla de mapeo para que Gabriel valide el criterio.

**Torre = `TorreConstruccion.numero_display`** (normaliza T-{n}/E{n}). Solo torres
`aplica=True`. Filas = torres con ≥1 material > 0 + fila **Total** (Σ de todas).

## Sub-items de la versión 1.0 (todos van; ninguno es "fase 2")

### Sprint A (deployable_solo: true — todo es un único bundle atómico)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | `ProyectoConstruccion.resumen_materiales()` — agrega por torre (TrinchoCuneta cemento×50→kg, arena, grava, alambre, geotextil, tubo, malla + PataObra Σ solado_m3/concreto_instalado_m3∥concreto_m3/relleno_m3) y devuelve `{"torres": [ {torre, ...materiales}... ordenadas por orden_numerico ], "total": {...}}`. Solo `aplica=True`. Sin agua/madera. | `apps/construccion/models.py` | unit: total = Σ filas; cemento_kg = bultos×50; 2 torres reales (E33,E54) → valores esperados; proyecto sin datos → estructura vacía sin crash | - | low | ⏳ |
| A2 | `ResumenMaterialesView` (LoginRequiredMixin+RoleRequiredMixin, TemplateView GET) + ruta `construccion:resumen_materiales` slug `resumen-materiales/`. Context: `proyecto`, `resumen` (dict de A1), `resumen_json` (json.dumps de series para Chart.js, crudo no es-CO). | `apps/construccion/views.py`, `apps/construccion/urls.py` | smoke: GET 200 autenticado contra proyecto QA | A1 | low | ⏳ |
| A3 | Template tabla: columnas dinámicas (las del mapeo, con sus unidades reales en el header), filas = torres, fila **Total** en negrita; nota al pie de Agua/Madera N/D; estado vacío amable si no hay materiales. `floatformat:"2g"` para decimales (es-CO). | `templates/construccion/resumen_materiales.html` | (cubierto por journey) | A2 | low | ⏳ |
| A4 | Gráfico Chart.js (barras agrupadas: categorías = torres, series = materiales con datos). Patrón repo: `Chart.defaults.animation=false`; datos vía `{{ resumen_json\|json_script:"resumen-materiales-data" }}` + `JSON.parse(el.textContent)` (NO JSON crudo en x-data); guard `if(window.Chart)`; canvas con id `#chart-materiales`. | `templates/construccion/resumen_materiales.html` | journey: `assert_canvas_painted` | A3 | medium | ⏳ |
| A5 | Entrada en sidebar de construcción: `<a :href="catUrl('resumen-materiales')" @click="catClick($event)">Resumen de Materiales</a>`, ubicada tras "Obras de Protección" (item 7) / antes de "Actividades Finales". Mismo patrón Alpine `catUrl`/`catClick` de los demás (link gateado por proyecto). | `templates/components/sidebar.html` | (cubierto por smoke visual) | A2 | trivial | ⏳ |

> El slug DEBE ser `resumen-materiales/` (la sidebar arma la URL con
> `catUrl('resumen-materiales')` → `/construccion/{proyecto_uuid}/resumen-materiales/`).
> Confirmado libre (no existe en urls/views/models).

## DAG dependencias
A1 → A2 → {A3, A5}; A3 → A4

## DoD (versión 1.0)
- [x] Migration: **N/A** (no hay modelo nuevo; solo lectura/agregación).
- [x] Backend: método de agregación + view + ruta + namespace.
- [x] UI completa: tabla (total + por torre) + gráfico + estado vacío + nota N/D + entrada de menú.
- [x] Tests: unit de `resumen_materiales()` (total=Σ, cemento×50, 2 torres reales, proyecto vacío) + journey E2E read-only.
- [x] Smoke E2E definido: goto a la ruta nueva del proyecto QA → tabla con ≥2 torres + fila Total + canvas pintado, sin pageerror.
- [x] Instrucciones de validación cliente: URL + tabla de mapeo de columnas en el comentario de cierre.

## Riesgos y mitigaciones
- **Datos del proyecto QA**: PataObra está vacío y TrinchoCuneta tiene datos solo
  en algunas torres (E33, E54, E55, E56, E60, E1). El journey DEBE assertar
  contra esas torres reales (E33/E54), NO contra PataObra. La fila Total debe
  reflejar la Σ de cemento_kg de esas torres.
- **Unidades**: cemento `bultos 50K`→kg (×50); arena/grava son **cuñetes** (NO
  m³ como dice el wireframe) → header honesto. Documentado en el comentario.
- **es-CO**: decimales con `floatformat:"2g"`; Chart.js con datos vía
  `json_script` crudo (memoria portafolio: JSON crudo en x-data rompe Alpine;
  Chart.js v4 sin `animation=false` queda en blanco y engaña al assert_selector).
- **Chart en blanco**: el journey usa `assert_canvas_painted` (no `assert_selector`).

## Validación esperada (qa_claude smoke maestros)
- `GET /construccion/ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7/resumen-materiales/` → 200.
- Tabla presenta torres reales con material (E33, E54) + fila "Total".
- Canvas `#chart-materiales` pinta píxeles (no en blanco), sin pageerror JS.
- Entrada "Resumen de Materiales" visible en el sidebar de construcción.
