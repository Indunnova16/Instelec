# PLAN — #103 Módulo Financiero — complemento (no greenfield)

**Fecha**: 2026-05-28
**Autor**: Miguel + Claude
**Repo**: Indunnova16/Instelec
**Issue**: [#103](https://github.com/Indunnova16/Instelec/issues/103) (Ana Sofía, 2026-05-25, 0 comentarios)
**Status**: borrador, esperando GATE de Miguel

---

## 0. Hallazgo clave

El issue describe un módulo "nuevo" de 38h, pero al inspeccionar `apps/construccion/` el **80% del scope ya existe** (issues #69, #66, #70, mergeados antes de 2026-05-25). Ana Sofía probablemente abrió #103 sin saber que el trabajo previo cubrió la mayoría.

**Delta real: ~12h** (3 vistas + parser Excel + RBAC granular opcional).

---

## 1. Inventario — qué pide #103 vs qué existe hoy

| Spec #103 | Estado actual | Acción |
|---|---|---|
| Modelo `Presupuesto` | `CategoriaFinanciera`+`PeriodoFinanciero`+`MovimientoFinanciero(tipo=PRESUPUESTO)` cubren el espacio | ✅ Reusar, documentar mapping en docstring |
| Modelo `Transaccion` | `TransaccionContable` (líneas 2554+ models.py) — campos: fecha, descripcion, nit_proveedor, valor, iva, centro_costo, adjunto, siigo_id | ✅ Existe, FK a `MovimientoFinanciero` |
| Modelo `ConceptoFinanciero` | `CategoriaFinanciera` (21 categorías PDEO seedeadas en migration 0007) | ✅ Existe |
| Modelo `EstadoResultados` (PyG) | `ProyectoConstruccion.pyg_resumen_ejecutivo()` + `pyg_totales` properties | ✅ Existe como properties, NO se necesita modelo separado |
| Vista `FinancieroListView` (Dashboard) | `DashboardFinancieroView` @ `/construccion/<uuid>/dashboard-financiero/` con KPIs + alertas + curva S financiera | ✅ Existe |
| Vista `PyGListView` (Estado de resultados) | `DashboardFinancieroView` muestra `resumen=pyg_resumen_ejecutivo()` | ⚠️ Hay PyG en el dashboard pero NO una vista dedicada con drill-down |
| Vista `PresupuestoListView` (grid mensual) | `FinancieroGridView` @ `/construccion/<uuid>/financiero/` con grid editable categoría × período | ✅ Existe |
| Vista `TransaccionesListView` (BD con filtros) | ⚠️ NO existe vista lista global de `TransaccionContable` | ❌ FALTA |
| Vista `TransaccionesUploadView` (cargar Excel PDEO) | ⚠️ NO existe upload + parser | ❌ FALTA |
| Vista `ReportesFinancierosView` | ⚠️ NO existe reportes personalizados | ❌ FALTA |
| Parser PDEO Excel (23K rows) | ⚠️ NO existe management command | ❌ FALTA |
| RBAC perms `financiero.view_pyg`, etc | Usa `allowed_roles = ALL_ADMIN_ROLES` (genérico) | ⚠️ Granular FALTA — pero hay que decidir si vale la pena migrar 5 vistas existentes ahora |

---

## 2. Conflictos detectados

- **URL prefix divergente**: el issue pide `/construccion/financiero/<tab>/` (sin proyecto en el path); el código existente es `/construccion/<uuid:proyecto_id>/financiero/...` (por proyecto). El issue tiene sentido si las nuevas vistas son **globales** (no por proyecto) — apropiado para TransaccionesListView (todas las transacciones del aplicativo) y ReportesFinancieros (cross-proyecto).
- **Nombres de modelos**: si Ana Sofía espera ver clases con nombre `Transaccion` y `EstadoResultados`, hay que decidir si renombramos `TransaccionContable` → `Transaccion` (alias o rename) o si mantenemos y documentamos en el closeout.

---

## 3. Plan propuesto

### Approach: COMPLEMENTO (no /modulo)

Reusar el modelo PDEO existente y agregar lo que falta. Scope acotado, 1 PR único.

### Sub-items

| # | Tarea | Estimado | Depends | Output |
|---|---|---|---|---|
| 1 | `TransaccionesListView` global @ `/construccion/financiero/transacciones/` con filtros (proyecto, categoría, periodo, NIT, fecha) + paginación | 4h | — | view + template + 2 unit tests |
| 2 | `TransaccionesUploadView` @ `/construccion/financiero/transacciones/upload/` con form Excel PDEO, parser de las 4 hojas (BD, Res EP, Presupuesto, PyG) que pueble `CategoriaFinanciera` + `PeriodoFinanciero` + `MovimientoFinanciero` + `TransaccionContable` | 5h | 1 | view + management command `cargar_pdeo_excel <file> <proyecto>` + tests con fixture pequeño |
| 3 | `ReportesFinancierosView` @ `/construccion/financiero/reportes/` con 3 reportes: PyG por trimestre, Top 10 proveedores, Alertas de variación >50% | 3h | — | view + template + export CSV |
| 4 | (Opcional) PyG dedicated view drill-down @ `/construccion/<uuid:proyecto_id>/pyg/` | 2h | — | view + template basado en `pyg_resumen_ejecutivo()` |

**Total: 12h sin opcional · 14h con opcional**

NO incluido (sale de scope): RBAC granular — migrar 5 vistas existentes de `ALL_ADMIN_ROLES` a perms `view_pyg`/`view_presupuesto`/etc es un sub-issue separado por riesgo de regresión.

### Por qué NO /modulo

- 12h es scope acotado para 1 PR único, sin paralelización útil.
- No hay sub-features independientes (las 3 vistas comparten layout + lógica).
- /modulo agrega overhead (worktrees, scaffolding F2, sub-agents) sin ganancia para este tamaño.

### Approach correcto: protocolo manual

Aplicar el protocolo de 7 pasos como issue grande pero coherente:
1. Plan ya construido (este archivo)
2. Causa raíz N/A (no es bug)
3. Implementar las 3 vistas + parser secuencialmente, tests por cada una
4. Deploy único `gh workflow run deploy-cloudrun.yml --ref main`
5. Smoke con `/qa-prod Instelec --journey=financiero_transacciones` (nuevo journey a crear)
6. Comentario con 🟢 listing las 3 vistas + parser + decisiones tomadas
7. Asignar `anasofiamc1-cpu` (validador Instelec)

---

## 4. Preguntas para Miguel antes de empezar

1. **¿Confirmar approach complemento?** Si Ana Sofía espera un "módulo financiero nuevo" arquitectónicamente separado (apps/financiero_v2/), abrimos discusión. Mi recomendación: complemento.
2. **¿Incluir reporte de RBAC granular en el closeout** (para que Ana Sofía abra un sub-issue) o **dejarlo silencioso**?
3. **¿Vista PyG dedicada drill-down (item 4 opcional)** o suficiente con la sección PyG del Dashboard actual?
4. **Acceso al PDEO Excel real** para validar parser: ¿`Documentacion/PDEO -Detalle 2024-2025-2026.xlsx` está actualizado en el repo o necesito uno más reciente? (Excel del repo verifica el formato pero los 23K registros son del 2024-11 a 2025-02; ¿hay datos más nuevos?)

---

## 5. Riesgos identificados

- Parser PDEO sobre 23K filas en single transaction puede ser lento/OOM en Cloud Run 512Mi. **Mitigación**: chunked import vía Celery (ya hay infra `tasks.py` en `apps/financiero/`).
- Cargar el mismo Excel dos veces duplicaría transacciones. **Mitigación**: clave única por `(numero_factura, nit_proveedor, fecha, valor)` + check de idempotencia en parser.
- Datos financieros confidenciales: el adjunto Excel se sube a Cloud Storage. **Mitigación**: prefix `private/financiero/`, signed URLs con expiración corta, audit log de uploads.
