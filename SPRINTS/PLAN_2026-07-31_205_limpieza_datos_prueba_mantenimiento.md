# Issue #205 — Borrar datos de prueba en Mantenimiento (excepto vanos)

## F1 — Triage

**Clasificación: DATA-FIX sobre BD prod, NO un bug de código.** El propio
issue lo etiqueta "requiere acceso a base de datos". No hay flag
`es_prueba`/`is_test` en ningún modelo tocado (`BaseModel` solo trae
`id`/`created_at`/`updated_at`) — la identificación de "qué es prueba" es
por **alcance de tabla**, no por columna.

Dado que toca 2 apps + 5+ tablas, con una excepción explícita (vanos) y un
riesgo real de colisión con datos de Construcción (ver abajo), se
construyó un **management command** en vez de un DELETE manual — es
justo el caso "requiere script repetible y seguro", no "3 filas a mano".

## Comando

`apps/core/management/commands/limpiar_datos_prueba_mantenimiento.py`
(+ tests en `apps/core/tests_issue_205_limpiar_datos_prueba.py`, 12 tests,
todos verdes contra Postgres local).

- **Sin flags → dry-run**: solo reporta conteos, no escribe nada.
- **`--commit`**: ejecuta los DELETE/UPDATE dentro de una transacción.

### Tablas 100% exclusivas de Mantenimiento (se borran completas)
`actividades.Actividad`, `ProgramacionMensual`, `HistorialIntervencion`,
`InformeDiario`. Verificado en código: dependen de `lineas.Linea/Torre`,
que Construcción no usa (tiene su propio árbol `ProyectoConstruccion` /
`TorreConstruccion`). No hay overlap posible.

### Cuadrilla / Asistencia — riesgo real detectado
`cuadrillas.Cuadrilla` también se referencia (solo lectura, por **nombre**,
no FK) desde el filtrado legacy de operarios de Construcción
(`apps.construccion.views.filtrar_torres_por_cuadrilla` /
`views_b3_mont_detalle`), que matchea contra los campos de texto libre
`TorreConstruccion.cuadrilla_civil/montaje/tendido` y los mismos campos en
`PataObra`/`FaseTorre`. El comando cruza `Cuadrilla.nombre` contra esos
campos ANTES de borrar y **excluye del `--commit`** cualquier coincidencia
(la reporta como riesgo en vez de tocarla). Cubierto por 4 tests
(`TestCommitCuadrillaConRiesgoDeColision`).

### Colaboradores (`PersonalCuadrilla`) — pedido explícito del comentario
- DELETE solo `activo=False`.
- UPDATE (no delete) de los activos: `area='' → 'MANTENIMIENTO'`, sin
  pisar ningún valor ya asignado (ej. si algún colaborador ya quedó en
  `CONSTRUCCION`).
- El reporte imprime el total de activos para que quien corra `--commit`
  confirme que coincide con los "61 colaboradores" que menciona el issue
  ANTES de ejecutar — si no coincide, detenerse y avisar.

### Nunca tocado
`lineas.Vano`, `lineas.VanoSemestre`, `lineas.Linea`, `lineas.Torre` — ni
se importan en el comando.

## Bloqueo — no verificado contra prod real

Esta sesión no tiene escritura a BD prod (`--no-deploy`) y, además, el
proxy/red de Cloud SQL (`130.211.117.166:5432`, DB `instelec_db`) **no fue
alcanzable desde este entorno** (puerto cerrado / IP no autorizada para
este sandbox). Por lo tanto:

- El comando fue probado con datos sintéticos (factories) contra Postgres
  local — la lógica está verificada, pero **los conteos reales de prod
  (cuántas Actividad/Cuadrilla/PersonalCuadrilla hay hoy, si el conteo de
  colaboradores activos da 61, si el chequeo de riesgo da 0 coincidencias)
  no se confirmaron.**

## Próximo paso (F2 en adelante, sesión con acceso a prod)

1. Con proxy Cloud SQL activo: `python manage.py limpiar_datos_prueba_mantenimiento`
   (dry-run) contra prod, leer el reporte.
2. Confirmar: conteo de colaboradores activos = 61 (o entender la
   diferencia), sección de riesgo de Cuadrilla = 0 coincidencias.
3. Si todo cuadra → `--commit`. Si no → escalar a Miguel/Andrea antes de
   tocar nada (el comando no adivina, solo reporta).
4. Deploy del comando (no requiere migración, es código nuevo) vía el
   flujo normal antes de poder correrlo en prod.

## Worktree

`~/Desktop/Repos/Instelec_wt_205`, branch `chore/instelec-205-limpieza-datos-prueba`
(desde `origin/main`). Sin commit todavía — cambios en working tree del
worktree, no en el checkout principal (que tiene trabajo sucio de otra
sesión activa, issue #201, no tocado).
