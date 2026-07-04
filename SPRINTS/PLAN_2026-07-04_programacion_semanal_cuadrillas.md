# PLAN — Programación semanal de cuadrillas (issue #178)

**Fecha:** 2026-07-04
**Issue:** Indunnova16/Instelec#178
**Estado:** Planning completado, listo para ejecución
**Ruta:** sprint_path (single-módulo: cuadrillas + actividades, per decisión Miguel 2026-06-28 —
NO handoff a /modulo pese a `complexity_class=epic` en F1; ver justificación abajo)

## Contexto

El cliente respondió con especificación técnica completa + Excel real (`Programación -
S27.xlsx`, 34 hojas) verificado dato-por-dato con openpyxl por F1. v1.0 COMPLETA
(build-for-client-validation, no MVP):

1. Parser de bloques de actividad por celda combinada en columna A/D (100% confiable) en vez
   del heurístico CARGO=CONDUCTOR sugerido por el cliente (97%, 3 excepciones reales en
   semanas 03/05/27).
2. Fix del bug confirmado en AMBOS importers existentes: la sección NOVEDADES no resetea el
   bloque activo → personal en vacaciones/incapacidad queda mezclado como miembro de la
   última actividad real de la hoja.
3. Soporte de hojas-semana `vc`/`C12`/`C16` (hoy mal excluidas / no matcheadas).
4. Columna PT SAP mapeada (hoy solo AVISOS/ORDEN).
5. Cargos `MALACATERO`/`COORDINADOR HSQ` agregados a `RolCuadrilla` (hoy caen en fallback
   silencioso a LINIERO_I).
6. Enlace PERSONAL↔PersonalCuadrilla vía CEDULA reusando el patrón resolver-o-crear de #176
   y el flag opt-in `crear_usuarios_faltantes` de #124.
7. UI nueva de Programación Semanal bajo `/cuadrillas/` (hoy esa ruta es solo un listado plano
   de `Cuadrilla` — el grid semanal + "Duplicar semana anterior" + export PDF/Excel horizontal
   NO existen y hay que construirlos).
