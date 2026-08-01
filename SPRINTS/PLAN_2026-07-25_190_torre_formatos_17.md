# PLAN — Torre: 17 formatos únicos por torre + pestaña "Torre" (issue #190)

**Fecha:** 2026-07-25
**Issue:** [Indunnova16/Instelec#190](https://github.com/Indunnova16/Instelec/issues/190)
**Estado:** Planning completado, listo para ejecución
**Reproceso:** bounce=1, categoría FIX_INCOMPLETO (ver `reproceso_Instelec_190.json` del RUN)

## Contexto

El fix anterior (`4715f85`, cerrado 🟢 2026-07-24) sincronizó solo 4 de 17
formatos técnicos (FT) "únicos por torre" entre las 4 patas (A/B/C/D), y no
tocó la UI. Indunnova reabrió (2026-07-25, validado en vivo por Andrea contra
QA#49 Puerta de Oro) pidiendo la versión completa:

1. Sincronizar los **17** campos FT reales entre las 4 patas (no 4).
2. Sacarlos **completamente** de los 4 forms/templates de sección de Pata
   (Excavación, Acero, Vaciado, Compactación).
3. Crear una pestaña nueva **"Torre"** en el menú lateral, **antes de "Patas"**,
   que agrupe los 17 campos por sección (Cerramiento/Acero/Vaciado/
   Compactación, según el AGRUPAMIENTO LITERAL del cliente en el reopen — ver
   advertencia de etiquetas abajo) y sea el **único lugar editable**.

## ⚠️ Advertencia — dos "Cerramiento" y desalineamiento de etiqueta (evita bounce 2)

El modelo `ObraCivilTorreDetalle` ya tiene una sección **"Cerramiento" real**
(`cerr_madera_un`, `cerr_lona_m`, `cerr_senalizacion_ok`, `cerr_notas`,
`cerr_finalizado_ok`) que **NO tiene ningún campo FT y NO se toca en este
issue**. La etiqueta "Cerramiento" que pide el cliente para agrupar los 11
campos `exc_ft0XX_ok` en la pestaña Torre es una **etiqueta de agrupamiento
visual nueva, distinta de esa sección del modelo** — no renombrar ni fusionar
con la sección Cerramiento existente.

Además, el agrupamiento del cliente en el reopen **no respeta el prefijo de
campo del modelo**:

| Campo (modelo) | Sección del modelo | Etiqueta pedida en Torre (reopen) |
|---|---|---|
| `exc_ft022/023/058/922/923/924/925/926/927/928/929_ok` (11) | Excavación | **Cerramiento** |
| `ace_ft028_ok` (1) | Acero | Acero |
| `ace_ft930_ok` (1) | **Acero** | **Vaciado** |
| `vac_ft916_ok`, `vac_it380_ok` (2) | Vaciado | Vaciado |
| `vac_ft056_ok` (1) | **Vaciado** | **Compactación** |
| `com_ft914_ok` (1) | Compactación | Compactación |

F3 debe seguir literalmente el agrupamiento de la tabla de la derecha en la
pestaña Torre — es solo un rótulo visual, no cambia el campo/dato.

## Sub-items (Sprint A — único sprint, deploya TODO junto)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Extender `CAMPOS_SYNC_TORRE` de 4 a 17 campos (signal defensivo/idempotencia) | `apps/construccion/signals_b3_oc_detalle.py` | Extender `tests_issue_190_sync_formatos_torre.py` (propagación de los 13 campos nuevos) | - | low | ⏳ pendiente |
| A2 | Nueva vista+form+URL "Torre" (backend): `OCTorreFormatosForm` (17 campos) + `ObraCivilTorreFormatosView` (GET) + `ObraCivilTorreFormatosGuardarView` (POST AJAX) — persiste vía `save()` de UNA pata canónica (ej. pata A), reutilizando el signal de A1 para propagar a B/C/D (NO reinventar un `update()` manual paralelo) | `apps/construccion/forms_b3_oc_detalle.py`, `apps/construccion/views_b3_oc_detalle.py`, `apps/construccion/urls_b3_oc_detalle.py` | GET renderiza form con 17 campos; POST persiste + dispara signal + JSON `{ok}` | A1 | medium | ⏳ pendiente |
| A3 | Nuevo template `obra_civil_torre_formatos.html` (4 sub-secciones por la etiqueta del cliente, ver tabla de arriba) + entrada de menú lateral **"Torre"**, ANTES del bloque "Patas", en `obra_civil_detalle.html` (reusa `_tabs_navegacion.html` con una lista de 1 ítem — NO modificar ese partial compartido con Montaje/Tendido) | `templates/construccion/obra_civil_torre_formatos.html` (nuevo), `templates/construccion/obra_civil_detalle.html` | Cubierto por journey UI-nueva (`ui_nueva_reconciliar`) | A2 | medium | ⏳ pendiente |
| A4 | Remover los 17 campos de los 4 forms **y** de los 4 templates de sección de Pata (deben ir acoplados — dejar el campo en el template sin estar en el Form deja un `{{ form.campo }}` huérfano) | `apps/construccion/forms_b3_oc_detalle.py` (4 clases), `templates/construccion/partials/oc_seccion_{excavacion,acero,vaciado,compactacion}.html` | Actualizar/retirar 2 tests existentes que se ROMPEN con este cambio (ver abajo) + tests nuevos que confirmen ausencia | A3 | medium | ⏳ pendiente |
| A5 | Backfill BD: migración nueva que reconcilia los 13 campos nuevos con la misma política "gana True" de `0048_sync_formatos_torre_backfill.py` (evidencia real ya recogida en BD prod — ver abajo) | `apps/construccion/migrations/0049_sync_17_formatos_torre_backfill.py` (nueva, sucesora de 0048, NO la reemplaza) | Test de la migración (`RunPython`) sobre fixture con divergencia (espejo de los tests de 0048) | A1 | low | ⏳ pendiente |
| A6 | Tests: cobertura completa (signal 17 campos, vista Torre GET/POST, ausencia en Patas) + arreglar las 2 regresiones que este cambio rompe | `apps/construccion/tests_issue_190_sync_formatos_torre.py`, `apps/construccion/tests_b3_oc_detalle_modelo.py`, `apps/construccion/tests_b3_oc_detalle_views.py` | (es el propio sub-item) | A1,A2,A3,A4,A5 | high | ⏳ pendiente |

### ⚠️ Regresiones conocidas que A4/A6 DEBEN arreglar (no son hipotéticas — ya existen en el repo)

1. `tests_b3_oc_detalle_modelo.py::test_oc_seccion_excavacion_form_expone_ft_023_058_922`
   (línea ~656) — assertea que `exc_ft023_ok`/`058`/`922` SIGUEN en
   `OCSeccionExcavacionForm.Meta.fields` y los guarda vía POST simulado. Con
   A4 aplicado, este test FALLA (`AssertionError`, el campo ya no está en
   `Meta.fields`). Reescribir para reflejar el nuevo contrato: esos campos
   viven en `OCTorreFormatosForm`, NO en `OCSeccionExcavacionForm`.
2. `tests_b3_oc_detalle_views.py::test_post_excavacion_metros_m3_persiste`
   (línea ~178) — el POST incluye `'exc_ft022_ok': 'on'` y luego assertea
   `det.exc_ft022_ok is True`. Con A4 aplicado, Django ignora el campo extra
   en el POST (no está en el form) → la aserción falla (queda en `False`,
   default). Quitar esa línea del POST y esa aserción del test (el resto del
   test — `exc_metros_m3`/`exc_ejecutada_pct`/`exc_cuadrilla` — sigue válido).

## Hot-file compartido con Instelec#191 (mismo RUN, paralelo)

`templates/construccion/partials/oc_seccion_acero.html` y
`apps/construccion/forms_b3_oc_detalle.py` (`OCSeccionAceroForm`) los toca
TAMBIÉN Instelec#191 (JS reactivo de recálculo de desviación de Acero,
líneas ~20-53 del template — inputs `ace_solicitado_kg`/`ace_instalado_kg` y
los spans `data-desv`/`data-desv-pct`). #190 solo toca las líneas 13-14
(`ace_ft028_ok`/`ace_ft930_ok`) — **zonas distintas del mismo archivo pero
riesgo real de conflicto de merge si F3 de ambos issues edita en paralelo**.
Recomendado: serializar el F3 de #190 y #191 sobre ese archivo (uno rebasa
sobre el otro), no mergear a ciegas. Ídem para `forms_b3_oc_detalle.py`: #191
declaró explícitamente "no tocar backend" — el riesgo de colisión real está
solo en el template.

