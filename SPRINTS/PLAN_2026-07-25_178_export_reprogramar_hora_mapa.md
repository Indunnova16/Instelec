# PLAN — Cuadrilla semanal: export horizontal, sin-asignar, reprogramar, hora planeada, mapa (issue #178)

**Fecha:** 2026-07-25
**Issue:** [Indunnova16/Instelec#178](https://github.com/Indunnova16/Instelec/issues/178)
**Estado:** Planning completado, listo para ejecución (F3 sprint_exec)
**Ruta:** sprint_path — completo, SIN partir. F1 marcó el issue `complexity_class: epic`
a nivel de triage (banda P-11 del scope SIN descomponer) y dejó
`requiere_input_humano: true` preguntando si partir en tandas; el orquestador ya trae
instrucción explícita de ejecutar los 5 pedidos codeables (A/B/C/D/F) de la demo del
2026-07-25 completos en este RUN — mismo patrón que #188 (epic bandeado se descompone
INTERNAMENTE en sub-items medium/high, eso NO es "partir el scope").

## Contexto

Demo en vivo con Alcides y Gabriel (2026-07-25) sobre el módulo Programación Semanal de
Cuadrillas, ya en producción (Sprint A/BC de #178 + Sprint D de #188, sin regresiones
reportadas). Confirmado funcionando: crear/editar bloque, agregar personal por cédula con
autocompletado, exportar PDF, duplicar semana, asistencia con horas extra/viáticos. El
comentario 2026-07-25 trae 5 pedidos nuevos con cita textual del cliente:

- **(A)** Exportar a Excel con el MISMO formato horizontal que Alcides ya usa
  (`ACTIVIDAD|LINEA|TRAMO|INICIO|FIN|PERSONAL|CEDULA|CELULAR|CARGO|ROL|PLACA|AVISOS|ORDEN|PT SAP|Comentarios`,
  1 fila por persona, sin merges — verificado con openpyxl contra el archivo real adjunto
  `Programación - S27.xlsx`, headers fila 2 EXACTOS).
- **(B)** Listado de personal del maestro Colaboradores SIN asignar a ningún bloque de la
  semana (Gabriel: manejan hasta 120 personas, "se le queda a uno por ahí volando").
- **(C)** Botón "Reprogramar" por cuadrilla/bloque: mover a otra actividad/ubicación desde
  un día específico de la semana en adelante, SIN romper el bloque original (ejemplo real:
  cuadrilla movida el 26/07 tras una emergencia).
- **(D)** Hora de inicio/fin PLANEADA a nivel de bloque, separada de la asistencia real
  (que ya calcula horas extra).
- **(F)** Filtro por semana en el Mapa de cuadrillas + entrada manual de coordenadas
  (sitios sin señal).

**Fuera de este sub-set** (no incluidos, por bloqueo real o decisión de scope pendiente):
`B1` (import masivo horizontal, bloqueado desde 2026-07-01 por Q1/Q4 sin responder) y `G`
(asistencia foto+geolocalización anti-fraude, explícitamente fuera de este comentario del
cliente, pendiente de que Andrea confirme con Miguel).

## Grounding de código hecho en esta corrida de F2 (más allá del `tocaria` de F1)

F1 ya identificó correctamente que el exportador existente
(`apps/actividades/exporters.py::ProgramacionSemanalExporter`) es un formato DISTINTO
(agrupado por `Actividad`, personal en celda combinada) — no reusable tal cual. Grounding
adicional de esta corrida, con impacto directo en el diseño de los sub-items:

1. **`Cuadrilla` NO tiene `fecha_fin`** — solo `fecha` (única, poblada como `fecha_inicio`
   por `ProgramacionS18CuadrillaImporter._guardar_bloque`, línea 975/992 de
   `apps/cuadrillas/importers.py`). El Excel real trae INICIO **y** FIN por actividad
   (`bloque['fecha_fin']` ya se parsea en el importer, línea 855, pero se descarta — solo
   se usa para armar el string `nombre`, línea 1227-1234). Para que el export horizontal
   (A) muestre FIN real hace falta **un campo nuevo** `Cuadrilla.fecha_fin` + persistirlo
   en el importer.
