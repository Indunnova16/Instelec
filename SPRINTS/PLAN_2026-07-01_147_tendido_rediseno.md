# PLAN — Instelec#147: Rediseño Tendido (detalle por torre + CANT TENDIDO)

- **Issue:** Instelec#147
- **Ruta:** sprint_path (single-módulo `apps/construccion`, va completo en 1 sprint)
- **Fecha plan:** 2026-07-01
- **Complexity global:** complex (incluye migración de modelo + reestructuración de 2 templates)
- **Riesgo global:** medio
- **Sprint único:** A1..A9, DAG con 2 cadenas cortas (modelo→forms→template) + resto independiente

## Contexto

Sesión de revisión con Gabriel Valencia (Director de Construcción), documentada
en el comentario `2026-06-29T16:24:08Z` con 2 mockups HTML adjuntos como oráculo
de diseño (`tendido_mockup.html` para el detalle por torre, `cant_tendido_mockup.html`
para la lista CANT TENDIDO). **NO es reproceso** — el comentario inmediatamente
anterior (`2026-06-29T15:59`, 25 min antes) es una validación POSITIVA explícita
de los 2 últimos fixes del bounce 6 (letrero "Entrega para carga" resuelto ✅,
nombres completos F.T presentes ✅). El pedido del 16:24 es scope nuevo de
rediseño post-reunión, no una queja. `reproceso_rate.py` marca esto como
"bounce 7" por comparación mecánica de timestamps sin leer sentimiento — F1 ya
determinó y documentó este falso positivo; **no se aplica modo adversarial**
(no se re-prueba circuito 2 "No aplica", navegación matriz→detalle, ni el
letrero — todos ✅ validados y fuera de este scope).

**Nota de proceso:** los mockups NO estaban en los adjuntos descargados por F1
(`attachments_manifest.json` solo capturó imágenes `user-attachments/assets/*`,
que son las 8 capturas de pantalla de bounces previos). Los 2 mockups son
adjuntos de tipo **archivo** (`user-attachments/files/*`), un patrón que el
script de descarga de F1 no cubre. F2 los descargó directamente con `curl` desde
las URLs citadas en el comentario y los leyó completos — ambos son HTML plano
sin autenticación, 26KB c/u, ahora en
`RUN_2026-07-01_0735/attachments/Instelec_147/{tendido_mockup,cant_tendido_mockup}.html`.
**Recomendación para el orquestador:** el script de descarga de adjuntos debería
cubrir también `github.com/user-attachments/files/` a futuro (no solo `/assets/`).

### Hallazgo clave que resuelve la pregunta abierta de F1

F1 dejó como pregunta no bloqueante "¿cuál es el N exacto de tiros fijo por
circuito?". **El mockup lo responde explícitamente**: el `info-box` de la
Sección 1 dice *"Cada torre pertenece a un único tiro. Ingresa el N° de tiro y
completa los datos del mismo."* — o sea, **no hay "N tiros fijos por
circuito": hay exactamente UN tiro por torre**, con su número editable (para
casos donde ese tiro no es el primero de la línea, ej. "N° de tiro = 4" en el
mockup). Esto es más simple que un formset de N filas: **se elimina el
formset `RiegaManilaTiroFormSet` por completo** y sus campos (numero_tiro,
fecha del tiro, F.T, observaciones-del-tiro) se fusionan directamente en
`FaseTorre` (o se usa una relación 1-a-1 `FaseTorre.tiro`, ver Decisión de
Modelo abajo). Esto también implica que el botón "+ Agregar tiro" desaparece
por diseño (no hay "agregar", hay un único bloque "Tiro" con N° editable).

## Decisión de modelo (blueprint) — 🟡 confirmar con cliente si hay fricción, no bloqueante

**Opción elegida: fusionar el único tiro dentro de `FaseTorre` (no mantener
`RiegaManilaTiro` como tabla hija).** Justificación:
- El mockup es explícito: 1 torre = 1 tiro. Una relación 1-a-N con
  `unique_together` y formset ya no tiene sentido para cardinalidad 1-a-1.
