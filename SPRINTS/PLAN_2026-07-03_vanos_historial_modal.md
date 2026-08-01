# PLAN — Modal de cambio de estado con historial/trazabilidad de Vanos (issue #177)

**Fecha:** 2026-07-03
**Issue:** [Indunnova16/Instelec#177](https://github.com/Indunnova16/Instelec/issues/177)
**Estado:** Planning completado, listo para ejecución (F3)
**Reproceso:** bounce=1 (rebote sobre el cierre 🟡 del 2026-06-30/07-01)
**Supersede a:** `PLAN_2026-07-03_vano_historial_modal.md` (borrador de un F2 anterior,
RUN_2026-07-03_0713, que no completó el pre-lint del journey por EPERM de sandbox +
sintaxis no canónica del YAML — ver corrección de contenido en la sección de
decisiones HITL más abajo, la diferencia real no es solo el nombre del archivo).

## Contexto

El 2026-06-30/07-01 se cerró 🟡 "deployado + persistencia validada" el Ajuste 1
(nota/foto al cambiar estado de un Vano) + Ajuste 2 (rename "En Espera"→"Parcial")
+ Ajuste 3 (datalabels donut). El mismo día QA de Indunnova (@Indunnova,
2026-07-01T13:40:16Z) devolvió el issue: Ajuste 2 OK, **Ajuste 1 sigue sin
guardar** en su prueba real, Ajuste 3 sin evidencia, y el dropdown/resumen debe
tener 6 estados (falta Seccionado/Especial, sobra No Ejecutado). En el mismo
comentario el cliente hizo un **re-scope mayor**: reemplazar el dropdown por un
**modal** con **historial append-only** (persona/fecha/estado/nota/foto(s), sin
sobreescribir registros anteriores) y fijó la lista definitiva de 6 estados.

### Causa raíz del rebote — CONFIRMADA con evidencia de logs Cloud Run (no solo hipótesis)

Se revisaron los logs de `instelec-api` (`gcloud logging read`, proyecto
`appsindunnova`) para la ventana exacta de la prueba de QA:

```
2026-07-01T13:38:37.554688Z POST .../vanos/ae733441.../estado/  200  (57224 bytes — CON foto)
2026-07-01T13:38:41.041083Z POST .../vanos/ae733441.../estado/  200  (1649 bytes — SIN foto/nota)
2026-07-01T13:38:43.050999Z POST .../vanos/ae733441.../estado/  200  (1650 bytes — SIN foto/nota)
```

Son **3 POST distintos al mismo vano en 6 segundos**, los 3 con `200 OK` — el
servidor SÍ recibió y procesó las 3 requests (descarta H4, no es un problema de
caché). El estado final en BD (`vanos` id `ae733441-0644-4c4c-82ff-bdead95102e9`,
"Vano 15"): `estado='no_ejecutado'`, `observaciones=''` (**vacío**),
`foto='campo/vanos/Captura_de_pantalla_2026-07-01_083809.jpg'` (sí quedó),
`updated_at`/`fecha_marcado` = 13:38:43.077961 (coincide con el **último** POST,
el más chico, sin nota).

Esto reconstruye exactamente lo que pasó y confirma H1 de F1: **cada botón de
estado del dropdown actual dispara un submit inmediato** (no hay un "Guardar"
explícito). QA probablemente escribió la nota + adjuntó la foto, hizo clic en un
estado (1er POST, con foto — el swap de HTMX cierra/resetea el dropdown), volvió
a abrir el dropdown para probar otro estado (2do/3er POST) **sin volver a escribir
la nota** porque ya la había escrito "antes" en su cabeza — pero el formulario es
uno nuevo tras cada swap, así que la nota de esos clics posteriores viaja vacía y,
como el mecanismo es *overwrite* (no historial), el **último clic gana** y borra
efectivamente la nota. El bug NO es que el fix de `ec45f2a` no sirva (si sirve:
persiste lo que venga en el payload) — es que el **modelo de interacción** permite
perder datos entre clics porque no hay un punto único y explícito de guardado. El
único test agregado en `ec45f2a` (`tests_issue_177.py`) arma el POST a mano con el
Django test client — nunca ejerció el navegador real ni el escenario de "reabrir y
volver a clicar", así que nunca hubiera cazado esto.

**Por qué el modal (re-scope del cliente) resuelve la causa raíz de raíz, no solo
el síntoma:** un único botón "Guardar" explícito, con `fetch()+FormData` (patrón
`_vano_semestre_modal.html`, ya probado en el repo) en vez de
múltiples `<button type=submit>` + hidden input seteado por `@click`, elimina la
clase de bug completa: ya no existe la posibilidad de "clicar sin querer" ni de
que un segundo clic sin re-escribir la nota pise al primero, porque solo hay UN
evento de guardado y el usuario decide explícitamente cuándo dispararlo.

## Hallazgo de scope — dos modelos con el mismo enum, solo uno es este issue

| Modelo | App | Vista/template | ¿Es este issue? |
|---|---|---|---|
| `Vano` (`apps/lineas/models_base.py`) | lineas | `RegistroAvanceCreateView` / `avance_registrar.html` / `vano_cuadro.html` / `VanoEstadoUpdateView` — grilla "Avances de Vanos" | **SÍ** — es el feature de att_01/02/03 |
| `AvanceVano` (`apps/campo/models.py`) | campo | `AvancesCuadrillaView` / `avances_cuadrilla.html` / `MarcarVanoView` — auto-marcado por cuadrilla dentro de una `Actividad` | **NO** — feature distinta, comparte enum por copy-paste pero no se toca acá |

También confirmado: `VanoSemestre.Estado` (`apps/lineas/models_b21.py`, feature
B2.1) es tabla/feature distinta — no se toca.

## Hallazgo adicional — bug de autorización latente (bundle quirúrgico, mismo archivo)

`VanoEstadoUpdateView.post` (a reemplazar) usa roles
`['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']` — **sin**
`admin_general`. `RegistroAvanceCreateView._build_context` ya documenta en
comentario que `admin_general` (RBAC v2 desde #44, rol canónico de `qa_claude`)
debe incluirse. Se corrige en el mismo archivo que ya se reescribe (sub-item A4),
sin trabajo adicional fuera de scope.

## Decisiones HITL resueltas con criterio conservador (no bloquean el desarrollo)

El orquestador dejó 2 decisiones de negocio pendientes de F1. Se resuelven así
(default conservador, documentado, NO ejecutado sobre BD prod sin gate humano):

### 1. Dato legacy `estado='no_ejecutado'` (1 fila en prod: vano "15", línea
   Puerta de Oro, `ae733441-0644-4c4c-82ff-bdead95102e9`)

**Decisión: NO se migra/reescribe la fila existente. Ningún `UPDATE` sobre
`vanos`.** El enum `Vano.Estado` se amplía de forma **aditiva**: se agregan
`SECCIONADO` y `ESPECIAL`, y **se conserva `NO_EJECUTADO`** como choice válido
(no se borra del modelo) pero se lo excluye del selector de estados **nuevos**
del modal vía un método `Vano.Estado.seleccionables()` que devuelve solo los 6
valores que el cliente pidió. El vano legacy sigue mostrando "No Ejecutado" vía
`get_estado_display()` sin ningún cambio, y su historial se retro-puebla (ver
sub-item A3) con ese mismo valor tal cual — no requiere ninguna decisión de
mapeo semántico (¿es Pendiente? ¿Sin Permiso?) que sí sería una decisión de
negocio real.

> ❗ **Corrección vs. el borrador anterior (RUN_2026-07-03_0713):** ese borrador
> proponía una migración `RunPython` que hacía `UPDATE vanos SET estado='pendiente'
> WHERE id='ae733441...'` — un remapeo semántico inventado por el agente, exactamente
> lo que esta directiva pide evitar. Se descarta esa migración de datos destructiva.

Efecto colateral aceptado (documentado, no bloqueante): el Stats Row/donut de 6
categorías (sub-item A8) no tiene una tarjeta para "No Ejecutado" — ese 1 vano
legacy simplemente no aparece en ninguna de las 6 categorías hasta que alguien
en campo lo reclasifique manualmente vía el modal nuevo (momento en que entra al
esquema nuevo de forma orgánica, sin intervención de datos). `Total Vanos` sigue
contando TODOS los vanos de la línea sin cambios (ya es independiente de las
categorías hoy).

**Pregunta abierta para Miguel (no bloquea):** ¿el cliente quiere que alguien
reclasifique manualmente ese vano legacy a uno de los 6 estados nuevos, o
prefiere que quede como "No Ejecutado" histórico indefinidamente?

### 2. Límite de fotos por cambio de estado

**Decisión: soporta múltiples fotos (0 a N, tope técnico N=5)**, reusando el
patrón `FotoDano`/`ReporteDano` (`apps/campo/models.py:415`) ya existente en el
repo — 1:N vía FK inverso. Nuevo modelo `VanoHistorialFoto` (FK a
`VanoHistorialEstado`, `related_name='fotos'`). Es la lectura más fiel al
re-scope del cliente ("foto(s)" en plural) y al precedente de código ya
existente, no una invención.

**Preguntas abiertas para Miguel (no bloquean, defaults documentados):**
- Colores para "Seccionado"/"Especial" en el dropdown/donut — default aplicado:
  `#a855f7` (púrpura) y `#ec4899` (rosa/fucsia), distintos a los 4 ya usados
  (gris/verde/naranja/amarillo).
- ¿El historial debe permitir editar/borrar un registro erróneo? — default
  aplicado: **no**, es estrictamente append-only e inmutable (sin endpoints de
  update/delete), consistente con la palabra "historial"/"trazabilidad" del
  pedido del cliente. Si se necesita corrección, será un issue nuevo con su
  propia definición de quién puede corregir y bajo qué gate.
- Tope de 5 fotos por cambio de estado — default técnico, ver arriba; el cierre
  del issue debe pedirle al cliente que confirme si 5 alcanza.

## Gate de scope — `epic_pero_single_módulo`, NO handoff a `/modulo`

F1 marcó `complexity_class=epic` (10 sub-items iniciales, riesgo alto, modelo
nuevo + migración + UI nueva). Descomponiendo en detalle: **11 sub-items, 4
`high` / 4 `medium` / 2 `trivial` / 1 `low`** — bajo el umbral del gate (≥1
`epic` individual o ≥6 `high`). Es un solo módulo funcional (Avances de Vanos,
dentro de `apps/lineas` + `apps/campo`, mismo dominio de negocio), no una épica
multi-módulo. Se ejecuta como `sprint_path` normal dentro de `/multiagente`, SIN
handoff a `/modulo`.

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada | Sub-items que lo entregan | ✅/❌ |
|---|---|---|---|---|
| 1 | **Fix real de persistencia nota/foto (root cause del bounce)** — reproduce el escenario EXACTO de logs (múltiples submits consecutivos sobre el mismo vano en <10s, reabriendo el modal entre cada uno) sin pérdida de datos | Journey E2E: 2 guardados consecutivos sobre el mismo vano, ambos con nota+foto propias, AMBOS visibles en el historial tras el segundo guardado | A4, A6 | ⏳ |
| 2 | Modal reemplaza dropdown, con botón "Guardar" explícito | Clic en la tarjeta del vano → modal (no dropdown) con selector 6 estados + nota + foto(s) + botón Guardar único | A6, A7 | ⏳ |
| 3 | Modelo `VanoHistorialEstado` (append-only) + `VanoHistorialFoto` (0..N) | Migración aplicada en prod; POST real crea fila nueva SIN borrar la anterior | A2, A4 | ⏳ |
| 4 | `Vano.estado` "actual" derivado/denormalizado del último registro del historial | Tras un cambio de estado, `Vano.estado` (campo denormalizado, actualizado por la vista) coincide con el último `VanoHistorialEstado.estado` | A4 | ⏳ |
| 5 | UI de historial completo visible por vano (todas las notas/fotos de cada cambio) | Partial de historial en prod muestra ≥2 registros tras 2 cambios consecutivos, cada uno con su nota y foto(s) propias | A5, A6 | ⏳ |
| 6 | Migración de estados: 6 nuevos seleccionables + legacy preservado (NO destructiva) | `Vano.Estado.choices` = 7 tuplas; `Vano.Estado.seleccionables()` = 6 (sin `no_ejecutado`); vano legacy intacto en BD (`estado='no_ejecutado'` sin tocar) | A1, A3 | ⏳ |
| 7 | Stats Row + donut actualizados a 6 categorías con conteos correctos | `avance_registrar.html` en prod: tiles + donut con las 6 categorías nuevas, colores sin colisión | A8 | ⏳ |
| 8 | Confirmar Ajuste 3 (datalabels donut) — QA no vio evidencia | Screenshot/URL smokeada mostrando los datalabels sobre el donut en prod (commit `6dc05ff`) | A10 | ⏳ |
| 9 | Tests happy + ≥2 edge cases (incl. escenario exacto de logs, historial multi-registro, legacy no destructivo) | `pytest apps/campo/tests_issue_177.py` 100% verde | A11 | ⏳ |
| 10 | Journey E2E mutativo que reproduce el escenario literal de QA/logs | `.e2e_pass` marker post-deploy vía `run_e2e_or_die.py` contra revisión promovida | A11 (journey ya entregado por este F2) | ⏳ |

## Sub-items (Sprint A — único sprint, v1.0 atómica)

Todo pertenece al mismo deployable: el modal no tiene sentido sin el historial
detrás, y el historial no tiene UI sin el modal. `deployable_solo=false` para
todos los sub-items salvo el paquete completo (A1..A11 juntos).

| id | Sub-item | Archivos | Complexity | Depende de |
|---|---|---|---|---|
| A1 | `Vano.Estado` ampliado a 7 choices (aditivo: +Seccionado/+Especial, retiene No Ejecutado como legacy no-seleccionable) | `apps/lineas/models_base.py`, migración `0014` (AlterField, sin mutación de datos) | low | — |
| A2 | Modelos `VanoHistorialEstado` + `VanoHistorialFoto` (patrón `FotoDano`/`HistorialIntervencion`) | `apps/lineas/models_base.py`, migración `0015` (CreateModel x2) | high | — |
| A3 | Data migration ADITIVA (solo INSERT): backfill 1 `VanoHistorialEstado` retro-poblado por cada Vano con señal de uso previo (estado≠pendiente / observaciones / foto), valores AS-IS sin remapear | migración `0016` (RunPython, idempotente, `RunPython.noop` en reversa) | medium | A1, A2 |
| A4 | Endpoint `VanoHistorialCreateView` — root cause fix + crear historial + tope 5 fotos + fix `admin_general` + actualiza estado denormalizado | `apps/campo/views.py`, `apps/campo/urls.py` | high | A1, A2, A3 |
| A5 | Endpoint `VanoHistorialListPartialView` — listar historial completo | `apps/campo/views.py`, `apps/campo/urls.py`, `templates/campo/partials/_vano_historial_list.html` (nuevo) | medium | A2 |
| A6 | Modal Alpine `_vano_estado_modal.html` (fetch+FormData, patrón `_vano_semestre_modal.html`) | `templates/campo/partials/_vano_estado_modal.html` (nuevo) | high | A4, A5 |
| A7 | Rewrite `vano_cuadro.html` — trigger modal, quita dropdown | `templates/campo/partials/vano_cuadro.html`, `templates/campo/avance_registrar.html` | medium | A6 |
| A8 | Stats Row + donut a 6 categorías (colores nuevos, datalabels intacto) | `apps/campo/views.py` (`_build_context`), `templates/campo/avance_registrar.html` | medium | A1 |
| A9 | `seed_data.py` — verificación (ya itera `Vano.Estado.choices` dinámicamente, sin cambio de código esperado) | `apps/core/management/commands/seed_data.py` (verificación) | trivial | A1 |
| A10 | Confirmar Ajuste 3 (datalabels donut) — re-smoke contra prod actual | N/A código — smoke/captura | trivial | — |
| A11 | Reescribir `tests_issue_177.py` + journey E2E (ya entregado por este F2) | `apps/campo/tests_issue_177.py`, `SPRINTS/RUN_2026-07-03_0800/journeys/Instelec_177.yaml` | high | A4, A5, A6, A7, A8 |

## DAG de dependencias

```
A1 (7 choices) ──┬──────────────────────────────────────────────────┐
                  ├─→ A3 (backfill aditivo) ─→ A4 (endpoint crear) ─┤
A2 (modelos) ─────┘                            A5 (endpoint listar)┤
                                                                     ├─→ A6 (modal) ─→ A7 (vano_cuadro.html) ─┐
A1 ────────────────────────────────────────────→ A8 (stats/donut) ───────────────────────────────────────────┤
A1 ────────────────────────────────────────────→ A9 (seed verify) ────────────────────────────────────────────┤
A10 (re-smoke Ajuste 3, independiente) ─────────────────────────────────────────────────────────────────────┤
                                                                                                                ├─→ A11 (tests+journey)
```

Orden sugerido: `A1 ∥ A2 → A3 → (A4 ∥ A5) → A6 → A7`; en paralelo `A8`/`A9` corren
apenas está `A1`; `A10` es independiente (puede correr en cualquier momento);
`A11` al final, depende de todo lo demás.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Repetir la clase de bug del rebote** (pérdida de datos entre submits) | Modal usa `fetch()+FormData` con un ÚNICO botón "Guardar" (patrón ya probado `_vano_semestre_modal.html`), no el patrón HTMX-submit-múltiple-con-hidden-input que causó el bug. Elimina la clase de bug, no solo el síntoma — confirmado con evidencia real de logs (ver Causa raíz arriba), no solo hipótesis. Gate E2E Playwright real obligatorio (journey `Instelec_177.yaml`) reproduciendo 2 guardados consecutivos. |
| **Migración de datos destructiva** | Descartada explícitamente (ver Decisiones HITL #1) — A3 es solo `INSERT`, cero `UPDATE`/`DELETE` sobre `vanos`. |
| **Confundir `Vano` con `AvanceVano`/`VanoSemestre`** | Documentado arriba (hallazgo de scope); ninguno de los otros dos se toca. |
| **Bug latente de autorización (`admin_general`)** | Se corrige en el mismo endpoint que ya se reescribe (A4), sin trabajo fuera de scope. |
| **Discrepancia visual: vano legacy no aparece en ninguna de las 6 categorías del resumen** | Documentado explícitamente arriba y en el comentario de cierre al cliente — no es un bug, es consecuencia directa de no tocar datos legacy sin autorización. |
| **Ventana de inconsistencia durante el deploy** (entre migración de esquema 0014/0015 y backfill 0016) | Las 3 migraciones van en el mismo release; el job `instelec-migrate` corre antes de promover tráfico (estándar del repo). |
| **Tope de 5 fotos no confirmado por cliente** | Default técnico documentado (ver Decisiones HITL #2); mencionar en el comentario de cierre para que el cliente confirme si necesita más. |

## Validación esperada (cliente, tras deploy)

1. Entrar a `/campo/avance/registrar/?linea_id=14d79066-060b-4713-a642-6580105a85f7`
   (línea Puerta de Oro, QA de referencia).
2. Clic sobre cualquier vano → se abre el **modal** (ya no el dropdown).
3. Seleccionar uno de los 6 estados, escribir una nota, adjuntar 1-2 fotos,
   clicar **Guardar**.
4. Repetir sobre el MISMO vano una segunda vez (otro estado, otra nota, otra
   foto) → el historial debe mostrar **ambos** registros (persona, fecha,
   estado, nota, foto), el más reciente arriba, **sin que el primero
   desaparezca** — este es el punto que falló en el rebote.
5. Verificar Stats Row + donut "Distribución de Estados": 6 categorías, sin
   "No Ejecutado", con "Seccionado" y "Especial" presentes con color propio.
6. Confirmar que el vano legacy "15" (`ae733441-...`) sigue mostrando "No
   Ejecutado" tal cual estaba (dato histórico intacto, no migrado).
7. Confirmar datalabels del donut (Ajuste 3) visibles sobre las porciones.

## Preguntas abiertas para Miguel (HITL informativo, no bloquean)

1. ¿El vano legacy "15" (estado='no_ejecutado') debe reclasificarse manualmente
   por alguien de campo, o queda como histórico indefinidamente?
2. Colores de "Seccionado"/"Especial" — default aplicado `#a855f7`/`#ec4899`,
   ¿el cliente tiene una paleta preferida?
3. ¿El historial debe permitir editar/borrar un registro erróneo? — default
   aplicado: no (append-only estricto).
4. Tope de 5 fotos por cambio de estado — default técnico, confirmar si alcanza.
