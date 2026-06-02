# Plan — Issue #124: Carga masiva de cuadrillas desde Excel "Programación S18" con encargados

Fecha: 2026-06-02 · Repo: Indunnova16/Instelec

## Causa raíz / gap
El formato actual de carga de cuadrillas (#105, `CuadrillaImporter`, ruta
`/cuadrillas/b4/upload-cuadrillas/`) espera **una columna CUADRILLA con código**.
El cliente usa el archivo real **"Programación - S18.xlsx"** que NO tiene código:
las filas están **agrupadas por actividad** (`#` numérico = encabezado + 1er
miembro; `#` vacío = miembros siguientes), el encargado se marca con
**ROL = "JT/CTA"**, y el cargo viene en la columna **CARGO** (Liniero I/II...).

## Grounding (verificado contra prod `instelec_db`)
- Modelos ya tienen lo necesario: `CuadrillaMiembro.CargoJerarquico` (JT_CTA/MIEMBRO)
  y `RolCuadrilla` (12 roles). **Sin migraciones.**
- `motivo_desactivacion` NOT NULL default `''` (mig 0011) → ORM `create()` directo.
- `ProgramacionSemanalImporter` (apps/actividades) ya parsea S18 → reuso su lógica
  de detección de hoja/encabezado/agrupación (re-implementada local para desacoplar).
- LINEA del S18 (`809`, `817/818`) resuelve a `LN809`/`LN817` vía `codigo__icontains`.
- Datos prod para test legacy: 40 líneas, 70 usuarios, 2 cuadrillas, **0 miembros**,
  10 vehículos. Cédula `72019461` NO existe → caso natural de advertencia.

## Cambios (additive, sin tocar la vista legacy frágil)
1. `apps/cuadrillas/importers.py`
   - `ProgramacionS18CuadrillaImporter`: recorre hojas semanales, agrupa por
     actividad, genera código `WW-YYYY-NNNN-AAA`, crea Cuadrilla + miembros,
     marca JT_CTA por ROL, mapea CARGO→RolCuadrilla, asigna vehículo por PLACA
     (fila del conductor), línea no hallada = advertencia (NO fatal, spec #124).
   - `detectar_formato_cuadrillas(archivo)` → 'S18' | 'AVISO_SAP'.
2. `apps/cuadrillas/views_b4.py`
   - `CuadrillaUploadView`: auto-detecta formato y enruta al importer correcto;
     reporta `formato_detectado`. Checkbox `crear_usuarios_faltantes` (default OFF).
   - `DescargarPlantillaProgramacionS18View` (+ URL `b4/descargar-plantilla-s18/`).
3. `templates/cuadrillas/cuadrilla_upload.html`
   - Muestra formato detectado + encargados asignados; soporta ambos formatos;
     link a plantilla S18; checkbox crear usuarios.
4. `apps/cuadrillas/tests_s18.py`
   - Fixture real `tests/fixtures/Programacion_S18_real.xlsx` (dato legacy) + edges:
     JT_CTA correcto, código generado, cédula inexistente (warning), línea fuzzy,
     re-run idempotente, formato mal detectado.

## Reglas de negocio aplicadas
- Encargado = ROL contiene JT/CTA/JEFE/ENCARGADO → CargoJerarquico.JT_CTA.
- Código: `{semana:02d}-{anio}-{numero:04d}-{INI3}` (≤20 chars).
- Línea no existe → advertencia + linea None (no aborta).
- Cédula no existe → advertencia + miembro omitido (o crear usuario si opt-in).
- Transacción atómica por archivo.

## Smoke / validación
- Tests Django (legacy fixture obligatorio).
- Deploy Cloud Run + `/qa-prod Instelec` journey S18 (subir fixture real, verificar
  cuadrillas + encargado en `/cuadrillas/`), cleanup psql.
