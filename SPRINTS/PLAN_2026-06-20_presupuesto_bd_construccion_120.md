# PLAN — Presupuesto BD Contable: carga v2 en Construcción + redirect URL vieja (issue #120)

**Fecha:** 2026-06-20
**Issue:** [Indunnova16/Instelec#120](https://github.com/Indunnova16/Instelec/issues/120)
**Estado:** Planning completado, listo para ejecución
**Decisión de scope (Miguel):** "ejecutar lo inequívoco" — NO el rehace total. El filtro MES queda como pregunta al cliente en el cierre (F6).

## Contexto
El cliente (anasofiamc1-cpu, 2026-06-06) reclama que el módulo Presupuesto Planeado "sigue con la visual de antes" (filtros Unidad de Negocio/Contrato), pide 2 pestañas (BASE DE DATOS + PRESUPUESTO) con la estructura del Presupuesto.xlsx, un filtro MES, y que aplique **tanto a Mantenimiento como a Construcción**.

La v2 con 2 pestañas YA existe en Mantenimiento (PR #126: `ContableCompleteImporter`, `MapeoCtaRubro`, `PresupuestoPlaneadoViewV2`) servida en `/financiero/cargar-bd-contable/`.

**Hallazgo F2 (inspección de código):** el lado de **Construcción YA está implementado** por #123/PR #126:
- Vista `PresupuestoPlaneadoConstruccionView` (apps/construccion/views_fin.py) tiene `post()` que detecta el formato (`detect_excel_format_construccion`), corre `ContableConstruccionExcelImporter` / `PresupuestoConstruccionExcelImporter` y persiste en `PresupuestoDetalladoConstruccion.datos`.
- El GET arma `rubro_rows` con `build_rubro_display_rows` (espejo #120).
- El template `construccion/financiero_presupuesto_planeado.html` ya renderiza **2 pestañas** (`Cargar Base de Datos` + `Presupuesto por Rubros`) con partials `_financiero_cargar_bd.html` (input file .xlsx) y `_financiero_presupuesto_tabla.html`.

Por tanto, el **único net-new inequívoco** de este sprint es el **redirect de la URL vieja de Mantenimiento** (`/financiero/presupuesto-planeado/`, que sirve `PresupuestoPlaneadoView` con los filtros viejos) hacia la v2 (`/financiero/cargar-bd-contable/`), para que el cliente deje de aterrizar en la pantalla vieja. El lado Construcción se valida (no se recodifica).

## Sub-items por sprint

### Sprint A (deployable_solo: true)
| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | **Redirect URL vieja → v2 (Mantenimiento).** Reemplazar el patrón `path('presupuesto-planeado/', views.PresupuestoPlaneadoView...)` por un `RedirectView.as_view(pattern_name='financiero:cargar_bd_contable', permanent=False, query_string=True)`. Así `/financiero/presupuesto-planeado/` (filtros viejos Unidad de Negocio/Contrato) redirige a `/financiero/cargar-bd-contable/` (v2, 2 pestañas). `PresupuestoPlaneadoView` queda como código muerto (no se borra en este sprint para no arrastrar refactor; opcional anotar `# deprecada por #120`). | `apps/financiero/urls.py` (línea 23) | test_redirect: GET `/financiero/presupuesto-planeado/` autenticado → 302 a `cargar-bd-contable/`; journey s2 E2E | - | low | ⏳ pendiente |
| A2 | **Verificación carga BD v2 en Construcción (sin código).** Confirmar vía E2E (journey s1) que `/construccion/<uuid>/financiero/presupuesto-planeado/` renderiza las 2 pestañas + input de carga. Si el journey RED por algo real (template/partial faltante en la branch de despliegue), F3 lo arregla; si GREEN, el sub-item es solo validación (ya implementado por #123). | (read-only / validación) | journey s1 E2E (2 pestañas + input file) | - | trivial | ⏳ pendiente |

> **No hay Sprint B.** El filtro MES (ambiguo: matriz mensual vs filtro visual) NO entra a esta v1.0 por decisión explícita de Miguel — se pregunta al cliente en F6 (`pregunta_cliente_cierre`).

## DAG dependencias
A1 (independiente) · A2 (independiente, validación)
Ambos van en una sola branch / un solo deploy.

## Requiere migración
**NO.** A1 es solo un cambio de routing (urls.py). Construcción reusa `PresupuestoDetalladoConstruccion.datos['finv2_bd']` que ya existe (#123). No hay cambios de modelo.

## Riesgos y mitigaciones
- **Riesgo bajo (A1):** `RedirectView` con `query_string=True` propaga `?anio=&contrato=`; verificar que la v2 acepte esos params sin 500 (los ignora si no aplican). Mitigación: el journey s2 hace GET simple y asserta el landing en la v2.
- **Riesgo de validación (A2):** la branch de despliegue podría no tener el template de construcción si #123 no llegó a `main` (verificar `git log` en F3). Mitigación: el journey s1 lo detecta; si RED, F3 porta el template/partial.
- **Reproceso (bounce=1):** el cliente ya rebotó esta pantalla. La causa raíz probable es **confusión de URL** (veía la vieja `/presupuesto-planeado/` en vez de la v2). El redirect ataca exactamente eso. Post-mortem para F6: la entrega previa (#126) implementó la v2 pero NO retiró/redirigió la pantalla vieja → el cliente siguió aterrizando en la vieja.

## Validación esperada (qa_claude — journeys del RUN)
- **s1 (construcción):** GET `/construccion/ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7/financiero/presupuesto-planeado/` → 200, contiene "Cargar Base de Datos" + "Presupuesto por Rubros", existe `input[type=file][accept='.xlsx']`.
- **s2 (redirect):** GET `/financiero/presupuesto-planeado/` → redirige a `/financiero/cargar-bd-contable/`, contiene "Cargar Base de Datos Contable" + "Presupuesto Planeado".
- Smoke maestros financiero: dashboard + cargar-bd-contable + editar-mapeo HTTP 200.

## Pregunta al cliente (F6)
"¿El filtro MES que pedís es (a) un desglose del presupuesto por cada mes (tabla matriz rubro×mes como el Presupuesto.xlsx) o (b) un filtro visual para ver un mes a la vez? Según tu respuesta lo agregamos."