8. Import masivo del nuevo formato horizontal conviviendo con el S18 vertical existente
   (#124), sin reemplazarlo.

**Nota de alcance — NO es el módulo `construccion:programacion_cuadrilla*`.** Ese namespace
(`apps/cuadrillas/views_pc_programacion.py`, templates `construccion/programacion_cuadrilla_*`)
es un concepto DISTINTO: asignación de una cuadrilla a un proyecto de construcción por
torre/año (`ProgramacionCuadrilla` ligado a `ProyectoConstruccion`). Este issue es sobre la
programación semanal de PERSONAL por actividad/línea/tramo desde el Excel operativo — no
tocar ese namespace, y elegir nombres de URL/template que no colisionen (`cuadrillas:semanal_*`
propuesto, no `programacion_cuadrilla*`).

**Por qué sprint_path y no handoff a /modulo:** todo el trabajo cae dentro de
`apps/cuadrillas/` + `apps/actividades/` (los dos importers ya existentes + la nueva UI de
grid). El único otro app tocado es el vínculo a `PersonalCuadrilla` vía CEDULA, que YA es
parte de `apps/cuadrillas` (catálogo de #176) — no se toca el módulo Colaboradores de forma
sustancial nueva, solo se reusa un patrón resolver-o-crear ya probado. Es una épica de UN SOLO
módulo (cuadrillas/actividades) → ejecuta en `/multiagente` en sprints secuenciales (A→B→C),
no en `/modulo`.

## Sub-items por sprint

### Sprint A — Fixes de importers existentes, backend puro (deployable_solo: true)
Sin UI nueva; corrige la lógica de parseo en los 2 importers ya existentes. Testeable con
`pytest` contra fixtures del Excel real (openpyxl) sin depender de Sprint B/C. Deploy de bajo
riesgo: mejora silenciosamente la precisión del import, no cambia contratos de API/URLs.

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Parser de bloques: detectar fin-de-bloque por rango de celda combinada en columna A (fallback a heurístico CARGO=CONDUCTOR solo si no hay merge, log de advertencia) | `apps/cuadrillas/importers.py::ProgramacionS18CuadrillaImporter`, `apps/actividades/importers.py::ProgramacionSemanalImporter` | happy: bloque cierra en merge exacto; edge 1: semana 03/05/27 (las 3 excepciones CARGO=CONDUCTOR reales); edge 2: bloque de 1 sola fila | - | high | ✅ done |
| A2 | Fix NOVEDADES: resetear `actual`/`current_actividad_idx` a `None` al detectar la fila NOVEDADES en ambos importers; persistir esas filas como registro independiente persona+semana (nuevo modelo `NovedadPersonalSemana` o reutilizar `PersonalCuadrilla` con FK a semana + tipo_novedad) | `apps/cuadrillas/importers.py` (L715-725), `apps/actividades/importers.py` (L1130-1140), `apps/cuadrillas/models.py` o `models_base.py` (migración si modelo nuevo) | happy: NOVEDADES con 1-6 filas no se atribuye a última actividad; edge 1: hoja sin NOVEDADES (no debe fallar); edge 2: NOVEDADES con cédula duplicada de una actividad real (debe quedar en AMBOS: actividad + novedad, no excluyente) | A1 | medium | ✅ done |
| A3 | Detección de hoja-semana: aceptar `vc`/`C12`/`C16`/`12 (2)` sin hardcodear nombres — ajustar regex/lista SHEETS_EXCLUIR para no excluir `vc` y matchear `C\d+` además de numérico puro | `apps/cuadrillas/importers.py::_es_hoja_semanal / SHEETS_EXCLUIR`, `apps/actividades/importers.py` (equivalente si existe) | happy: `vc`,`C12`,`C16`,`12 (2)` matchean; edge: `pt-corredores`/`Hoja1`/`Hoja2`/`Hoja5` siguen excluidas | - | low | ✅ done |
| A4 | Agregar `PT SAP` (columna O) a `COLUMN_MAPPINGS` de `ProgramacionS18CuadrillaImporter`, con `_split_multi`/`_join_multi` (patrón ya existente, hasta 15 valores) | `apps/cuadrillas/importers.py` | happy: PT SAP multivalor se persiste y se re-serializa igual; edge: PT SAP vacío no rompe el import | - | low | ✅ done |
| A5 | Agregar choices `MALACATERO`/`COORDINADOR HSQ` a `RolCuadrilla` + `ROL_TEXTO_A_CHOICE`; reemplazar fallback silencioso a LINIERO_I por advertencia explícita si el CARGO no matchea ningún choice conocido | `apps/cuadrillas/models_base.py` (migración), `apps/cuadrillas/importers.py` | happy: fila con CARGO=MALACATERO / COORDINADOR HSQ se clasifica correcto; edge: CARGO desconocido nuevo genera warning explícito (no fallback mudo) | - | low | ✅ done |
| A6 | Enlace CEDULA→PersonalCuadrilla: reusar patrón resolver-o-crear Usuario de #176 + flag opt-in `crear_usuarios_faltantes` de #124 (default OFF = advertencia, no auto-crear) en el importer de Programación Semanal | `apps/cuadrillas/importers.py`, referencia a `apps/cuadrillas/views.py::_resolver_o_crear_usuario` | happy: cédula existente en PersonalCuadrilla se enlaza; edge 1: cédula no encontrada con flag OFF → advertencia + fila omitida (no crea); edge 2: cédula no encontrada con flag ON → crea usuario igual que #124 | - | medium | ✅ done |

### Sprint B — Import masivo del formato horizontal, conviviendo con S18 (deployable_solo: true, depende de Sprint A)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| B1 | Extender `detectar_formato_cuadrillas` (o vista de carga masiva) para reconocer el formato horizontal (34 hojas, bloques por merge) como una rama NUEVA que convive con S18 vertical existente — NO reemplaza #124 | `apps/cuadrillas/importers.py::detectar_formato_cuadrillas`, `apps/cuadrillas/views_b4.py` | happy: sube `Programación - S27.xlsx` real y detecta formato horizontal correctamente; edge 1: sube un Excel S18 vertical viejo y sigue detectando ese formato sin regresión; edge 2: Excel con hojas mixtas (alguna semana + catálogos) no falla | A1, A2, A3, A4, A5, A6 | high | ⏳ pendiente |
| B2 | Actualizar `templates/cuadrillas/cuadrilla_upload.html` con mensaje de resumen (patrón SALTAR+RESUMEN de #124) explicando qué se importó por bloque/NOVEDADES/formato detectado | `templates/cuadrillas/cuadrilla_upload.html`, `apps/cuadrillas/views_b4.py` | happy: resumen post-import muestra conteo de bloques/novedades/omitidos; edge: 0 filas importadas muestra mensaje claro (no "0 sin explicación") | B1 | low | ⏳ pendiente |

### Sprint C — UI de Programación Semanal (grid + duplicar + export) (deployable_solo: false salvo C1, depende de Sprint A)

Épica del F1 (`tipo: epic`) descompuesta en sub-items no-épicos para no disparar el gate P-11
de handoff — cada uno es una vista/acción concreta y acotada.

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| C1 | Vista grid semanal read-only: `/cuadrillas/semanal/<int:anio>/<int:semana>/` — cuadrillas × días × actividades de una semana ya importada, agrupado por bloque, con sección NOVEDADES visible aparte | `apps/cuadrillas/views_semanal.py` (`ProgramacionSemanalGridView` + `ProgramacionSemanalIndexView`), `apps/cuadrillas/urls.py`, `templates/cuadrillas/programacion_semanal_grid.html` | happy: semana con datos reales muestra bloques + novedades; edge 1: semana sin datos muestra estado vacío, no 500; edge 2: NOVEDADES en su propia sección | A1, A2, A6 | high | ✅ done (v mínima Sprint BC — aloja C2/C3; nav prev/next; requiere login) |
| C2 | Botón "Duplicar semana anterior": vista POST que copia `Cuadrilla`+`CuadrillaMiembro` de la semana N-1 a la semana N (sin NOVEDADES, que no se duplican por naturaleza) | `apps/cuadrillas/views_semanal.py` (`ProgramacionSemanalDuplicarView`), `apps/cuadrillas/urls.py`, template del grid (botón) | happy: duplicar semana con datos crea copia editable (fechas +7d); edge 1: origen sin datos → error claro, no crea vacío; edge 2: destino con datos → confirmación, NO destructivo (omite existentes); edge 3: cruce de año (sem 1 ← última ISO del año previo) | C1 | medium | ✅ done |
| C3 | Export PDF imprimible de la programación semanal (WeasyPrint — ya en `requirements/base.txt` + libs nativas en Dockerfile de prod) | `apps/cuadrillas/views_semanal.py` (`ProgramacionSemanalPDFView`), `templates/cuadrillas/programacion_semanal_pdf.html`, `apps/cuadrillas/urls.py` | happy: export de semana con datos genera PDF (application/pdf, bytes>0, `%PDF`); edge: semana vacía exporta PDF con "sin datos", no 500 | C1 | medium | ✅ done |
| C4 | Export Excel horizontal: replica estructura real de columnas A-P (sin merges, por regla de negocio #3 confirmada por cliente) usando openpyxl | `apps/cuadrillas/views.py` (nueva `ProgramacionSemanalExcelXlsxView`), `apps/cuadrillas/urls.py` | happy: export contiene headers idénticos a los del Excel original y datos de la semana consultada; edge: NOVEDADES se exporta en su propia sección/hoja, no mezclada | C1, B1 | high | ⏳ pendiente |

## DAG dependencias

```
A3 ─┐
A4 ─┤
A5 ─┼─→ A1 → A2 ─┬─→ B1 → B2
A6 ─┘            │
                  ├─→ C1 → C2
                  │      → C3
                  └────→ C4 (también depende de B1)
```

Entrypoints sin dependencias (primera tanda ejecutable en paralelo): **A1** (nota: A1 no
depende de nada externo, es el parser de bloques — A2 sí depende de A1), A3, A4, A5, A6.

## Riesgos y mitigaciones

- **Riesgo medio (marcado por F1):** cambiar la lógica de detección de bloques (A1) puede
  alterar el comportamiento de #124 en producción para cargas ya en curso. Mitigación: test
  obligatorio contra dato legacy — correr el importer con ≥1 Excel real ya cargado
  anteriormente (no solo `Programación - S27.xlsx`) y comparar conteo de `Cuadrilla`/
  `CuadrillaMiembro` creados antes/después del cambio.
- **NOVEDADES como registro independiente (A2):** decisión de modelo (nuevo modelo vs.
  reutilizar `PersonalCuadrilla` con flag) se deja a F3 sprint_exec — evaluar cuál requiere
  menos migración y es más consistente con el patrón ya usado en #176.
- **B1 conviviencia de formatos:** riesgo de regresión sobre #124 (S18 vertical). Mitigación:
  edge test explícito (ver tabla B1) subiendo un Excel S18 viejo real tras el cambio.
  **importer legacy** — evaluar en Sprint B si `views_b4.py::CuadrillaMasivaUploadView` o el
  detector de formato es el punto correcto de ramificación (F1 no confirmó el nombre exacto
  de la función de detección; usar `grep -n "def detectar_formato\|COLUMN_MAPPINGS"
  apps/cuadrillas/importers.py` al iniciar B1 para confirmar firma exacta).
- **C1-C4 UI nueva:** no colisionar con namespace `construccion:programacion_cuadrilla*`
  (concepto distinto, ver nota de alcance arriba). Usar prefijo `cuadrillas:semanal_*`.
- **Anomalía hoja 27** (3 filas administrativas huérfanas post-NOVEDADES sin bloque): decisión
  ya tomada por F1 — NO auto-importar, solo advertencia. C1 debe reflejar esa advertencia en
  el grid, no ocultarla silenciosamente.
- **Riesgo global: medio** (heredado de F1) — mitigado por la secuenciación A→B→C con tests de
  regresión legacy en cada sprint antes de avanzar al siguiente.

## Validación esperada (qa_claude smoke maestros)

- Sprint A: sin superficie HTTP nueva — validar con `pytest` (happy + 2 edge cada sub-item) +
  smoke de que `/cuadrillas/masiva/upload/` sigue respondiendo 200 y el import S18 legacy
  sigue funcionando (no regresión).
- Sprint B: smoke subiendo `Programación - S27.xlsx` real a `/cuadrillas/masiva/upload/` (o la
  ruta que B1 determine) y verificar mensaje de resumen con conteo de bloques/novedades.
- Sprint C: smoke de `/cuadrillas/semanal/<anio>/<semana>/` con datos ya importados en Sprint
  B — grid visible, botón duplicar funcional, export PDF/Excel descargable (HTTP 200 +
  Content-Type correcto). Instrucción de validación cliente: pedir a Instelec que compare
  visualmente el export Excel horizontal contra `Programación - S27.xlsx` original (misma
  estructura de columnas, sin merges).