2. **AVISOS/ORDEN/PT SAP NO tienen columnas propias en `Cuadrilla`** — se serializan como
   prefijo de texto en `observaciones` (`_construir_observaciones`,
   `apps/cuadrillas/importers.py:1236-1254`): `"Avisos: X | Orden: Y | PT SAP: Z | <obs>"`.
   NO existe un parser reverso. El exportador (A) necesita uno nuevo para separar esas 3
   columnas + el remanente de Comentarios. Bloques creados desde la UI de #188 (grid
   editable) NO tienen ese prefijo — el parser debe degradar limpio (todo va a
   Comentarios, AVISOS/ORDEN/PT SAP vacíos).
3. **🔴 Riesgo silencioso de alto impacto — inversión CARGO/ROL.** En
   `_bloque_a_dict` (`apps/cuadrillas/views_semanal.py:113-170`), la clave de dict
   `m["cargo"]` = `m.get_cargo_display()` = **CargoJerarquico** (JT/CTA vs Miembro), y
   `m["rol"]` = `m.get_rol_cuadrilla_display()` = **el cargo/puesto real** (Liniero I,
   Ayudante...). Esto coincide con cómo YA se ve la tabla en prod (`_bloque_card.html`,
   columnas "Cargo"/"Rol" con esos mismos valores) — pero es **exactamente lo INVERSO** de
   lo que el Excel real de Alcides llama CARGO (puesto: Liniero I) y ROL (JT/CTA) — ver
   `ProgramacionS18CuadrillaImporter.COLUMN_MAPPINGS` y su docstring: *"El **encargado** se
   marca con la columna `ROL` (`JT/CTA`)... La columna `CARGO` (`LINIERO I`, `AYUDANTE`...)
   mapea a `RolCuadrilla`"*. Si A2 escribe `fila['CARGO'] = miembro['cargo']` ingenuamente
   (copiando el nombre de la clave del dict), el Excel exportado sale con las columnas
   CARGO/ROL **cambiadas** — bug silencioso, alto impacto (cada fila de cada export), bajo
   ruido visual (nadie lo nota sin comparar contra el Excel real de Alcides). Mapeo
   CORRECTO exigido: **Excel `CARGO` ← `miembro['rol']`** (puesto real) / **Excel `ROL` ←
   `miembro['cargo']`** (JT/CTA). Test unitario obligatorio en A2 (ver tabla).
4. **Colisión de migraciones — extendida más allá de C/D.** El riesgo que el orquestador
   pidió resolver explícitamente (C y D tocando `Cuadrilla` + `migrations/` en paralelo)
   **se extiende a A y F** tras este grounding: A necesita `Cuadrilla.fecha_fin`, C
   necesita campos nuevos de reprogramación, D necesita horas planeadas, y F necesita un
   campo en `TrackingUbicacion` (mismo app `cuadrillas`, mismo directorio
   `migrations/`) para distinguir coordenada manual de GPS automático. **Decisión: [a]
   migración única consolidada** (sub-item `M1`, mismo patrón que
   `PLAN_2026-07-19_188_rediseno_cuadrillas.md` sub-item A1) con TODOS los campos nuevos de
   los 4 pedidos, 100% aditiva/nullable, cero backfill destructivo. `A2`, `D1`, `C1` y `F2`
   dependen de `M1` — el orquestador NO debe despachar ninguno de ellos antes de que `M1`
   esté mergeado, y nunca en paralelo entre sí sobre `migrations/`.
5. **Colisión secundaria de archivo — `_bloque_card.html`/`_bloque_form.html` entre C y
   D.** Con la migración ya consolidada en `M1`, queda un segundo riesgo de colisión: `D1`
   agrega 2 inputs de hora al form + su display en la card; `C1` agrega un botón +
   mini-form nuevo en la card. Ambos tocan `_bloque_card.html` (y `C1` referencia
   `_bloque_form.html` indirectamente si reusa su estructura). **Decisión: `C1` depende
   explícitamente de `D1`** (no solo de `M1`) — se ejecutan en SERIE, `D1` primero (cambio
   más chico y aditivo sobre la card), `C1` después (agrega el flujo nuevo sobre la card ya
   actualizada). El DAG abajo lo refleja; el orquestador no debe despacharlos en paralelo.