## Enumeración de sitios (paso 3.5, obligatorio — `complexity_class: epic` a
nivel de issue + `riesgo_global: alto`)

Grep dirigido de los 17 símbolos FT contra los `archivos_a_tocar` de A4 —
CADA sitio va en `sitios_checklist[]` del JSON de salida (F3 debe marcar
`tocado` o `revisado-intacto: <justificación>` por cada uno; `closeout.py`
hace HARD-BLOCK si queda alguno sin resolver):

- `templates/construccion/partials/oc_seccion_excavacion.html` líneas 38-48
  (11 campos: `exc_ft022/023/058/922/929/923/924/925/926/927/928_ok`)
- `templates/construccion/partials/oc_seccion_acero.html` líneas 13-14
  (`ace_ft028_ok`, `ace_ft930_ok`)
- `templates/construccion/partials/oc_seccion_vaciado.html` líneas 17, 21, 22
  (`vac_ft916_ok`, `vac_it380_ok`, `vac_ft056_ok`)
- `templates/construccion/partials/oc_seccion_compactacion.html` línea 12
  (`com_ft914_ok`)
- `apps/construccion/forms_b3_oc_detalle.py` líneas 90-92
  (`OCSeccionExcavacionForm.Meta.fields`, 11 campos)
- `apps/construccion/forms_b3_oc_detalle.py` línea 165
  (`OCSeccionAceroForm.Meta.fields`, 2 campos)
