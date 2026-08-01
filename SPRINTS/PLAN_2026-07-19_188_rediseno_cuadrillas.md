# PLAN — Rediseño Programación Semanal de Cuadrillas (issue #188)

**Fecha:** 2026-07-19
**Issue:** [Indunnova16/Instelec#188](https://github.com/Indunnova16/Instelec/issues/188)
**Estado:** Planning completado, listo para ejecución (F3 sprint_exec)
**Ruta:** sprint_path — completo, SIN partir (decisión explícita de Miguel tras el gate de
scope de la 1ra corrida de F2, que bloqueó por `sub-item #1 = epic`). Se ejecuta todo en este
RUN/sprint, con #1 descompuesto INTERNAMENTE en sub-items de implementación (A2-A7) para dar
a F3 una ruta de ejecución clara — esa descomposición interna NO es "partir el scope".

## Contexto

Rediseño Sprint D de #178 sobre una base ya 🟢 validada en prod (C1 grid read-only, C2
duplicar semana, C3 export PDF). El cliente (comentario 2026-07-17 sobre #178) pide una
v1.0 completa: grid editable in-place (crear/editar bloques y personal sin recargar),
cascada de selects para tipo de actividad/línea/tramo, alta de personal integrada al maestro
Colaboradores (#176, ya en prod), validación de duplicados, fusión de pantallas
`/cuadrillas/` + `/cuadrillas/semanal/`, pestañas "Semanas"/"Mapa", y reubicación de los
botones de carga masiva de personas hacia `/cuadrillas/colaboradores/`.

**Grounding adicional de código hecho en esta corrida de F2** (más allá del bandeo por
banda de complejidad ya confirmado en la corrida anterior, que se reusa tal cual):

1. **`Cuadrilla` (el "bloque de actividad" que arma el grid) NO tiene `tipo_actividad` ni
   `tramo`** — solo `linea_asignada`. La cascada "Tipo actividad → Línea → Tramo" que pide
   el cliente requiere **2 campos nuevos** en `Cuadrilla` (migración aditiva, nullable).
2. **`PersonalCuadrilla` (maestro Colaboradores) NO tiene `celular`** — el cliente pide
   autocompletar "cédula/celular/cargo/rol", pero el maestro solo guarda
   nombre/documento/rol_cuadrilla/salario/fechas. `celular` sí existe como concepto en el
   dominio (`ProgramacionS18CuadrillaImporter`/`ProgramacionSemanalImporter` ya lo parsean
   del Excel del cliente hacia `Usuario.telefono`) pero **no en el maestro que alimenta el
   autocompletado**. Requiere migración aditiva (`celular` CharField blank en
   `PersonalCuadrilla`) + exponerlo en `PersonalCuadrillaAPIView`.
3. **No existe campo de placa manual por miembro.** "Placa manual solo si cargo=Conductor"
   requiere un campo nuevo `placa_vehiculo` en `CuadrillaMiembro` (hoy solo existe
   `es_conductor_interno`, boolean).
4. **El patrón resolver-o-crear ya existe y es reusable, con evidencia de que funciona en
   prod:** `CuadrillaMiembroAddView._resolver_o_crear_usuario` (apps/cuadrillas/views.py:534)
   resuelve/crea el `Usuario` a partir de un `PersonalCuadrilla` por documento — exactamente
   el patrón que sub-item #3 necesita para el grid nuevo. El template `detalle.html`
   (L218-274) ya implementa el flujo UI completo (input documento + datalist autocompletado +
   JS `autoCargarDatosPorDocumento()` + campos readonly + costo/día) contra
   `PersonalCuadrillaAPIView` — **se reusa el mismo patrón probado**, no se reinventa.
5. **`CuadrillaMiembro.unique_together = ['cuadrilla', 'usuario', 'activo']` ya existe a
   nivel de BD.** La regla de negocio de "no duplicados" YA está enforced — `sub-item #4` es
   principalmente **superficie UX** (resaltar/avisar inline en el nuevo grid HTMX, en vez del
   mensaje full-page-reload que usa hoy `CuadrillaMiembroAddView`), no una regla nueva.
6. **Hallazgo operativo (riesgo, no bloqueante):** la tabla `tramos` está **vacía en prod
   (0 filas)** — verificado por SELECT directo. La cascada Línea→Tramo va a funcionar
   técnicamente pero **no tendrá opciones reales** hasta que el cliente cargue Tramos (dato
   maestro fuera del scope de #188 — ya existe CRUD/importer de Tramo en `apps/lineas`). Se
   documenta como riesgo operativo del DoD; el journey de validación crea su propio Tramo
   `QA_E2E_` para probar el mecanismo (no depende de que el cliente ya haya cargado el dato).
7. **`CuadrillaListView` (listado, HTMXMixin+partial) y `ProgramacionSemanalGridView`
   (TemplateView) usan modelos de acceso a datos distintos** (queryset+paginación por semana
   vía parseo de código en un caso, `_contexto_semana`/`_bloques_qs` en el otro) — la fusión
   (#6) reconcilia ambos sobre el mismo querySet base (`Cuadrilla` filtrado por prefijo de
   código de semana), reutilizando `_bloques_qs`/`_contexto_semana` de `views_semanal.py`
   como fuente única de verdad y retirando el queryset propio de `CuadrillaListView`.

## Decisiones de diseño DEFAULT (documentadas, pendientes de confirmación del cliente)

- **#10 — Destino de "Nueva Cuadrilla":** DEFAULT = se mantiene como botón separado en la
  pantalla fusionada (no se fusiona al flujo de crear/editar actividad del grid). Es la
  opción más simple y menos disruptiva; el botón sigue abriendo el modal HTMX existente
  (`CuadrillaCreateView`). **Pendiente de confirmación del cliente** — no bloquea el resto
  del scope (F1 ya lo evaluó así, confirmado en esta corrida).
- **Contenido de la pestaña "Mapa" (#7):** DEFAULT = el mapa Leaflet en tiempo real que ya
  existe en `lista.html` (marcadores por cuadrilla, actualización cada 30s) se traslada TAL
  CUAL a la pestaña "Mapa" de la pantalla fusionada — sin contenido nuevo, porque el
  comentario del cliente no especifica más allá de lo ya construido.

## Sub-items ejecutables (Sprint único — v1.0 completa, sin Sprint B/C)

`#1` (epic, bandeado en la corrida previa) se descompone en **A2-A7**. El resto de sub-items
originales de F1 mapea 1:1 a A8-A13. `#10` no es un sub-item ejecutable (es el insumo del
cliente de la sección anterior).

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | **Migraciones aditivas** (todas nullable/blank, cero backfill): `Cuadrilla.tipo_actividad` FK a `actividades.TipoActividad` (null=True, blank=True), `Cuadrilla.tramo` FK a `lineas.Tramo` (null=True, blank=True), `PersonalCuadrilla.celular` CharField(max_length=20, blank=True), `CuadrillaMiembro.placa_vehiculo` CharField(max_length=10, blank=True) | `apps/cuadrillas/models_base.py`, `apps/cuadrillas/migrations/00XX_bloque_tipo_tramo_celular_placa.py` | `tests_issue_188.py::test_migraciones_aditivas_no_rompen_filas_existentes` (bloques/miembros/personal ya cargados siguen leyendo bien con los campos nuevos en `None`/`""`) | - | low | ✅ validado E2E prod |
| A2 | **Shell interactivo del grid**: convertir cada bloque de `programacion_semanal_grid.html` en un partial HTMX (`templates/cuadrillas/partials/_bloque_card.html` = vista; `_bloque_form.html` = edición) con `hx-target`/`hx-swap="outerHTML"` por card + Alpine `x-data="{editando:false}"` para alternar vista/edición sin JS custom pesado. Sin endpoints nuevos todavía — es el maquetado base que A3-A7 completan. Incluye el botón "+ Nuevo bloque" (abre `_bloque_form.html` vacío vía HTMX) | `templates/cuadrillas/programacion_semanal_grid.html`, `templates/cuadrillas/partials/_bloque_card.html` (nuevo), `templates/cuadrillas/partials/_bloque_form.html` (nuevo) | Render-only: template renderiza con 0/1/N bloques sin error | A1 | medium | ✅ validado E2E prod |
| A3 | **Endpoint crear bloque** (`POST /cuadrillas/semanal/<anio>/<semana>/bloque/crear/`) con cascada Línea→Tramo por AJAX (`GET /cuadrillas/api/tramos-por-linea/?linea_id=` nuevo, filtra `Tramo.objects.filter(linea_id=...)`) — campos: nombre, tipo_actividad, línea, tramo, vehículo, supervisor, observaciones. Devuelve el partial `_bloque_card.html` renderizado (HTMX swap `beforeend` en el contenedor de bloques), sin reload | `apps/cuadrillas/views_semanal.py` (`ProgramacionSemanalBloqueCrearView`, `TramosPorLineaAPIView`), `apps/cuadrillas/urls.py` (o `views_semanal.urlpatterns`), `templates/cuadrillas/partials/_bloque_form.html` | happy: crear bloque con tramo real (QA_E2E_) → aparece en grid sin reload; edge 1: línea sin tramos (combo vacío, no rompe); edge 2: tipo_actividad/tramo omitidos (opcionales, bloque se crea igual) | A1, A2 | high | ✅ validado E2E prod |
| A4 | **Endpoint editar bloque** (`POST /cuadrillas/semanal/bloque/<uuid>/editar/`) — mismos campos de A3 sobre un bloque existente, guarda y devuelve `_bloque_card.html` actualizado sin reload | `apps/cuadrillas/views_semanal.py` (`ProgramacionSemanalBloqueEditarView`), `templates/cuadrillas/partials/_bloque_form.html` (reusa el de A3, precargado) | happy: editar nombre/tramo de un bloque existente y verificar que persiste; edge: guardar sin cambios no rompe | A3 | medium | ✅ validado E2E prod |
| A5 | **Endpoint agregar personal a un bloque** (`POST /cuadrillas/semanal/bloque/<uuid>/miembro/agregar/`) — REUSA el patrón probado de `CuadrillaMiembroAddView`/`detalle.html`: input documento + datalist autocompletado AJAX vía `PersonalCuadrillaAPIView` (extendida en A1 para incluir `celular`) + `_resolver_o_crear_usuario` (extraído a helper compartido `apps/cuadrillas/services.py` para no duplicar entre `views.py` y `views_semanal.py`). Si el `Cargo` elegido es `CONDUCTOR`, muestra campo manual `placa_vehiculo` (requerido); si no, oculto. Devuelve `_bloque_card.html` actualizado | `apps/cuadrillas/services.py` (nuevo — extrae `_resolver_o_crear_usuario`), `apps/cuadrillas/views.py` (usa el helper extraído, sin cambiar comportamiento), `apps/cuadrillas/views_semanal.py` (`ProgramacionSemanalMiembroAgregarView`), `templates/cuadrillas/partials/_bloque_card.html` | happy: agregar colaborador existente (documento real) a un bloque, verificar `CuadrillaMiembro` creado + `celular` visible; edge 1: documento inexistente → error inline claro; edge 2: cargo=CONDUCTOR sin placa → error de validación; edge 3: colaborador con Usuario ya resuelto (reuso, no duplica Usuario) | A1, A2, A3 | high | ✅ validado E2E prod |
| A6 | **Endpoint quitar/inactivar personal de un bloque** (`POST /cuadrillas/semanal/bloque/<uuid>/miembro/<miembro_uuid>/quitar/`) — marca `CuadrillaMiembro.activo=False`, devuelve `_bloque_card.html` actualizado | `apps/cuadrillas/views_semanal.py` (`ProgramacionSemanalMiembroQuitarView`), `templates/cuadrillas/partials/_bloque_card.html` | happy: quitar miembro, verificar que desaparece de la card y `activo=False` en BD; edge: quitar un miembro ya inactivo no rompe (idempotente) | A5 | low | ✅ validado E2E prod |
| A7 | **Validación de duplicado inline**: misma persona 2 veces en la misma actividad → resaltar y avisar. La regla de negocio YA existe a nivel de BD (`unique_together` cuadrilla+usuario+activo, ver hallazgo #5 arriba) — este sub-item captura el `IntegrityError`/pre-check en `ProgramacionSemanalMiembroAgregarView` (A5) y lo muestra como mensaje inline en el partial (HTMX), en vez del `messages` full-page-reload que usa hoy `CuadrillaMiembroAddView` | `apps/cuadrillas/views_semanal.py` (mismo endpoint de A5, catch + mensaje), `templates/cuadrillas/partials/_bloque_card.html` (bloque de error inline) | happy: agregar la misma persona 2 veces al mismo bloque → 2do intento muestra aviso inline, NO crea 2do `CuadrillaMiembro`; edge: la misma persona en 2 bloques DISTINTOS de la misma semana sí es válido (no debe bloquearse) | A5 | low | ✅ validado E2E prod |
| A8 | **Duplicar semana → editar el duplicado → guardar sin perder datos**: verificación/ajuste de integración — `ProgramacionSemanalDuplicarView` (ya existe, C2 validado prod) genera bloques que deben ser 100% editables vía A2-A7 sin pérdida de datos (mismo modelo `Cuadrilla`/`CuadrillaMiembro`, no requiere cambios de esa vista salvo que el testing revele un gap) | `apps/cuadrillas/views_semanal.py` (ajuste menor si aplica, no se anticipa reescritura) | happy: duplicar semana con datos → editar un bloque del duplicado (agregar personal, sub-item A5) → guardar → verificar que la semana ORIGEN no cambió y el duplicado persiste el nuevo miembro | A2, A3, A4, A5, A6, A7 | medium | ✅ validado E2E prod |
| A9 | **Fusionar `/cuadrillas/` (`CuadrillaListView`) con `/cuadrillas/semanal/` en una sola pantalla**, reconciliando el queryset propio de `CuadrillaListView` sobre `_bloques_qs`/`_contexto_semana` de `views_semanal.py` (fuente única de verdad, hallazgo #6 arriba). Preserva TODO lo ya validado en prod (export PDF, duplicar, filtros de listado, mapa). Diseño DEFAULT de "Nueva Cuadrilla": botón separado (ver sección de decisiones arriba) | `apps/cuadrillas/views.py` (`CuadrillaListView` → redirige o se fusiona con `ProgramacionSemanalGridView`), `apps/cuadrillas/views_semanal.py`, `apps/cuadrillas/urls.py`, `templates/cuadrillas/lista.html` (pasa a ser el shell fusionado), `templates/cuadrillas/programacion_semanal_grid.html` (su contenido migra a un partial de la pestaña "Semanas" de A10) | happy: `/cuadrillas/` (o la URL fusionada elegida) muestra el grid editable + acciones de listado en una sola pantalla; regresión: export PDF, duplicar y mapa siguen respondiendo 200 | A2 | high | ✅ validado E2E prod |
| A10 | **Reorganizar la pantalla fusionada en pestañas "Semanas" / "Mapa"** — "Semanas" = el grid editable (A2-A9); "Mapa" = DEFAULT el mapa Leaflet ya existente en `lista.html` (ver sección de decisiones arriba), sin contenido nuevo | `templates/cuadrillas/lista.html` (fusionada, tabs Alpine `x-data="{tab:'semanas'}"`) | happy: cambiar de pestaña sin reload (Alpine), el mapa sigue actualizándose cada 30s en su pestaña | A9 | medium | ✅ validado E2E prod |
| A11 | **Mover los botones de carga masiva de personas** ("Subir Personal", "📥 Plantilla", "Carga Masiva") desde la pantalla fusionada hacia `/cuadrillas/colaboradores/` — **deployable_solo: true**, aislado del resto | `templates/cuadrillas/lista.html` (fusionada, retirar los 3 botones), `templates/cuadrillas/colaboradores_lista.html` (agregarlos) | happy: los 3 botones/acciones NO aparecen en la pantalla fusionada, SÍ aparecen y funcionan en `/cuadrillas/colaboradores/` | - | low | ✅ validado E2E prod |
| A12 | **Suite de tests** — cubre A1-A11: in-place create/edit/agregar/quitar personal, cascada línea→tramo, duplicado, no-regresión de duplicar-semana (C2) y export PDF (C3) ya validados en prod, fusión de pantallas, pestañas, reubicación de botones | `apps/cuadrillas/tests_issue_188.py` (nuevo) | happy + ≥2 edge cases por sub-item (detallados en cada fila de arriba) | A1-A11 | high | ✅ validado E2E prod |
| A13 | Comentario al cliente con URLs + pasos numerados de validación (DoD, no código) | - | - | A1-A12 | trivial | ✅ validado E2E prod |

**Notas de banda de complejidad:** las bandas de A1-A11 son consistentes con el bandeo por
código ya confirmado en la corrida previa de F2 para los sub-items originales #1-#9 (mismo
criterio P-11 cualitativo). La descomposición de #1 en A2-A7 reparte la complejidad `epic`
original en piezas `medium`/`high` manejables para F3 — el conjunto sigue siendo el mismo
epic grande, ahora con una ruta de ejecución clara.

## DAG de dependencias

```
A1 (migraciones)
 └─→ A2 (shell HTMX/Alpine del grid)
      ├─→ A3 (crear bloque + cascada línea→tramo)
      │    └─→ A4 (editar bloque)
      ├─→ A5 (agregar personal, requiere A3 para el partial de card)
      │    ├─→ A6 (quitar personal)
      │    └─→ A7 (duplicado inline)
      └─→ A9 (fusión de pantallas, requiere el grid ya HTMX-listo)
           └─→ A10 (pestañas Semanas/Mapa)

A2, A3, A4, A5, A6, A7 → A8 (duplicar semana → editar sin perder datos)

A11 (mover botones carga masiva) — independiente, deployable_solo: true

A1..A11 → A12 (tests) → A13 (comentario cliente)
```

## Riesgos y mitigaciones

- **A3/A9 (alto — mayor superficie nueva del epic):** greenfield HTMX/Alpine sobre un
  template que hoy es 100% read-only (0 `hx-post`/`hx-get`/Alpine). Mitigación: A2 aísla el
  maquetado del wiring de datos antes de tocar backend; A3-A7 reusan el MISMO partial
  `_bloque_card.html` (un solo punto de swap, no 4 mecanismos distintos).
- **Tramo vacío en prod (0 filas) — operativo, no de código.** La cascada Línea→Tramo no
  tendrá datos reales hasta que el cliente cargue Tramos. Mitigación: journey de A3 crea su
  propio Tramo `QA_E2E_`; se documenta en el comentario final al cliente como acción
  pendiente de SU lado (cargar Tramos vía el CRUD/importer ya existente en `apps/lineas`).
- **A5 (alto — integración con maestro Colaboradores):** requiere extraer
  `_resolver_o_crear_usuario` a un helper compartido sin romper el flujo YA validado en prod
  de `CuadrillaMiembroAddView`. Mitigación: `apps/cuadrillas/tests_issue_176.py` (existente)
  sigue corriendo verde como test de no-regresión del refactor de extracción (A12 lo incluye
  explícitamente).
- **A9 (alto — reconciliación de 2 modelos de acceso a datos distintos):** riesgo de romper
  filtros/paginación de `CuadrillaListView` ya validados en prod. Mitigación: A12 cubre
  explícitamente filtros de listado + export PDF + duplicar + mapa como regresión, no solo
  el feature nuevo.
- **`#10` sin resolver (cliente):** diseño DEFAULT documentado arriba para A9/A10; si el
  cliente responde distinto tras el deploy, es un ajuste incremental sobre lo ya construido,
  no una reconstrucción.
- **Riesgo de golden journeys stale:** el corpus `Instelec.yaml` tiene journeys de #178
  (`b...`/read-only del grid actual) que asertan la vista READ-ONLY. Al pasar a editable,
  esos journeys siguen siendo válidos en lo que assertan (el grid sigue mostrando bloques +
  personal), pero si alguno assertaba explícitamente "no hay botones de edición" habría que
  revisarlo — no se detectó ninguno así en el corpus actual (los `b*` journeys validan
  render, no ausencia de acciones).

## Validación esperada (qa_claude / smoke maestros post-deploy)

- `/cuadrillas/` (fusionada) — carga 200, muestra grid + acciones de listado, pestañas
  Semanas/Mapa funcionan.
- Crear bloque nuevo con línea+tramo (QA_E2E) → aparece sin reload.
- Editar un bloque existente → persiste sin reload.
- Agregar colaborador real (documento de `personal_cuadrilla` activo) a un bloque → aparece
  con celular visible.
- Intentar agregar la misma persona 2 veces al mismo bloque → aviso inline, no duplica.
- Cargo=Conductor sin placa → bloqueado con mensaje claro.
- Duplicar semana anterior → editar el duplicado (agregar miembro) → semana origen intacta.
- Export PDF (`/cuadrillas/semanal/<anio>/<semana>/pdf/`) sigue en 200 (regresión C3).
- `/cuadrillas/colaboradores/` — botones de carga masiva presentes y funcionales; NO
  presentes en la pantalla fusionada.

## Definition of Done (v1.0 completa)

- [x] Migraciones creadas/aplicables (A1) — todas aditivas, sin backfill destructivo.
- [x] Backend: endpoints + forms + lógica de negocio (A3-A7, A9).
- [x] UI con estados completos: loading (HTMX indicator), success (swap visible), error
  (mensajes inline en A5/A7).
- [x] Tests cubren happy + ≥2 edge cases por sub-item (tabla arriba + A12).
- [x] Smoke E2E definido (sección de Validación esperada + journey YAML).
- [x] Instrucciones de validación cliente redactadas (A13).
