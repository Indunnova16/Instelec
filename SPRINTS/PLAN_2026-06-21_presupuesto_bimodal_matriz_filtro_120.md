# PLAN — Presupuesto Planeado BI-MODAL: vista matriz rubro×12-meses + filtro mes (issue #120)

**Fecha:** 2026-06-21
**Issue:** [Indunnova16/Instelec#120](https://github.com/Indunnova16/Instelec/issues/120)
**Estado:** Planning completado, listo para ejecución
**Decisión de scope (Miguel):** COMPLETO — entregar la v1.0 con AMBAS vistas (matriz + filtro mes) en esta ola, NO partir.
**Reproceso:** bounce=2, categoría FIX_INCOMPLETO. La v2 (#126) entregó 2 PESTAÑAS pero solo 1 vista plana (rubro→total anual). El reclamo vigente es la BI-MODALIDAD VISUAL del presupuesto, que hoy NO existe.

## Contexto
Último comentario cliente (Indunnova 2026-06-21): "pueden ser ambos — Vista matriz (a) para ver el panorama del año con los 12 meses como columnas, igual que el Presupuesto.xlsx; Filtro mes (b) para enfocarse en un mes específico y ver el detalle". Aplica **tanto a Mantenimiento como a Construcción**.

### Hallazgo F2 (lectura de código + del Excel oráculo)
- La pestaña "Presupuesto Planeado" hoy renderiza una tabla plana: `rubro → total ANUAL → % presupuesto` (`templates/financiero/presupuesto_planeado_v2.html`, filas de `build_rubro_display_rows`). NO hay desglose mensual.
- **El importer contable (`ContableCompleteImporter.procesar_bd_completa`) suma `Neto` (col C) por `Cta equivalente` (col O) en UN solo `total` anual.** No bucketea por mes. → **Esta es la causa raíz del FIX_INCOMPLETO: sin datos mensuales no puede existir matriz ni filtro mes.**
- La BD `BASE DE DATOS.xlsx` (att_03, 23.185 filas) SÍ trae el mes: **col D = `Fecha` (datetime)** y col F = `Periodo` (YYYYMM). El bucketing mensual es posible sin pedir nada al cliente.
- **Oráculo de la matriz**: la hoja `Presupuesto` del mismo archivo tiene exactamente la forma pedida — `Etiquetas de fila` (rubros) × columnas **julio, agosto, … junio, TOTAL** (año fiscal **julio→junio**). La matriz a construir debe replicar ese orden y los 12 meses + TOTAL.
- Construcción ya espeja el lado financiero (`PresupuestoPlaneadoConstruccionView` + `build_rubro_display_rows` + `templates/construccion/_financiero_presupuesto_tabla.html`), así que el mismo refactor de datos+template aplica a ambos lados.

### Forma de datos objetivo (lo que produce A1)
Extender `finv2_bd` para que cada rubro y cada cuenta lleve también `meses`:
```json
"finv2_bd": {
  "total": <anual>, "cuentas_count": N, "cuentas_no_mapeadas": [...],
  "rubros": {
    "<Rubro>": {
      "total": <anual>,
      "meses": {"julio": x, "agosto": x, ..., "junio": x},
      "cuentas": [{"cta_equivalente": "...", "descripcion": "...", "total": <anual>,
                   "meses": {"julio": x, ..., "junio": x}}]
    }
  }
}
```
Constante única de orden de meses (año fiscal): `MESES_FISCALES = ['julio','agosto','septiembre','octubre','noviembre','diciembre','enero','febrero','marzo','abril','mayo','junio']`.

## Sub-items por sprint

### Sprint A (deployable_solo: false — A1→A2→A3 van en una sola branch / un solo deploy)
| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | **Backend: bucketing mensual del importer contable.** Extender `ContableCompleteImporter.procesar_bd_completa` para leer col D (`Fecha`) — fallback col F (`Periodo` YYYYMM) — y acumular `Neto` por mes en `meses` para cada cuenta y cada rubro (sumando hijos). Añadir `MESES_FISCALES` (orden julio→junio) y helper `build_rubro_matrix_rows(datos)` que devuelve filas con `meses[]` ordenados + totales por columna (mes) y por fila (rubro). `build_rubro_display_rows` se conserva (vista plana fallback). Manejo de errores: filas sin fecha caen en un bucket "sin_mes" excluido del total mensual pero contado en el anual. | `apps/financiero/importers_finv2.py` | `apps/financiero/tests/test_finv2_matriz.py` (nuevo): happy (BD con fechas en ≥3 meses → meses correctos por rubro), edge1 (fila sin fecha → no rompe, va a sin_mes), edge2 (datos legacy sin `meses` → matrix_rows tolera y rinde 0s) | - | high | ⏳ pendiente |
| A2 | **UI Mantenimiento: vista matriz + toggle + filtro mes.** En `presupuesto_planeado_v2.html`, pestaña "Presupuesto Planeado": agregar Alpine `x-data` con `vista` (`'matriz'`/`'mes'`, inicial de `?vista=`) y `mesSel` (de `?mes=`). (a) **Vista Matriz**: tabla `rubro × 12 meses (julio→junio) + TOTAL`, fila de totales por columna, contenedor `[data-vista='matriz']`. (b) **Filtro Mes**: `select[name='mes']` con los 12 meses + render reducido (rubro→valor de ese mes), contenedor `[data-vista='mes']`. Botones toggle "Vista Matriz | Filtro Mes". La view pasa `matrix_rows` + `meses_fiscales` + `mes_sel` + `vista` al contexto. Formato `floatformat:"0"|intcomma` (enteros es-CO OK). Estados: empty-state si no hay `finv2_bd`. | `apps/financiero/views_finv2_presupuesto.py`, `templates/financiero/presupuesto_planeado_v2.html` | journey `i120_a1_matriz_12_meses_mantenimiento` + `i120_a2_filtro_mes_mantenimiento` | A1 | high | ⏳ pendiente |
| A3 | **UI Construcción: espejo de la bi-modalidad.** Misma matriz+toggle+filtro en el partial de construcción; la view pasa `matrix_rows`/`meses_fiscales`/`vista`/`mes_sel`. Reusar el mismo bloque de template (idealmente extraer un partial compartido `_presupuesto_bimodal_tabla.html` incluido por ambos lados para no divergir). | `apps/construccion/views_fin.py`, `templates/construccion/_financiero_presupuesto_tabla.html`, `templates/construccion/financiero_presupuesto_planeado.html` (+ posible partial nuevo `templates/financiero/_presupuesto_bimodal_tabla.html`) | journey `i120_a3_matriz_y_filtro_construccion` | A1, A2 | medium | ⏳ pendiente |

> **No hay Sprint B.** Las dos vistas (matriz + filtro mes) y los dos lados (Mantenimiento + Construcción) entran COMPLETOS a la v1.0 por decisión explícita de Miguel.

## DAG dependencias
A1 → A2 → A3 (A2 y A3 ambos consumen la salida `meses`/`matrix_rows` de A1; A3 reusa el template de A2). Una sola branch, un solo deploy.

## Requiere migración
**NO.** El cambio es de estructura del JSON `finv2_bd` (sub-llave `meses` añadida), no de schema. Los presupuestos ya cargados con la v2 vieja (sin `meses`) deben tolerarse: `build_rubro_matrix_rows` rinde 0 por mes si falta la llave, y un re-upload del Excel los rellena (A1). NO se reescriben datos en prod automáticamente.

## Riesgos y mitigaciones
- **Riesgo alto (A1):** la col `Fecha` puede venir vacía/no-datetime en parte de las 23k filas. Mitigación: parser tolerante (datetime → mes; si `Periodo` YYYYMM presente → derivar mes; si nada → bucket `sin_mes`, contado solo en anual). Test edge con fila sin fecha.
- **Riesgo de paridad anual:** la suma de los 12 meses por rubro debe igualar el `total` anual ya mostrado en la vista plana (no romper el número que el cliente ya vio). Mitigación: test que asserta `sum(meses.values()) == total` salvo lo que cae en `sin_mes`.
- **Riesgo de datos legacy (no re-cargados):** un presupuesto cargado por la v2 vieja no tiene `meses`. La matriz mostraría ceros hasta re-subir. Mitigación: el journey siembra datos CON `meses` (valida el render); el comentario al cliente le pide re-subir la BD una vez para poblar la matriz histórica.
- **Año fiscal julio→junio:** el orden de columnas NO es enero→diciembre. Mitigación: `MESES_FISCALES` fija el orden; assert del journey verifica que "Julio" aparece antes que "Junio".
- **Divergencia Mantenimiento↔Construcción:** dos templates podrían quedar inconsistentes. Mitigación A3: extraer partial compartido.

## Validación esperada (qa_claude — journeys del RUN, `journeys/Instelec_120.yaml`)
- **i120_a1_matriz_12_meses_mantenimiento:** GET `/financiero/cargar-bd-contable/?anio=2099&tab=planeado&vista=matriz` (con `finv2_bd.meses` sembrado) → 200; aparecen los 12 encabezados de mes (Julio…Junio); rubros "Ingresos Operacionales" + "Servicios Publicos"; toggle "Vista Matriz"; `[data-vista='matriz'] table` existe.
- **i120_a2_filtro_mes_mantenimiento:** GET `…&vista=mes&mes=julio` → 200; `select[name='mes']` existe; contenedor `[data-vista='mes']`; rubro visible.
- **i120_a3_matriz_y_filtro_construccion:** GET `/construccion/<uuid>/financiero/presupuesto-planeado/?anio=2099&tab=planeado&vista=matriz` → 200; 12 meses + rubro + toggle; `[data-vista='matriz'] table`.
- Smoke maestros financiero: dashboard + cargar-bd-contable + editar-mapeo HTTP 200.

## Post-mortem para el comentario del issue (F6 — reproceso)
- **Qué afirmamos antes:** "v2 con 2 pestañas + redirect desplegada" (#126).
- **Qué falló realmente:** la v2 mostró una tabla plana (rubro→total anual); el cliente pedía BI-MODALIDAD visual (matriz 12-meses + filtro mes), que requería un cambio de DATOS (bucketing mensual) que no se hizo. Se interpretó "ambos" como "ambas pestañas", no como "dos modos de visualización".
- **Por qué no lo atrapamos:** el triage v1.0 aplazó "filtro mes" a pregunta-cliente sin notar que la matriz anual también faltaba; nunca se compartió la vista mensual contra el oráculo Presupuesto.xlsx.
- **Corrección esta vez:** importer bucketea por mes (col Fecha), matriz julio→junio igual al oráculo, filtro mes con selector, ambos lados, validado E2E contra datos mensuales.
- Marcador watchdog: `<!-- REPROCESO_DATA: {"category":"FIX_INCOMPLETO","root":"intent_mal_leido","bounce":2} -->`