- `apps/construccion/forms_b3_oc_detalle.py` líneas 198-199
  (`OCSeccionVaciadoForm.Meta.fields`, 3 campos)
- `apps/construccion/forms_b3_oc_detalle.py` línea 255
  (`OCSeccionCompactacionForm.Meta.fields`, 1 campo)

Grep global de control (confirmado, sin sitios adicionales fuera de
templates/forms/signals/models/migraciones estructurales — sin admin.py,
sin serializers, sin API ninja, sin exports):
```
grep -rln -E "exc_ft0(22|23|58)_ok|exc_ft9(22|23|24|25|26|27|28|29)_ok|ace_ft028_ok|ace_ft930_ok|vac_ft916_ok|vac_it380_ok|vac_ft056_ok|com_ft914_ok" \
  --include="*.py" --include="*.html" --include="*.js" .
```

## DAG dependencias

```
A1 → A2 → A3 → A4 → A6
A1 → A5 → A6
```

## Evidencia BD prod ya recogida (F2, proxy 127.0.0.1:5434, instelec_db)

- Solo existe **1 proyecto real** con datos: `QA test #49 — Puerta de Oro`
  (`ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`, 65 torres con detalle). No hay
  otros proyectos que dimensionar para el backfill.
- **17 torres** de ese proyecto tienen divergencia real HOY entre patas en
  los 13 campos FT nuevos (hasta 8 campos divergentes en una misma torre).
  Ejemplo real usado para journey/tests: **Torre E63**
  (`9d208805-8d98-4b8d-94b6-db3e747e8e8a`) — pata D tiene
  `exc_ft022/923/924/925/926/927/928/929_ok = False` mientras A/B/C = `True`
  (8 campos divergentes en 1 torre).

## Riesgos y mitigaciones

- **Hot-file con #191** (ver sección arriba) → serializar F3, no merge ciego.
- **Confusión de etiqueta "Cerramiento"** (sección real del modelo vs.
  agrupamiento visual nuevo) → advertencia explícita arriba, F3 debe releer
  antes de nombrar variables/templates.
- **Regresión de 2 tests existentes** (ver tabla) → listados explícitamente,
  no son opcionales de arreglar.
- **UI completamente nueva** (el template Torre no existe hoy) → protocolo
  `ui_nueva_reconciliar` aplicado al journey (asserts laxos por texto,
  marcados `# RECONCILIAR_DOM`, ver `journeys/Instelec_190.yaml`).

## Validación esperada (smoke E2E / qa_claude)

- Pestaña "Torre" visible en el menú lateral, ANTES de "Patas", para
  cualquier torre de QA#49.
- Los 17 campos FT visibles y editables SOLO en la pestaña Torre, agrupados
  por sección según la tabla de etiquetas de arriba.
- Al editar un campo en Torre y guardar, las 4 patas quedan sincronizadas
  (validado con `ace_ft930_ok` en torre E63, campo NO cubierto por el signal
  anterior).
- Los 17 campos YA NO aparecen en ninguno de los 4 forms/templates de
  sección de Pata (Excavación/Acero/Vaciado/Compactación).
- Post-deploy (migración `0049_...`), torre E63 pata D queda con los 8
  campos que estaban en `False` reconciliados a `True` (política "gana
  True", igual que 0048).
- Capturas de pantalla de la pestaña Torre nueva contra QA#49 adjuntas al
  comentario de cierre.