6. **Fuente de datos real de la semana confirmada:** `_bloques_qs`/`_contexto_semana`
   (`apps/cuadrillas/views_semanal.py`) siguen siendo la única fuente de verdad (mismo
   patrón que #188) — A2/B1 la reusan tal cual, no se crea un query paralelo.
7. **`MapaCuadrillasPartialView`/`MapaCuadrillasView` viven en `apps/cuadrillas/views.py`**
   (NO en `views_b3.py` como decía el `tocaria` inicial de F1) — corrección de archivo real
   para F1(mapa)/F2(coords manuales). El polling del mapa es JS plano (`fetch()` cada 30s +
   botón manual, `templates/cuadrillas/mapa.html:110-196`), NO HTMX — el filtro de semana
   (sub-item `F1`) debe viajar como querystring en ese `fetch()`, no vía atributos HTMX.
8. **Filtro de semana del mapa (F1): usar el mismo criterio `codigo` que TODO el resto del
   módulo, NO fechas de calendario.** `TrackingUbicacion` no tiene ningún campo de fecha de
   "semana de trabajo" (solo `created_at`, el timestamp del ping GPS) — pero su FK
   `cuadrilla` SÍ pertenece a una semana concreta vía el prefijo `codigo` `WW-YYYY-`
   (mismo concepto que usa `_bloques_qs`/`_prefijo` en `views_semanal.py`). Filtrar el mapa
   "por semana" es entonces `Cuadrilla.objects.filter(activa=True, codigo__startswith=_prefijo(anio,semana))`
   — reutiliza exactamente la MISMA semántica que el resto del módulo, sin inventar un
   filtro de rango de fechas nuevo. Se extrae `_prefijo` (hoy privado de
   `views_semanal.py`) a `apps/cuadrillas/utils_semana.py` (nuevo, sin lógica nueva, solo
   mover) para que `views.py` (F1) lo importe sin tocar función privada de otro módulo —
   mismo espíritu de extracción que `services.py` (#188, A5).
9. **`tramos` sigue vacía en prod (0 filas)** — riesgo operativo heredado de #188, aplica
   también a `C1` si la reprogramación cambia de tramo. Documentado, no bloqueante (mismo
   tratamiento que #188).

## Sub-items ejecutables (v1.0 completa — un solo sprint)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| M1 | **Migraciones aditivas consolidadas** (TODAS nullable/blank, cero backfill): `Cuadrilla.fecha_fin` (DateField), `Cuadrilla.reprogramado_desde` (FK self, `on_delete=SET_NULL`, `related_name='reprogramaciones'`), `Cuadrilla.hora_inicio_planeada` / `Cuadrilla.hora_fin_planeada` (TimeField), `TrackingUbicacion.origen` (CharField choices `auto`\|`manual`, default `auto`) | `apps/cuadrillas/models_base.py`, `apps/cuadrillas/migrations/00XX_bloque_fechafin_reprogramacion_horaplaneada_origen.py` | `apps/cuadrillas/tests_issue_178_demo0725.py::test_migraciones_aditivas_no_rompen_filas_existentes` (bloques/miembros/tracking ya cargados siguen leyendo `None`/`"auto"` sin romper) | - | low | ⏳ pendiente |
| A1 | **Persistir `fecha_fin` real al importar S18** — `ProgramacionS18CuadrillaImporter._guardar_bloque` (línea ~975 create, ~992 update) agrega `fecha_fin=bloque['fecha_fin']` (ya se parsea, hoy se descarta) | `apps/cuadrillas/importers.py` | happy: importar fila con INICIO+FIN reales → `Cuadrilla.fecha_fin` persistido; edge: fila sin FIN (columna vacía) → `fecha_fin=None`, no rompe | M1 | trivial | ⏳ pendiente |
| A2 | **Exportador Excel horizontal exacto** (pedido A) — nuevo método `generar_excel_horizontal(anio, semana)` en `ProgramacionSemanalExporter` (o clase nueva, a decidir por F3 sin romper la existente), reusa `_bloques_qs`/`_contexto_semana`; nuevo helper `_parsear_avisos_orden_ptsap(observaciones)` (reverso de `_construir_observaciones`); endpoint `ProgramacionSemanalExportarHorizontalView` (`GET /cuadrillas/semanal/<anio>/<semana>/exportar/`, nombre `cuadrillas:semanal_exportar_horizontal`); botón "Exportar Excel" junto al de PDF en `_tab_semanas.html`. **Mapeo CARGO/ROL obligatoriamente el del hallazgo #3 arriba (Excel CARGO←`rol`, Excel ROL←`cargo`) — NO copiar nombres de clave 1:1.** 1 fila por persona, sin merges, columnas EXACTAS `#`\|`ACTIVIDAD`\|`LINEA`\|`TRAMO`\|`INICIO`\|`FIN`\|`PERSONAL`\|`CEDULA`\|`CELULAR`\|`CARGO`\|`ROL`\|`PLACA`\|`AVISOS`\|`ORDEN`\|`PT SAP`\|`Comentarios` | `apps/actividades/exporters.py`, `apps/cuadrillas/views_semanal.py`, `apps/cuadrillas/urls.py`, `templates/cuadrillas/partials/_tab_semanas.html` | happy: semana con 2 bloques QA_E2E_ (≥2 personas c/u) → export 200, `Content-Type` spreadsheet, columnas exactas, CARGO/ROL NO invertidos (test unitario explícito con openpyxl comparando contra el dict fuente); edge 1: bloque con `observaciones` sin prefijo Avisos/Orden/PT SAP (creado por UI #188) → esas 3 columnas vacías, Comentarios = texto completo; edge 2: bloque con `fecha_fin=None` (legacy pre-A1) → columna FIN vacía, no rompe | A1 | high | ⏳ pendiente |
| B1 | **Listado de personal sin programar en la semana** (pedido B) — nuevo método/helper `_personal_sin_asignar(anio, semana)` en `views_semanal.py`: `PersonalCuadrilla.objects.filter(activo=True)` excluyendo `documento` de quienes tienen `CuadrillaMiembro.activo=True` en algún bloque de `_bloques_qs(anio, semana)` (mismo patrón de join por documento que `_bloque_a_dict` ya usa para `celular`); nueva sección en `_tab_semanas.html` (después de NOVEDADES, antes del datalist) listando nombre/documento/cargo | `apps/cuadrillas/views_semanal.py`, `templates/cuadrillas/partials/_tab_semanas.html` | happy: 2 colaboradores QA_E2E_ activos SIN bloque esta semana → ambos aparecen listados (`generalizes`: cualquier colaborador activo sin asignación de la semana consultada); edge 1: colaborador asignado a un bloque de OTRA semana → SÍ aparece en la semana actual (no falso negativo); edge 2: colaborador inactivo (`activo=False`) → NO aparece aunque no esté asignado | - | medium | ⏳ pendiente |
| D1 | **Hora de inicio/fin PLANEADA a nivel de bloque** (pedido D) — 2 inputs `type="time"` nuevos en `_bloque_form.html` (`hora_inicio_planeada`/`hora_fin_planeada`, junto al input `fecha` existente); `_bloque_card.html` muestra "Horario planeado: HH:MM–HH:MM" cuando ambos están seteados (claramente separado de Asistencia real, que vive en otro modelo/pantalla — sin colisión); `ProgramacionSemanalBloqueCrearView`/`BloqueEditarView` leen y guardan los 2 campos; `_bloque_a_dict` los expone | `apps/cuadrillas/views_semanal.py`, `templates/cuadrillas/partials/_bloque_form.html`, `templates/cuadrillas/partials/_bloque_card.html` | happy: crear bloque con hora_inicio=07:00/hora_fin=15:00 → persiste y se muestra en la card; edge 1: solo una de las 2 horas seteada → no rompe, se guarda igual (ambas nullable); edge 2: hora_fin < hora_inicio → mensaje de validación inline, no bloquea el resto del form (reusa patrón `_form_con_error`/`_card_con_error` ya existente) | M1 | medium | ⏳ pendiente |
| C1 | **Botón "Reprogramar" — mover cuadrilla/bloque desde un día específico, sin romper el original** (pedido C) — nuevo botón en `_bloque_card.html` (junto a "✏️ Editar"), nuevo partial `_bloque_reprogramar_form.html` (form separado de `_bloque_form.html` para minimizar colisión de archivo: nueva actividad/línea/tramo vía cascada AJAX ya existente `TramosPorLineaAPIView`, fecha desde, motivo opcional); nuevo endpoint `ProgramacionSemanalBloqueReprogramarView` (`POST /cuadrillas/semanal/bloque/<uuid:pk>/reprogramar/`, `cuadrillas:semanal_bloque_reprogramar`) que, en una transacción: (1) valida `fecha_desde` dentro de la semana ISO del bloque origen (usa `_rango_calendario` de `utils_semana.py`), (2) trunca el bloque origen (`fecha_fin = fecha_desde - 1 día`), (3) crea un bloque nuevo (`_siguiente_codigo_bloque`) con la nueva actividad/línea/tramo, `fecha=fecha_desde`, `fecha_fin=<fecha_fin original del origen antes de truncar>`, `reprogramado_desde=<origen>`, (4) copia los `CuadrillaMiembro` activos del origen al nuevo bloque (mismo usuario/rol/cargo/placa) — el origen NO se borra ni pierde su personal histórico. Responde con OOB swap (card origen actualizada + card nueva agregada), mismo patrón que `ProgramacionSemanalBloqueCrearView` | `apps/cuadrillas/views_semanal.py`, `apps/cuadrillas/urls.py`, `templates/cuadrillas/partials/_bloque_card.html`, `templates/cuadrillas/partials/_bloque_reprogramar_form.html` (nuevo) | happy: reprogramar un bloque QA_E2E_ con 2 miembros desde el día 3 de la semana → bloque origen con `fecha_fin` truncada + 2 CuadrillaMiembro SIN cambios, bloque nuevo con nueva actividad/línea + `reprogramado_desde` apuntando al origen + 2 CuadrillaMiembro copiados; edge 1: `fecha_desde` fuera del rango lunes-domingo de la semana del bloque → rechazado con mensaje inline, NO crea bloque nuevo; edge 2: bloque origen sin personal (0 miembros) → reprograma igual, bloque nuevo con 0 miembros, no rompe | M1, D1 | high | ⏳ pendiente |
| F1 | **Filtro por semana en el Mapa de cuadrillas** (pedido F, parte 1) — extrae `_prefijo` de `views_semanal.py` a `apps/cuadrillas/utils_semana.py` (nuevo, solo mover, sin lógica nueva); `MapaCuadrillasPartialView.get_context_data` (`apps/cuadrillas/views.py`) acepta `?anio=&semana=` opcional y filtra `Cuadrilla.objects.filter(activa=True, codigo__startswith=_prefijo(anio,semana))` (MISMO criterio `codigo` WW-YYYY- que usa todo el resto del módulo — sin filtro = comportamiento actual, todas las cuadrillas activas); `mapa.html` agrega selector anio/semana; `loadCrewLocations()` (JS plano, no HTMX) lee `anio`/`semana` de `window.location.search` en el `DOMContentLoaded` inicial (testable por URL directa, ej. `/cuadrillas/mapa/?anio=2099&semana=1`) Y del selector en cambios interactivos, incluyéndolos como querystring en su `fetch()` | `apps/cuadrillas/utils_semana.py` (nuevo), `apps/cuadrillas/views_semanal.py` (usa el import del nuevo módulo en vez de definir localmente), `apps/cuadrillas/views.py`, `templates/cuadrillas/mapa.html` | happy: filtrar por una semana con 2 bloques QA_E2E_ en semanas DISTINTAS, cada uno con su `TrackingUbicacion` → solo el de la semana filtrada aparece (`generalizes`: cualquier semana ISO filtra por su prefijo `codigo` real); edge: semana sin ninguna cuadrilla → mapa vacío con el overlay informativo ya existente (#175 A3), no rompe | - | medium | ⏳ pendiente |
| F2 | **Entrada manual de coordenadas** (pedido F, parte 2) — nuevo módulo `apps/cuadrillas/views_mapa.py` (patrón optional-import como `views_semanal.py`/`views_b3.py`), vista `TrackingUbicacionManualCreateView` (`POST /cuadrillas/<uuid:pk_cuadrilla>/ubicacion/manual/`, crea `TrackingUbicacion(origen='manual', usuario=request.user, ...)`); botón + mini-form (lat/lng/cuadrilla) en `mapa.html`; marcador Leaflet con ícono/color distinto para `origen='manual'` (evita que se confunda con GPS real en un sitio sin señal) | `apps/cuadrillas/views_mapa.py` (nuevo), `apps/cuadrillas/urls.py`, `templates/cuadrillas/mapa.html` | happy: ingresar coordenada manual para una cuadrilla QA_E2E_ → aparece en el mapa con marcador "manual"; edge 1: lat/lng fuera de rango válido (ej. lat>90) → rechazado con mensaje, no crea el registro; edge 2: cuadrilla inactiva → no permite reportar ubicación manual para ella | M1 | medium | ⏳ pendiente |
| T1 | **Suite de tests** — cubre M1-F2: migraciones no rompen filas existentes, export exacto (columnas + CARGO/ROL no invertido + parser Avisos/Orden/PT SAP con y sin prefijo), listado sin-asignar (incl. edge de otra semana), hora planeada (incl. validación fin<inicio), reprogramar (bloque origen intacto + nuevo con miembros copiados + fecha fuera de semana rechazada), filtro mapa por semana (incl. semana vacía), coordenada manual (incl. validación de rango) | `apps/cuadrillas/tests_issue_178_demo0725.py` (nuevo) | happy + ≥2 edge cases por sub-item (detallados arriba) | M1, A1, A2, B1, D1, C1, F1, F2 | high | ⏳ pendiente |
| T2 | Comentario al cliente con URLs + pasos numerados de validación (DoD, no código) — incluye nota explícita sobre exports/bloques LEGACY (pre-A1) que mostrarán columna FIN vacía en el export horizontal | - | - | T1 | trivial | ⏳ pendiente |

## DAG de dependencias

```
M1 (migraciones consolidadas: fecha_fin, reprogramado_desde, hora_inicio/fin_planeada, origen)
 ├─→ A1 (persistir fecha_fin al importar S18)
 │     └─→ A2 (exportador horizontal + endpoint + botón)
 ├─→ D1 (hora planeada: form + card + endpoint)
 │     └─→ C1 (reprogramar: depende de M1 Y de D1 — serializa los toques
 │              compartidos sobre _bloque_card.html, ver hallazgo #5)
 └─→ F2 (coordenada manual — depende de M1 por TrackingUbicacion.origen)

B1 (listado sin-asignar) — independiente, sin dependencias
F1 (filtro semana en mapa) — independiente, sin dependencias (NO toca Cuadrilla/migrations)

M1, A1, A2, B1, D1, C1, F1, F2 → T1 (tests)
T1 → T2 (comentario cliente)
```

**Primer sub-conjunto para despachar en paralelo (sin dependencias):** `M1`, `B1`, `F1`.
**Regla dura para el orquestador:** NO despachar `A2`, `D1`, `C1` ni `F2` hasta que `M1`
esté mergeado (todos tocan `apps/cuadrillas/models_base.py` y/o `migrations/`). NO
despachar `C1` en paralelo con `D1` (ambos tocan `_bloque_card.html`) — `C1` espera a que
`D1` termine.

## Riesgos y mitigaciones

- **🔴 Inversión CARGO/ROL (hallazgo #3, alto impacto/bajo ruido):** mitigado con mapeo
  explícito documentado en A2 + test unitario dedicado que compara el Excel generado
  contra el dict fuente campo a campo (no contra un "parece razonable").
- **Colisión de migraciones (A/C/D/F sobre `Cuadrilla`/`TrackingUbicacion`):** resuelta con
  `M1` consolidada — un solo archivo de migración, sin backfill destructivo.
- **Colisión de template (`_bloque_card.html`) entre C1 y D1:** resuelta secuenciando
  `C1` después de `D1` en el DAG (no en paralelo).
- **AVISOS/ORDEN/PT SAP sin parser reverso:** nuevo helper explícito en A2, con test para
  bloques CON y SIN el prefijo (los creados por la UI #188 no lo tienen).
- **`fecha_fin` ausente en bloques legacy (pre-A1, ya importados o creados por UI antes de
  este fix):** el export mostrará columna FIN vacía para esas filas — aditivo, no bloquea,
  se documenta explícitamente en el comentario al cliente (T2) como limitación conocida de
  datos históricos (no de código).
- **`tramos` vacía en prod (0 filas, riesgo operativo heredado de #188):** aplica también a
  C1 si la reprogramación cambia de tramo — mismo tratamiento: el journey de C1 crea su
  propio Tramo `QA_E2E_`, no depende de que el cliente ya haya cargado el dato real.
- **Reprogramar no inactiva la membresía del bloque origen:** decisión de diseño explícita
  (no bug) — el bloque origen queda truncado por fecha pero sus `CuadrillaMiembro`
  permanecen `activo=True` como registro histórico de quién trabajó ahí antes del cambio;
  se documenta en el comentario al cliente.
- **Reprogramar cruzando de semana:** fuera de alcance de este pedido (el cliente pidió
  "desde un día específico de la semana en adelante", no entre semanas) — `C1` valida y
  rechaza explícitamente una `fecha_desde` fuera del rango lunes-domingo del bloque origen.

## Validación esperada (qa_claude / smoke maestros post-deploy)

- `/cuadrillas/semanal/<anio>/<semana>/` — sigue en 200, grid intacto (no-regresión #188).
- `/cuadrillas/semanal/<anio>/<semana>/exportar/` (A2) — 200, `Content-Type` spreadsheet,
  columnas exactas `#|ACTIVIDAD|LINEA|TRAMO|INICIO|FIN|PERSONAL|CEDULA|CELULAR|CARGO|ROL|PLACA|AVISOS|ORDEN|PT SAP|Comentarios`,
  1 fila por persona, CARGO/ROL NO invertidos.
- Sección "Personal sin programar" (B1) visible al final del grid semanal, con ≥1
  colaborador real de la semana consultada si aplica.
- Crear/editar bloque con hora planeada (D1) → persiste y se muestra en la card.
- Botón "Reprogramar" (C1) sobre un bloque real → bloque origen intacto (personal
  preservado) + bloque nuevo visible con la nueva actividad/línea.
- `/cuadrillas/mapa/` — filtro por semana (F1) acota los puntos mostrados; entrada manual
  de coordenadas (F2) agrega un punto visible con marcador distinguible de GPS automático.
- Regresión: `/cuadrillas/semanal/<anio>/<semana>/pdf/` (C3 de #178) y `/cuadrillas/` (grid
  fusionado de #188) siguen en 200 sin cambios de comportamiento.

## Definition of Done (v1.0 completa)

- [ ] Migraciones creadas/aplicables (M1) — todas aditivas, sin backfill destructivo.
- [ ] Backend: endpoints + forms + lógica de negocio (A1, A2, B1, D1, C1, F1, F2).
- [ ] UI con estados completos: loading (HTMX indicator / fetch en curso), success (swap
  visible / marcador en mapa), error (mensajes inline en D1/C1/F2).
- [ ] Tests cubren happy + ≥2 edge cases por sub-item (tabla arriba + T1).
- [ ] Smoke E2E definido (sección de Validación esperada + journey YAML
  `Instelec_178.yaml`).
- [ ] Instrucciones de validación cliente redactadas (T2), incluyendo la nota de
  limitación de datos legacy (FIN vacío pre-A1).