- Los campos hoy "generales por torre" en `FaseTorre` (vestida, riega manila,
  riega guaya, FT-046/047/932/918, grapado, accesorios, placas, cuadrilla,
  %tendido, %facturación, observaciones) **YA SON** los campos que el mockup
  agrupa dentro de la sección "Tiro" — no hay que moverlos de tabla, ya viven
  en `FaseTorre`. Lo único que falta traer desde `RiegaManilaTiro` hacia
  `FaseTorre` es: `numero_tiro` (nuevo, editable), y opcionalmente `flecha_tendido_m`
  (F.T) si el cliente la sigue queriendo — el mockup NO muestra un campo F.T
  visible en la sección Tiro (fue reemplazado por los checks); **se mantiene
  como 🟡 decisión de scope**: F.T no aparece en el mockup, se interpreta como
  "eliminado de la UI" pero el dato NO se borra de BD (se preserva en el nuevo
  campo `fasetorre.flecha_tendido_m`, oculto de la vista, no se muestra en el
  template — así no se pierde el dato histórico ni se rompe nada si el
  cliente pide reactivarlo).
- Ventaja: elimina el formset dinámico Alpine (`agregarTiro`/`quitarFila`/
  `reindexar`, ~60 líneas JS) y el `inlineformset_factory` completo — reduce
  superficie de bug, alineado con "amerita blueprint dedicado" que anticipó el
  bounce 6.

**Campos nuevos en `FaseTorre` (migración 0041, additive):**
- `numero_tiro` — `PositiveSmallIntegerField(null=True, blank=True)` (no
  puede ser NOT NULL de entrada porque las torres existentes no tienen valor;
  ver backfill abajo).
- `ft931_ok` — `BooleanField(default=False, verbose_name='FT-931 Control
  regulación cable de guarda')` (campo nuevo pedido explícitamente).

**Backfill (migración de datos, additive, no destructiva):**
- Para cada `FaseTorre` con `tiros_manila.exists()`: `numero_tiro` = el
  `numero_tiro` MÍNIMO de sus `RiegaManilaTiro` asociados (representa el
  primer/único tiro real de esa torre; si por error histórico alguna torre
  tiene >1 fila en `RiegaManilaTiro`, se preserva la de menor número y las
  demás quedan intactas en la tabla legacy — no se borran, solo dejan de
  mostrarse en el nuevo template).
- Para `FaseTorre` sin ninguna fila en `tiros_manila`: `numero_tiro` queda
  `NULL` (torre aún no tendida, consistente con el resto de campos boolean
  default False / fecha NULL de "aún no iniciado").
