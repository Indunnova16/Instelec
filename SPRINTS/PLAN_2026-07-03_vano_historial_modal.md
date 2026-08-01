# Plan #177 — Modal de cambio de estado con historial/trazabilidad (Avances de Vanos)

Rebote (bounce=1). Reemplaza por completo el mecanismo del "Ajuste 1" (dropdown +
nota/foto sobreescribiendo el Vano) por un modal con historial append-only y reduce
el enum de estado a exactamente 6 valores. Ruta: `sprint_path` (single-módulo).

## Contexto

- **Qué reportó QA (2026-07-01):** el Ajuste 1 previo (nota/foto al cambiar estado)
  sigue sin persistir en el flujo real de navegador. Causa raíz hipotética: el único
  test existente (`apps/campo/tests_issue_177.py`) hace POST directo con el Django
  test client armando el payload a mano — nunca ejercita el DOM real donde el hidden
  `estado` se setea vía `@click` de Alpine justo antes del submit HTMX (condición de
  carrera / timing bug que un test de integración server-side jamás detecta).
- **Redefinición de scope (mismo comentario, inmediatamente después):** el dropdown
  "Cambiar estado" se reemplaza por un **modal** que, al guardar, crea un **nuevo
  registro de historial** (persona/fecha/estado/nota/foto(s)) sin sobreescribir el
  anterior. Historial completo visible. Estados válidos EXACTAMENTE 6: Ejecutado,
  Parcial, Sin Permiso, Seccionado, Especial, Pendiente (hoy hay 5, incluye "No
  Ejecutado" que debe desaparecer).
- **Precedente de reproceso anterior:** issue #101 (`PLAN_2026-06-06_issue101_vanos.md`)
  — el módulo de vanos ya tuvo una re-apertura por Sofi por un gap entre "contador"
  y "filas reales". Este historial de iteración confirma que el módulo requiere
  cuidado en migraciones de datos (no destructivas, idempotentes).

## Hallazgo de scope adicional (verificación de código, no estaba en F1)

Existen **dos modelos distintos** que comparten el mismo enum de 5 estados por
copy-paste, y **solo uno** es el de este issue:

| Modelo | App | Usado por | ¿Es este issue? |
|---|---|---|---|
| `Vano` (`apps/lineas/models_base.py`) | lineas | `RegistroAvanceCreateView` / `avance_registrar.html` / `vano_cuadro.html` / `VanoEstadoUpdateView` — grilla "Avances de Vanos" con dropdown "Cambiar estado" | **SÍ** — es el mockup de att_01/03 y la planilla RESUMEN de att_02 |
| `AvanceVano` (`apps/campo/models.py`) | campo | `AvancesCuadrillaView` / `avances_cuadrilla.html` / `MarcarVanoView` — feature separada de auto-marcado por cuadrilla dentro de una `Actividad` | **NO** — fuera de scope, no tocar |

`AvanceVano.Estado` **NO se toca** en este issue (aunque hoy comparte los mismos 5
values que `Vano.Estado` — es deuda técnica de nomenclatura duplicada, no un
requisito del cliente). Si el cliente reporta el mismo problema en la vista de
cuadrilla, será un issue nuevo.

También confirmado (ya lo había marcado F1): `VanoSemestre.Estado`
(`apps/lineas/models_b21.py`, feature B2.1) es una tabla y feature distinta — NO
tocar.

## Hallazgo adicional — bug latente de autorización (bundle quirúrgico)

`VanoEstadoUpdateView.post` (a reemplazar) usa roles
`['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']` — **sin**
`admin_general`. `RegistroAvanceCreateView._build_context` ya tiene un comentario
explícito documentando que `admin_general` (RBAC v2, rol canónico admin de Instelec
desde #44) debe incluirse o los admins RBAC v2 (incl. `qa_claude`) caen al branch
de trabajador / reciben 403. El nuevo endpoint de historial hereda este gate — se
corrige agregando `admin_general` a la lista de roles autorizados (fix quirúrgico,
mismo archivo que ya se está tocando, cero riesgo adicional).

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| 1 | Modelo `VanoHistorialEstado` (FK Vano, usuario, fecha auto, estado, nota) — append-only | Migración aplicada en prod; `SELECT COUNT(*) FROM vanos_historial_estado` > 0 tras smoke | ⏳ |
| 2 | Sub-modelo `VanoHistorialFoto` (FK historial, imagen, 0..N) | Migración aplicada; foto subida en smoke visible vía URL GCS | ⏳ |
| 3 | `Vano.Estado` reducido a exactamente 6 choices (agrega Seccionado/Especial, quita No Ejecutado) | `Vano.Estado.choices` en shell prod = 6 valores exactos | ⏳ |
| 4 | Migración de datos: 1 vano legacy `estado='no_ejecutado'` → `pendiente` + backfill de 1er registro de historial retro-poblado por cada Vano con estado/observaciones/foto previos | `SELECT * FROM vanos WHERE estado='no_ejecutado'` = 0 filas; vano legacy tiene ≥1 fila en `vanos_historial_estado` | ⏳ |
| 5 | Modal Alpine (`_vano_estado_modal.html`) reemplaza el dropdown — abre al clic sobre la tarjeta del vano | Screenshot/E2E: clic en vano → modal visible con selector 6 estados + nota + fotos múltiples | ⏳ |
| 6 | Endpoint `VanoHistorialCreateView` — crea registro de historial (NO sobreescribe), actualiza estado "actual" denormalizado del Vano, tope 5 fotos, gate de autorización (incl. fix `admin_general`) | POST real en prod desde navegador crea fila nueva sin borrar la anterior | ⏳ |
| 7 | Endpoint `VanoHistorialListPartialView` — historial completo visible (todas las notas/fotos de todos los cambios) | GET partial en prod muestra ≥2 registros tras 2 cambios de estado consecutivos | ⏳ |
| 8 | Stats Row + donut Chart.js actualizados a 6 estados (Seccionado/Especial nuevos, No Ejecutado removido) | `avance_registrar.html` en prod: 6 tiles + donut con 6 labels, datalabels intactos | ⏳ |
| 9 | `seed_data.py` — verificado, NO requiere cambio (lee `Vano.Estado.choices` dinámicamente) | `make seed` local corre sin error con el enum nuevo | ⏳ |
| 10 | Tests happy+edge (incl. tope de fotos, permisos, append-only, enum) + journey E2E Playwright real (clic→modal→guardar→historial) vía `/multiagente` | `pytest apps/campo/tests_issue_177.py` verde; `.e2e_pass` marker post-deploy | ⏳ |

## Sub-items (Sprint A — único sprint, v1.0 atómica)

Todo pertenece al mismo deployable: el modal no tiene sentido sin el modelo de
historial detrás, y el historial no tiene UI sin el modal. `deployable_solo=false`
para todos salvo el paquete completo.

| id | Sub-item | Archivos | complexity | depende de |
|---|---|---|---|---|
| 2 | Reducir `Vano.Estado` a 6 choices | `apps/lineas/models_base.py`, migración `0014` | medium | — |
| 1 | Modelos `VanoHistorialEstado` + `VanoHistorialFoto` | `apps/lineas/models_base.py`, migración `0015` | high | — |
| 3 | Data migration: remap legacy + backfill historial | migración `0016` (RunPython) | high | 1, 2 |
| 4 | Endpoint `VanoHistorialCreateView` (crear + gate + tope fotos + fix admin_general) | `apps/campo/views.py`, `apps/campo/urls.py` | high | 1, 2, 3 |
| 5 | Endpoint `VanoHistorialListPartialView` (listar historial) | `apps/campo/views.py`, `apps/campo/urls.py`, nuevo `templates/campo/partials/_vano_historial_list.html` | medium | 1 |
| 6 | Modal Alpine `_vano_estado_modal.html` | nuevo `templates/campo/partials/_vano_estado_modal.html` | high | 4, 5 |
| 7 | Rewrite `vano_cuadro.html` (trigger modal, quita dropdown, incluye historial) | `templates/campo/partials/vano_cuadro.html` | medium | 6 |
| 8 | Stats row + donut 6 estados | `templates/campo/avance_registrar.html`, `apps/campo/views.py` (`RegistroAvanceCreateView._build_context`) | medium | 2 |
| 9 | `seed_data.py` — verificación (sin cambio de código) | `apps/core/management/commands/seed_data.py` | low | 2 |
| 10 | Reescribir `tests_issue_177.py` + journey E2E Playwright | `apps/campo/tests_issue_177.py`, journey YAML (F2, ya entregado) | high | 4, 5, 6, 7, 8 |

## DAG de dependencias

```
2 (enum 6 choices) ─┐
                     ├─→ 3 (data migration) ─→ 4 (endpoint crear) ─┐
1 (modelos historial)┘                          5 (endpoint listar)┤
                                                                     ├─→ 6 (modal) ─→ 7 (vano_cuadro.html) ─┐
2 ─────────────────────────────────────────────→ 8 (stats/donut) ──────────────────────────────────────────┤
2 ─────────────────────────────────────────────→ 9 (seed_data verify) ──────────────────────────────────────┤
                                                                                                              ├─→ 10 (tests + E2E)
```

Orden de ejecución sugerido: 2 → 1 → 3 → (4 ∥ 5) → 6 → 7; en paralelo 8 y 9 pueden
correr apenas está 2; 10 al final, tras todo lo demás.

## Gate de scope — `epic_pero_single_modulo`

F1 marcó `complexity_class=epic` (10 sub-items, varios `high`, 1 modelo nuevo +
migración de datos + UI nueva + reescritura de tests). Esto dispara el gate
"≥1 epic o ≥6 high" que normalmente amerita handoff a `/modulo`. **Decisión: NO
hacer handoff.** Justificación: es un solo módulo (Avances de Vanos, dentro de
`apps/lineas` + `apps/campo`, sin tocar otras apps del portafolio), no una épica
multi-módulo (que es el caso de uso real de `/modulo`: features que abarcan varios
dominios de negocio en paralelo con integración atómica al final). El scope es
grande en LOC pero angosto en superficie funcional — un flujo, un modelo de datos
nuevo, una migración. Se ejecuta como `sprint_path` normal dentro de `/multiagente`.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Repetir el mismo bug de timing (root cause del rebote)** | El modal usa `fetch()` + `FormData` (patrón ya probado en `_vano_semestre_modal.html`), NO el patrón HTMX-submit-con-hidden-input-seteado-por-@click que causó la condición de carrera original. Elimina la clase de bug, no solo el síntoma. Gate E2E Playwright real obligatorio (journey `Instelec_177.yaml`) contra el navegador, no solo Django test client. |
| **Migración de datos destructiva/no idempotente** | Sigue el patrón ya validado en #101 (`Linea.sincronizar_vanos`: idempotente, nunca borra). La data migration solo crea filas de historial (INSERT) y hace 1 UPDATE puntual (remap `no_ejecutado`→`pendiente` del único vano legacy, verificado por SELECT en BD prod: `ae733441-0644-4c4c-82ff-bdead95102e9`). Reversión: `RunPython.noop` (documentado como no reversible limpiamente, aceptable para este tipo de dato). |
| **Confundir `Vano` con `AvanceVano` o `VanoSemestre`** | Documentado explícitamente arriba (hallazgo de scope). `AvanceVano.Estado` NO se toca. |
| **Bug latente de autorización (`admin_general` faltante)** | Se corrige en el mismo endpoint que ya se reescribe (sub-item 4), no requiere trabajo adicional fuera de scope. |
| **Tope de fotos no confirmado por cliente** | Interpretación tomada por F1: máximo 5 fotos por registro de historial (validación server-side, trunca silenciosamente el exceso — documentar en el comentario de cierre para que el cliente confirme si necesita más). |
| **Historial visible a quién / inmutabilidad** | Interpretación F1: mismo gate de acceso que hoy (roles admin + miembro de cuadrilla de la línea); registros append-only sin edición/borrado (server no expone endpoint de update/delete). |
| **Grid/stats muestran datos inconsistentes durante el deploy** (ventana entre migración de esquema y data migration) | Ambas migraciones (`0015` esquema, `0016` data) van en el mismo deploy/release; el job `instelec-migrate` corre antes de promover tráfico (estándar del repo). |

## Validación esperada (cliente)

1. Entrar a `/campo/avance/registrar/?linea_id=14d79066-060b-4713-a642-6580105a85f7`
   (línea con el vano legacy remapeado).
2. Clic sobre cualquier vano → se abre el modal (ya no el dropdown).
3. Seleccionar un estado de los 6 (Ejecutado/Parcial/Sin Permiso/Seccionado/
   Especial/Pendiente), escribir una nota, adjuntar 1-2 fotos, guardar.
4. Verificar: el historial del vano muestra el nuevo registro (persona, fecha,
   estado, nota, foto) **y** el/los registro(s) anteriores siguen visibles (no
   se sobreescribieron).
5. Repetir el cambio de estado sobre el mismo vano una segunda vez → confirmar que
   ahora hay ≥2 (o ≥3, si había backfill legacy) registros en el historial.
6. Verificar Stats Row + donut de "Distribución de Estados": 6 categorías, sin
   "No Ejecutado", con "Seccionado" y "Especial" presentes.
7. Confirmar con el vano legacy (`ae733441-...`, hoy `no_ejecutado`) que quedó
   migrado a `Pendiente` y que su historial retro-poblado muestra el estado/nota/
   foto que tenía antes de este cambio.
