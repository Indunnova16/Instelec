# PLAN — Maestros editables: Tipos de Actividad y Colaboradores (issue #176)

**Fecha:** 2026-06-30
**Issue:** [Indunnova16/Instelec#176](https://github.com/Indunnova16/Instelec/issues/176)
**Estado:** Planning confirmado por F2, listo para F3 sprint_exec (DAG: A2→A3→A4, A2→A5, A1 independiente/deployable_solo, todos→A6)

## Contexto

Versión 1.0 completa para validación de Andrea/equipo: (1) Maestro Tipos de
Actividad en `/actividades/tipos/` — CRUD completo (crear/editar/inactivar)
sobre el modelo `TipoActividad` ya existente, exponiéndolo a usuarios (no solo
admin de Django), con filtro de inactivos en todos los dropdowns que consumen
`TipoActividad`. (2) Maestro Colaboradores en `/cuadrillas/colaboradores/` —
CRUD completo sobre `PersonalCuadrilla` extendido con campos nuevos
(`salario_base`, `fecha_ingreso`, `fecha_salida`) y migración; `documento`
como clave única ya existe, se agrega validación de unicidad amigable en UI.
(3) Refactor del flujo de asignación a cuadrilla (`CuadrillaMiembroAddView` /
`templates/cuadrillas/detalle.html`): input de documento con autocompletado
AJAX de nombre/cargo/rol desde `PersonalCuadrilla` (reusa
`PersonalCuadrillaAPIView` ya existente), cargo no editable en el formulario
de asignación, y el picklist de colaboradores disponibles filtrado a
`activo=True` de `PersonalCuadrilla`. (4) Importer de colaboradores desde
archivo — nuevo (no existe hoy uno específico para `PersonalCuadrilla` con
los campos nuevos); listo para recibir el listado de Alcides vía Andrea, no
bloquea el resto del scope.

**Hallazgo de código (corrige la hipótesis inicial de F1):** `CuadrillaMiembro`
ya tiene un campo `cargo` (`CargoJerarquico`: `JT_CTA`/`MIEMBRO`) separado de
`rol_cuadrilla`. Lo que el issue llama "Cargo" (Ayudante/Conductor/Técnico...)
mapea a `PersonalCuadrilla.rol_cuadrilla` (se expone en UI con label "Cargo");
lo que el issue llama "Rol en cuadrilla" (Jefe/Miembro) mapea al `cargo`
jerárquico que hoy vive en `CuadrillaMiembro`, no en `PersonalCuadrilla`. No
hace falta crear un campo `cargo` nuevo en `PersonalCuadrilla` — el maestro de
Colaboradores expone `rol_cuadrilla` bajo el label "Cargo" que pide el issue.

**Decisión de diseño (A4, resuelta con evidencia, no bloqueante):**
`PersonalCuadrilla.documento` es `unique=True`; `Usuario.documento` NO lo es.
`CuadrillaMiembro.usuario` se **mantiene** como FK a `usuarios.Usuario` (no se
toca el modelo de datos) porque otros flujos ya dependen de él
(`TrackingUbicacion.usuario`, fotos, reportes, exportes Excel vía
`usuario.get_full_name()`). El picker de asignación cambia de *origen de
datos* (hoy: `Usuario.cargo/documento/salario_mensual` embebidos en cada
`<option>`) a *AJAX contra PersonalCuadrilla por documento*; al hacer submit,
el backend resuelve/crea el `Usuario` correspondiente por nombre+documento
(mismo patrón de match-por-nombre que ya usa `CuadrillaMiembroUploadView` para
altas masivas desde Excel). Este es el sub-item de mayor riesgo del plan
(`A4`, `complexity_class: high`).

## Sub-items por sprint

### Sprint A (deployable_solo: true para A1; el resto compone la v1.0 completa)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | CRUD Tipos de Actividad en `/actividades/tipos/` (list/create/edit/inactivar) + filtro de inactivos en dropdowns que consumen `TipoActividad` | `apps/actividades/views.py`, `apps/actividades/urls.py`, `apps/actividades/forms.py` (nuevo), `templates/actividades/tipos_lista.html` (nuevo), `templates/actividades/tipos_form.html` (nuevo) | `apps/actividades/tests_issue_176.py`: crear, editar, inactivar, tipo inactivo no aparece en dropdown de creación de actividad, código duplicado rechazado | - | medium | ⏳ pendiente |
| A2 | Migración `PersonalCuadrilla`: agregar `salario_base` (Decimal), `fecha_ingreso` (Date), `fecha_salida` (Date, null/blank) + `save()`/signal que fija `activo=False` cuando `fecha_salida` se registra | `apps/cuadrillas/models_base.py`, `apps/cuadrillas/migrations/00XX_personalcuadrilla_campos_nuevos.py` | `apps/cuadrillas/tests_issue_176.py`: migración aplica, registrar `fecha_salida` inactiva automáticamente | - | low | ⏳ pendiente |
| A3 | CRUD Colaboradores en `/cuadrillas/colaboradores/` (list/create/edit/inactivar) sobre `PersonalCuadrilla` extendido, validación de unicidad de `documento` en UI con mensaje claro | `apps/cuadrillas/views.py`, `apps/cuadrillas/urls.py`, `apps/cuadrillas/forms_personal.py` (nuevo — NO reusar `forms_pc.py`, que es de `ProgramacionSemanalCuadrilla`, otro submódulo), `templates/cuadrillas/colaboradores_lista.html` (nuevo), `templates/cuadrillas/colaboradores_form.html` (nuevo) | `apps/cuadrillas/tests_issue_176.py`: crear, editar, documento duplicado rechazado con mensaje de dominio, inactivar vía `fecha_salida`, colaborador inactivo no aparece en listas de asignación | A2 | medium | ⏳ pendiente |
| A4 | Refactor asignación a cuadrilla: input de documento + autocompletado AJAX desde `PersonalCuadrilla` (reusa `PersonalCuadrillaAPIView` existente en `apps/cuadrillas/views.py:1207`), cargo (`rol_cuadrilla`) no editable en el form de asignación, picklist filtrado a `PersonalCuadrilla.activo=True`, resolución/creación de `Usuario` por documento al submit (mismo patrón match-por-nombre de `CuadrillaMiembroUploadView`) | `apps/cuadrillas/views.py` (`CuadrillaMiembroAddView`, `CuadrillaDetailView.get_context_data`), `templates/cuadrillas/detalle.html` (form de agregar miembro L218-274 + JS `autoCargarDatos()`/`actualizarCostoDia()` L608+) | `apps/cuadrillas/tests_issue_176.py`: colaborador inactivo no aparece en picklist, cargo bloqueado (POST con cargo distinto al del maestro es ignorado/rechazado), autocompletado AJAX responde nombre+cargo+rol por documento, `Usuario` se crea/reusa correctamente al asignar por primera vez | A2, A3 | high | ⏳ pendiente |
| A5 | Importer de colaboradores desde archivo (extiende patrón de `PersonalCuadrillaUploadView` en `apps/cuadrillas/views.py:1148` para soportar columnas nuevas: salario_base, fecha_ingreso, fecha_salida) | `apps/cuadrillas/views.py` (`PersonalCuadrillaUploadView`) | `apps/cuadrillas/tests_issue_176.py`: importa fila con campos nuevos, fila sin fecha_salida queda activo, documento duplicado en archivo se reporta como error sin abortar el resto | A2 | low | ⏳ pendiente |
| A6 | Comentario al cliente/Andrea con URLs + pasos de validación numerados | - | - | A1, A3, A4, A5 | trivial | ⏳ pendiente |

No hay Sprint B — el scope completo (6 sub-items, 0 `epic`, 1 `high`) cabe en
una sesión según el gate de F2 (P-11). Todo lo del issue entra a v1.0; nada se
difiere a "fase 2".

## DAG dependencias

```
A2 → A3 → A4
A2 → A5
A1 (independiente, deployable solo)
A1, A3, A4, A5 → A6 (comentario final, no código)
```

## Riesgos y mitigaciones

- **A4 (alto)**: cambia el origen de datos del picker de asignación de
  `Usuario` a `PersonalCuadrilla`, con resolución/creación de `Usuario` al
  submit. Riesgo: colaboradores en `PersonalCuadrilla` sin `Usuario`
  correspondiente (caso común — `PersonalCuadrilla` es hoy un catálogo suelto,
  poco usado en el flujo real). Mitigación: `get_or_create` por documento +
  nombre, con `is_active=False` y sin password utilizable (no debe poder
  loguearse) — el `Usuario` creado es solo un registro de vínculo para
  `CuadrillaMiembro.usuario`, no una cuenta operativa. Documentarlo
  explícitamente en el comentario al cliente porque cambia semántica interna
  (aunque invisible para el usuario final).
- **Datos legacy**: `CuadrillaMiembro` existentes ya asignados vía `Usuario`
  sin `PersonalCuadrilla` correspondiente siguen funcionando sin cambios (no
  se migra data histórica, solo el flujo de alta nueva cambia). Confirmar en
  smoke que la tabla de miembros existente (con datos legacy) sigue
  renderizando bien tras el cambio de template.
- **A5 no bloqueante pero incompleto sin insumo real**: el archivo de Alcides
  aún no ha llegado (issue lo declara explícito). El importer se construye y
  testea con fixtures propias; la carga real de datos del cliente queda fuera
  de este RUN y se ejecuta cuando el archivo llegue (no es parte del DoD de
  v1.0 de este plan, es un paso operativo posterior).
- **Costos por rol hardcodeados**: `CostoRolAPIView` (L1246) tiene un dict
  `costos` hardcodeado por `rol_cuadrilla` que hoy es independiente del
  `salario_base` nuevo en `PersonalCuadrilla`. El issue no pide unificar esto
  (dice "el salario base permite... calcular costo... en reportes de cuadrilla
  semanal", no dice reemplazar `CostoRolAPIView`). Fuera de scope explícito de
  v1.0 — no tocar `CostoRolAPIView` en este plan; dejar nota en el comentario
  al cliente de que es una oportunidad de unificación futura, no un pendiente
  de esta feature.

## Validación esperada (qa_claude smoke maestros)

- `/actividades/tipos/` — login qa_claude, crear tipo, editarlo, inactivarlo,
  confirmar que no aparece en el dropdown de `/actividades/crear/`.
- `/cuadrillas/colaboradores/` — crear colaborador con documento nuevo,
  intentar duplicar documento (rechazo con mensaje), editar salario/fechas,
  registrar `fecha_salida` y confirmar que pasa a inactivo.
- Flujo de asignación (`/cuadrillas/<uuid>/` detalle, form de agregar
  miembro) — ingresar documento de un colaborador activo, confirmar
  autocompletado de nombre/cargo/rol, confirmar que el campo cargo no es
  editable, confirmar que colaboradores inactivos no aparecen en el picklist,
  completar el submit y verificar que el miembro queda agregado a la
  cuadrilla con el cargo correcto.
- Legacy: abrir una cuadrilla con miembros ya asignados antes del cambio y
  confirmar que la tabla de miembros sigue renderizando sin errores.