- `RiegaManilaTiro` (tabla) **NO se elimina** en esta migración — se deja
  como legacy de solo-lectura (sin FK nueva apuntando a ella, sin exponerse en
  template/form). Elimina el riesgo de pérdida de dato de F.T. históricos.
  Si Miguel confirma con el cliente que no hace falta, un issue de limpieza
  futuro puede hacer `DROP TABLE` en una migración aparte — fuera de este
  scope.

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada (URL/campo/comportamiento) | ✅/❌ |
|---|---|---|---|
| 1 | Migración 0041 additive: `FaseTorre.numero_tiro` + `FaseTorre.ft931_ok` + backfill desde `RiegaManilaTiro` | `python manage.py showmigrations construccion` muestra 0041 aplicada; query prod post-deploy: torres con tiros previos tienen `numero_tiro` poblado | ❌ pendiente ejecución |
| 2 | Sección "Tiro" única en `tendido_torre.html`: N° tiro editable + todos los checks (vestida, riega manila/guaya, FT-046/047/**931**/932/918, grapado, accesorios, placas) + cuadrilla/%tendido/%facturación/observaciones agrupados, SIN botón "+ Agregar tiro" | Smoke visual URL detalle torre: existe 1 solo bloque "Tiro", campo N° tiro es `<input type=number>`, no aparece botón "+ Agregar tiro" en el DOM | ❌ pendiente ejecución |
| 3 | Sección "Información general" eliminada (fusionada dentro de Tiro) | Template ya no tiene `<details>` separado con Cuadrilla/%Tendido/%Facturación/Observaciones fuera del bloque Tiro | ❌ pendiente ejecución |
| 4 | Renombrado OPGW→Cable de guarda, Fase A/B/C→Fase 1/2/3 en detalle de torre (labels visuales, no nombres de campo Python) | Texto visible en `tendido_torre.html` renderizado: "Cable de guarda", "Fase 1"/"Fase 2"/"Fase 3"; ningún texto visible dice "OPGW" o "Fase A/B/C" | ❌ pendiente ejecución |
| 5 | "Regulación y flechado" reorganizada: dentro de Circuito 1 (con Cable de guarda) y dentro de Circuito 2 (oculta si C2 no aplica) — ya NO es sección independiente al final | Template: no existe `<details>` "Regulación y flechado por circuito" standalone; los campos `regulacion_flechado_c1_ok/fecha` viven dentro del `<details>` de Circuito 1, `regulacion_flechado_c2_ok/fecha` dentro de Circuito 2 (con `x-show="aplica"`), `regulacion_flechado_guarda_ok/fecha` dentro de la subsección Cable de guarda | ❌ pendiente ejecución |
| 6 | Campo nuevo FT-931 visible y guardable | Checkbox "FT-931 Control regulación cable de guarda" aparece en la sección Tiro, se persiste al guardar (`fasetorre.ft931_ok`) | ❌ pendiente ejecución |
| 7 | Mejora de densidad: fases 1/2/3 y cable de guarda izq/der en columnas horizontales (no filas verticales apiladas) | CSS grid con las 3 fases lado a lado (`md:grid-cols-3` ya existe — verificar que se conserva/ajusta tras el refactor) | ❌ pendiente ejecución |
| 8 | Sección "Cable de guarda + regulación final + cuadrilla" eliminada; sus 6 campos redistribuidos (tendido_guarda_* eliminados de UI por duplicar izq/der; regulación→movida; cuadrilla/%tendido/%facturación/observaciones→dentro de Tiro) | Template ya no tiene ese `<details>`; campos redistribuidos verificados en sus nuevas ubicaciones (#3, #5) | ❌ pendiente ejecución |
| 9 | CANT TENDIDO: renombrado "Fibra OPGW"→"Cable de guarda" (KPI, panel pesos, encabezado grupo, columna %, columna Realizó) | Smoke visual `/tendido/` matriz: texto "Cable de guarda" en KPI superior derecho, panel de pesos, encabezado de grupo de columnas y columna "% C. guarda"; ningún texto visible dice "Fibra OPGW"/"OPGW" | ❌ pendiente ejecución |
| 10 | CANT TENDIDO: columna Torre clickeable al detalle | `<a href="{% url 'construccion:tendido_torre' %}">` envuelve el número de torre en cada fila | ❌ pendiente ejecución |
| 11 | CANT TENDIDO: columna "Detalle/Editar" eliminada | La columna final con el link "Editar" ya no existe en el `<thead>`/`<tbody>` | ❌ pendiente ejecución |
| 12 | CANT TENDIDO: columna "Aplica" solo checkbox sin texto redundante | Verificar `_toggle_aplica_torre.html` — si ya es solo-checkbox, marcar ✅ sin cambios; si tiene texto por fila, quitarlo | ❌ pendiente ejecución (ver Riesgo/Nota abajo — puede ya estar OK) |
| 13 | Tests actualizados: `tests_issue_147.py` reescrito para tiro-único (elimina tests de formset multi-tiro: `test_post_crea_dos_tiros`, `test_persistencia_blindaje_dos_tiros_recarga`, `test_delete_oculto_borra_fila_guardada`, etc.) + tests nuevos para `numero_tiro` editable y `ft931_ok` | `pytest apps/construccion/tests_issue_147.py -v` pasa 100% en CI | ❌ pendiente ejecución |
| 14 | Test contra dato legacy (torre con `RiegaManilaTiro` pre-existente en prod, ej. T-1 de "QA test #49 — Puerta de Oro") | Tras backfill, `numero_tiro` de esa torre en prod refleja el valor esperado (mínimo de sus tiros previos) — verificar con 1 query SELECT prod post-deploy | ❌ pendiente ejecución |

## Sub-items (Sprint A — single-módulo, ejecuta completo)

| ID | Nombre | Descripción | Archivos | Depende de | Complexity | Deployable solo |
|---|---|---|---|---|---|---|
| A1 | Migración 0041: `numero_tiro` + `ft931_ok` + backfill | Additive migration + data migration (RunPython) que hace backfill desde `RiegaManilaTiro.numero_tiro` mínimo por `FaseTorre` | `apps/construccion/models.py`, `apps/construccion/migrations/0041_tiro_unico_ft931.py` | — | medium | No (base de A2-A5) |
| A2 | `FaseTorreTendidoForm`: agregar `numero_tiro`, `ft931_ok` a `Meta.fields`; quitar dependencia del formset | Actualizar form; remover import/uso de `RiegaManilaTiroFormSet` de `views.py` (`TendidoTorreView.get_context_data`/`form_valid`) | `apps/construccion/forms.py`, `apps/construccion/views.py` (L1372-1463) | A1 | medium | No |
| A3 | Template `tendido_torre.html`: reconstrucción completa de la sección "Tiro" (fusiona Vestida+sub-flujo conductor+Info general+Cable de guarda final en 1 bloque), eliminar botón "+Agregar tiro" y el bloque Alpine `tirosManila` del `extra_js` | Reescribir bloque `<details>` "Tiro" con N° tiro editable + checks (incl. FT-931) + cuadrilla/%tendido/%facturación/observaciones; eliminar `x-data="tirosManila(...)"` y el `<script>` completo de manejo de formset dinámico | `templates/construccion/tendido_torre.html` | A2 | high | Sí (dentro del sprint, no aislado de A4/A5 por ser mismo archivo) |
| A4 | Template `tendido_torre.html`: renombrado labels (OPGW→Cable de guarda, Fase A/B/C→1/2/3) + reorganización Regulación dentro de cada circuito + columnas horizontales | Sobre el mismo archivo de A3: cambiar textos visibles de `<summary>`/`<p>` (NO nombres de campo Python — son solo labels de UI), mover los 3 `regulacion_flechado_*` de su `<details>` standalone hacia dentro de los `<details>` de Circuito 1 / Circuito 2 / Cable de guarda, ajustar grid a columnas horizontales | `templates/construccion/tendido_torre.html` | A3 (mismo archivo, aplicar en la misma pasada de edición para evitar conflictos de merge) | medium | Sí |
| A5 | Eliminar sección "Cable de guarda + regulación final + cuadrilla" standalone | Remover el `<details>` completo (L219-231 actual); sus campos ya redistribuidos en A3 (cuadrilla/%tendido/%facturación/observaciones→Tiro) y A4 (regulación→dentro de circuito); `tendido_guarda_ok`/`tendido_guarda_fecha` se eliminan de la UI (duplicaban las fechas izq/der que sí se conservan) — el campo Python NO se borra de BD (solo deja de mostrarse, evita perder dato histórico) | `templates/construccion/tendido_torre.html` | A4 | low | Sí |
| A6 | CANT TENDIDO: renombrado "Fibra OPGW"→"Cable de guarda" (5 puntos: KPI, panel pesos, encabezado grupo columnas, columna %, columna Realizó) | Cambiar SOLO los textos visibles (`<h3>`, `<p>`, `<th>`) — los nombres de campo Python (`riega_manila_fibra`, `tendido_opgw`, etc.) y los slugs de `COLUMNAS_FIBRA` NO cambian (son internos, no visibles al cliente) | `templates/construccion/tendido_matriz.html` | — (independiente del resto) | low | Sí |
| A7 | CANT TENDIDO: columna Torre clickeable + eliminar columna Detalle/Editar | Envolver `{{ fila.torre.numero_display }}` en `<a href="{% url 'construccion:tendido_torre' proyecto.id fila.torre.id %}">`; eliminar la `<th>`/`<td>` de "Detalle" (L121, L184-190) y ajustar el `colspan` del `{% empty %}` (L193, hoy 22 → pasa a 21) | `templates/construccion/tendido_matriz.html` | — | low | Sí |
| A8 | CANT TENDIDO: verificar/compactar columna "Aplica" (solo checkbox) | Inspeccionar `_toggle_aplica_torre.html` — si ya renderiza solo un checkbox sin texto por fila, marcar como ya-cumplido (❌ falso positivo del pedido, el cliente puede estar viendo otra versión); si tiene texto, quitarlo | `templates/construccion/_toggle_aplica_torre.html` | — | low | Sí |
| A9 | Tests: reescribir `tests_issue_147.py` para modelo tiro-único + tests nuevos (`numero_tiro`, `ft931_ok`, columna Torre clickeable, columna Detalle ausente) | Eliminar/reescribir los ~7 tests que asumen formset multi-tiro; agregar tests de backfill (`numero_tiro` poblado tras migración con dato legacy) y de UI (assert botón "+Agregar tiro" NO existe, assert "Cable de guarda" sí existe, assert "OPGW" no existe en response visible) | `apps/construccion/tests_issue_147.py` | A1, A2, A3, A4, A5, A6, A7 | high | No (cierre) |

## DAG de dependencias

```
A1 (migración) ──> A2 (form/view) ──> A3 (template Tiro) ──> A4 (labels+regulación) ──> A5 (elimina sección final)
                                                                                              │
A6 (matriz rename) ─────────────────────────────────────────────────────────────────────────┤
A7 (matriz link+col) ─────────────────────────────────────────────────────────────────────────┤
A8 (matriz aplica) ───────────────────────────────────────────────────────────────────────────┤
                                                                                              ▼
                                                                                    A9 (tests, cierre — depende de TODO)
```

A6/A7/A8 son independientes entre sí y de la cadena A1→A5 (tocan
`tendido_matriz.html`, no `tendido_torre.html`/`models.py`) — pueden ejecutarse
en paralelo con la cadena de modelo. A9 cierra al final porque valida el
resultado combinado.

## Riesgos y mitigaciones

1. **Riesgo alto — pérdida de dato F.T (`flecha_tendido_m`) histórico.**
   Mitigación: NO se borra `RiegaManilaTiro` ni sus filas; el campo deja de
   mostrarse en UI pero el dato persiste en BD para auditoría/recuperación
   futura. Documentado explícitamente como decisión de scope ℹ️ en el
   comentario de cierre.
2. **Riesgo medio — torres con >1 `RiegaManilaTiro` histórico** (el
   formset viejo permitía várias filas; si algún operario ya cargó 2+ tiros
   para una torre, el backfill solo toma el de menor `numero_tiro` y el resto
   queda "huérfano" en la tabla legacy sin verse en la UI). Mitigación:
   ANTES de escribir la migración de datos, correr un `SELECT fase_id,
   count(*) FROM construccion_riega_manila_tiro GROUP BY fase_id HAVING
   count(*) > 1` contra prod (solo lectura) para dimensionar cuántas torres
   se ven afectadas; si son pocas (<5), reportar la lista exacta en el
   comentario de cierre para que el cliente decida manualmente cuál tiro es
   el válido. Si son muchas, escalar a Miguel antes de continuar (podría
   indicar que "1 tiro por torre" no es universal y hay excepciones reales
   de campo no capturadas en el mockup).
3. **Riesgo medio — regresión de tests existentes.** La reescritura de
   `tests_issue_147.py` es grande (7+ tests eliminados/reescritos). Mitigación:
   correr la suite completa de `apps/construccion/` (no solo
   `tests_issue_147.py`) antes de dar por cerrado, para detectar fixtures
   compartidos rotos (`torre_i147`, `proyecto_i147`) que otros tests puedan
   reusar.
4. **Riesgo bajo — colisión de campo `ft931_ok` con numeración de FT
   existente.** El modelo ya tiene `ft046_ok`, `ft047_ok`, `ft932_ok`,
   `ft918_ok` sin un patrón numérico estrictamente ascendente en estos 4 —
   agregar `ft931_ok` es consistente con el patrón de nombres existente, no
   requiere renombrar nada más.
5. **Riesgo bajo — A8 puede ser un no-op.** Falta confirmar en código si
   `_toggle_aplica_torre.html` ya es solo-checkbox (el pedido del cliente
   puede estar describiendo una versión visual que ya no corresponde a HEAD
   actual, o él la vio con texto en otra pantalla). Verificar antes de tocar.

## Validación esperada (para F3/F4/F5)

- **Smoke prod obligatorio:** crawlear `/construccion/<proyecto>/tendido/`
  (lista + matriz CANT TENDIDO) y el detalle de ≥2 torres distintas —
  **incluir T-1 de "QA test #49 — Puerta de Oro"** (`torre_id
  3cf707c8-306d-4e33-948c-bcf8cc220ef6`, el mismo registro legacy usado en la
  validación del bounce 6) para confirmar que el backfill de `numero_tiro`
  funcionó sobre dato real y que los checks migrados (FT-046/047/932/918)
  siguen marcados tras el refactor.
- **Journey YAML** (`$RUN_DIR/journeys/Instelec_147.yaml`): edita el detalle
  de T-1, verifica ausencia del botón "+Agregar tiro", presencia de "Cable de
  guarda"/"Fase 1/2/3", marca FT-931, guarda, recarga y confirma persistencia.
  Generaliza sobre la vista CANT TENDIDO validando ≥2 torres (T-1 y otra,
  ej. T-5) para el renombrado "Cable de guarda" en la tabla.
- **Registro legacy obligatorio:** T-1 de Puerta de Oro (dato real
  pre-existente con `RiegaManilaTiro` cargado desde el bounce de riega de
  manila) es el caso de prueba anti-regresión — si su `numero_tiro`
  post-backfill y sus checks persisten correctamente, el resto de torres
  (creadas después, sin tiros legacy) son un subconjunto más simple.

## Siguiente acción del orquestador

Lanzar F3 (sprint_exec) para A1→A9 en el orden del DAG (A1-A5 secuencial,
A6-A8 en paralelo con la cadena de modelo, A9 al final). Un solo PR/branch
`fix/instelec-147` (arranca fresh desde `origin/main`, la anterior ya fue
borrada por el orquestador). Migración 0041 requiere `python manage.py
migrate` en el deploy — confirmar que el workflow de deploy corre migraciones
automáticamente (patrón estándar Instelec) antes de promover tráfico.
