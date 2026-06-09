# PLAN — Clase de cimentación independiente en Excavación OOCC (issues #135 + #134)

**Fecha:** 2026-06-09
**Issue:** [Indunnova16/instelec#135](https://github.com/Indunnova16/instelec/issues/135) — ABSORBE [#134](https://github.com/Indunnova16/instelec/issues/134)
**Estado:** Planning completado, listo para ejecución
**Decisión de scope (Miguel):** este sprint resuelve ambos issues. #134 ("tipo de
excavación claro = Manual / Con máquina") se cierra al limpiar `EXC_TIPO_CHOICES`;
#135 (clase de cimentación) se resuelve con el campo nuevo `exc_clase_cimentacion`.

## Contexto

Hoy `EXC_TIPO_CHOICES` mezcla dos conceptos distintos en el mismo campo
`exc_tipo` (`ObraCivilTorreDetalle`, tabla `construccion_oc_detalle`):

- **Tipo de excavación** (método): MANUAL / MAQUINA  ← lo que pide #134
- **Clase de cimentación** (fundación): HELICOIDAL  ← lo que pide #135

`HELICOIDAL` es una clase de cimentación, NO un método de excavación. El plan
separa ambos conceptos:

1. Campo nuevo `exc_clase_cimentacion` con choices HELICOIDAL / ZAPATA /
   PARRILLA / PARRILLA_PESADA (independiente, blank permitido).
2. `EXC_TIPO_CHOICES` queda limpio: solo MANUAL / MAQUINA.
3. **Migración de DATOS legacy**: filas con `exc_tipo='HELICOIDAL'` →
   `exc_tipo=''` + `exc_clase_cimentacion='HELICOIDAL'` (no perder el dato).
4. UI: render de ambos selects en el partial de excavación (create + update).

### Evidencia inspeccionada (literal)
- `apps/construccion/models_b3_oc_detalle.py:33-37` — `EXC_TIPO_CHOICES` con HELICOIDAL.
- `:122-124` — `exc_tipo = CharField('Tipo excavación', max_length=20, choices=EXC_TIPO_CHOICES, blank=True)`.
- `:376-377` — `db_table = 'construccion_oc_detalle'`.
- `forms_b3_oc_detalle.py:83-98` — `OCSeccionExcavacionForm.Meta.fields` (incluye `exc_tipo`).
- `templates/construccion/partials/oc_seccion_excavacion.html:19-25` — render `exc_tipo` (grid 2 col).
- `views_b3_oc_detalle.py:290-340` — `ObraCivilDetalleSeccionView.post(proyecto_id, torre_id, pata, seccion)`:
  `get_or_create(torre, pata)` + `form.save()`, devuelve JSON `{ok:true,...}`.
  Endpoint (name `obra_civil_detalle_seccion`):
  `/<proyecto_id>/obra-civil/<torre_id>/detalle/<pata>/<seccion>/` (slug `excavacion`).
- Forms usan widget Django por defecto (no Select estilizado custom) → render `<select>` plano.

### Riesgo de datos
La conexión BD prod no estuvo disponible en planning (IP directa timeout, proxy
:5434 down). **F3 DEBE** correr `SELECT exc_tipo, count(*) FROM construccion_oc_detalle
GROUP BY exc_tipo;` vía proxy (`cloud-sql-proxy --port 5434`) ANTES de escribir la
data-migration, para confirmar cuántas filas HELICOIDAL existen. La migración debe
ser data-safe aunque haya 0 filas (idempotente, reverse incluido).

## Sub-items (Sprint A — único sprint, v1.0 completa, deployable en bundle)

| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|---|---|---|---|---|
| A1 | Modelo: agregar `EXC_CLASE_CIMENTACION_CHOICES` (HELICOIDAL/ZAPATA/PARRILLA/PARRILLA_PESADA) y campo `exc_clase_cimentacion = CharField('Clase de cimentación', max_length=20, choices=..., blank=True)`; limpiar `EXC_TIPO_CHOICES` a solo MANUAL/MAQUINA | `models_b3_oc_detalle.py` | choices correctos, blank OK, label correcto | - | ⏳ |
| A2 | Form: agregar `exc_clase_cimentacion` a `OCSeccionExcavacionForm.Meta.fields` (después de `exc_tipo`) | `forms_b3_oc_detalle.py` | form acepta valor válido, rechaza choice inválido | A1 | ⏳ |
| A3 | Migration schema: `AddField exc_clase_cimentacion` + `AlterField exc_tipo` (choices nuevo) | `migrations/0024_*` | `makemigrations --check` limpio | A1 | ⏳ |
| A4 | Migration de DATOS (misma 0024 o 0025): `RunPython` forward = filas `exc_tipo='HELICOIDAL'` → set `exc_clase_cimentacion='HELICOIDAL'`, `exc_tipo=''`; reverse = inverso. Idempotente, data-safe con 0 filas | `migrations/0024_*` (o `0025_*`) | test migra fila legacy HELICOIDAL correctamente | A3 | ⏳ |
| A5 | Template: render `exc_clase_cimentacion` como `<select>` junto a `exc_tipo` (mismo grid 2-col, label + errors) | `partials/oc_seccion_excavacion.html` | render contiene `name="exc_clase_cimentacion"` y las 4 opciones | A2 | ⏳ |
| A6 | Tests unitarios: (a) save con tipo=MANUAL + clase=ZAPATA persiste ambos; (b) HELICOIDAL ya NO es choice de exc_tipo (rechazado); (c) data-migration sobre fila legacy; (d) update_or_create vía POST view setea ambos campos | `tests_b3_oc_detalle_modelo.py` (+ test view si aplica) | happy + ≥2 edge | A2,A4,A5 | ⏳ |
| A7 | Smoke E2E autenticado (journey YAML, ver abajo): registrar excavación con tipo Manual/Máquina + seleccionar clase de cimentación, persistir, recargar, validar | `$RUN_DIR/journeys/instelec_135.yaml` | journey verde, reproduces el escenario cliente | A5 | ⏳ |
| A8 | Comentario cliente: URL exacta de detalle OOCC + pasos numerados para validar ambos campos | (comentario GH, F6) | - | A7 | ⏳ |

## DAG dependencias
```
A1 → A2 → A5 → A6
A1 → A3 → A4 → A6
A6 → A7 → A8
```
Todo es UN bundle deployable (toca el mismo modelo/form/template/migration) →
`primer_sub_conjunto_deployable = [A1..A8]` (no se parte; deploy único).

## Riesgos y mitigaciones
- **Pérdida de dato legacy HELICOIDAL** → data-migration `RunPython` con reverse;
  F3 verifica conteo en prod ANTES de escribirla. CRÍTICO (instrucción Miguel).
- **AlterField exc_tipo rompe filas existentes** con valor HELICOIDAL si la
  data-migration no corre PRIMERO → ordenar operaciones: `AddField` + `RunPython`
  (mover dato) ANTES de cualquier validación de choice; `AlterField` solo cambia
  metadata (Django no valida choices a nivel DB) así que el orden seguro es
  AddField → AlterField → RunPython (RunPython al final mueve el dato). Confirmar
  que ninguna constraint DB bloquee.
- **Migration conflict (multiple leaf)** → última es `0023_*`; pre-asignar `0024`.
  Correr `makemigrations --check` dentro del job migrate (hermético).
- **es-CO / Alpine inline** → los selects son Django widgets simples, sin floats ni
  JSON en x-data; bajo riesgo. Aun así el journey valida el render real.
- **Deploy no promueve tráfico** (gotcha portafolio) → vía `/multiagente`, F5
  promueve `--to-latest` y smokea contra la revisión promovida.

## Validación esperada (qa_claude smoke + journey)
- Journey `i135_a7_excavacion_clase_cimentacion` (mutativo) en
  `$RUN_DIR/journeys/instelec_135.yaml`:
  POST a `obra_civil_detalle_seccion` (slug `excavacion`) con
  `exc_tipo=MANUAL` + `exc_clase_cimentacion=ZAPATA`; verificar JSON `ok:true`;
  recargar detalle y assertear que el `<select>` clase muestra ZAPATA seleccionado.
- Smoke crawl: lista OOCC + detalle torre + sección excavación → HTTP 200.
- Validar ≥1 registro legacy (torre/pata que ya existía) además de la fixture.
