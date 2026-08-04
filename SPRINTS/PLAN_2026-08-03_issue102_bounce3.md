# PLAN — Instelec#102 (bounce=4 en curso, tercer rebote confirmado por watchdog)

## Contexto (F1)

Historial completo del hilo (`gh issue view 102 --comments`):

| # | Fecha | Qué se declaró cerrado | Devolución del cliente |
|---|---|---|---|
| 1 | 2026-05-26 | Modelo `VanoSemestre` construido (B2.1) | 2026-07-21: "el filtro de semestre nunca quedó conectado" — el dropdown existía, 0 wiring real |
| 2 | 2026-07-22 | PR #192: filtro cableado en `RegistroAvanceCreateView` (grid con `linea_id`) + carga real de vanos S1/S2 (migración 0017) | 2026-07-24: filtro seguía "igual" — root cause real: el cliente probaba `lineas:detalle`, página distinta con el mismo dropdown, nunca cableada |
| 3 | 2026-08-01 | `instelec-api-00216-mm6`: `LineaDetailView` (`lineas:detalle`) cableada a `VanoSemestre` | 2026-08-03 (comentario actual): "Validado aun no se borran los datos de… y no funcionan los filtros" + 4 capturas |

Post-mortem watchdog: `FIX_INCOMPLETO / validado_1_registro` (bounce=2) — el patrón
se repite: cada intervención valida UNA página/registro y dice 🟢, pero el
dropdown `lineas/_filtro_semestre.html` está incluido en **más de dos**
lugares y cada bounce solo cablea el que el reproductor probó.

## Lectura literal de las 4 capturas del comentario actual (descargadas y vistas)

1. `1_borrado_datos.png` — grid de vanos de **LN5114**
   (`linea_id=14d79066-060b-4713-a642-6580105a85f7`, texto del comentario lo
   confirma). Muestra Vano 1-7 "Ejecutado" (verde) y Vano 8-11, 15 "Sin
   Permiso" (rojo) — exactamente los estados de prueba que un comentario
   ANTERIOR (previo al bounce=3, nunca resuelto) ya había pedido borrar.
2. `2_semestre1.png` — URL visible en la barra:
   `.../campo/avance/registrar/?semestre=S1` **sin `linea_id`** → selector
   de líneas (tarjetas), "Mostrando solo vanos S1." LN5114=104, LN5156=264,
   LN5157=264, LN733=18, LN734=35, LN764=33, LN765=33, LN801=87, LN802=87…
3. `3_semestre2.png` — misma URL con `?semestre=S2`, mismo selector, **los
   mismos números exactos**: LN5114=104, LN5156=264, LN5157=264, LN733=18,
   LN734=35…
4. `4_todos.png` — `?semestre=` vacío ("Todos los semestres"), otra vez los
   mismos números.

El cliente lo resume él mismo: "son iguales".

## Qué pide el cliente AHORA (2 sub-requisitos, distintos de los 2 bounces previos)

Los bounces 1 y 2 fueron sobre "el filtro no filtra nada" en dos páginas ya
cerradas (`campo:avance_registrar` CON `linea_id`, y `lineas:detalle`). El
reclamo actual tiene DOS partes que NO son "arreglar el filtro" otra vez en
esas páginas:

**A. Borrar datos de prueba en LN5114** — pedido original en un comentario
previo (antes de bounce=3), nunca ejecutado: Vano 1-7 "Ejecutado", 8-11 y 15
"Sin Permiso", con historial de prueba debajo. Confirmado en BD (ver F2).

**B. El selector de líneas de `/campo/avance/registrar/` (SIN `linea_id`,
la pantalla ANTES de elegir línea) no filtra por semestre** — página
DISTINTA a las 2 ya cerradas: es el tercer lugar donde vive el mismo
dropdown `lineas/_filtro_semestre.html`, y nadie lo había cableado todavía.

| Página | View | ¿Cableada a `VanoSemestre`? |
|---|---|---|
| `campo:avance_registrar` CON `linea_id` (grid de vanos de 1 línea) | `RegistroAvanceCreateView` (rama "línea elegida") | ✅ bounce=2 (PR #192) |
| `lineas:detalle` (`/lineas/<uuid>/`) | `LineaDetailView` | ✅ bounce=3 (`instelec-api-00216-mm6`) |
| `campo:avance_registrar` SIN `linea_id` (selector, tarjetas por línea) | `RegistroAvanceCreateView` (rama "sin línea", early return) | ❌ — nunca leía `?semestre=`, usaba `l.vanos.count` fijo. **Root cause de este bounce.** |

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| 1 | Selector de líneas (`/campo/avance/registrar/` sin `linea_id`) respeta `?semestre=`: cada tarjeta muestra el conteo de vanos DE ESE semestre, no el total fijo | Conteo distinto para S1 vs S2 en ≥3 líneas reales de BD (LN733, LN5156, LN734) reproducido antes del fix y corregido después | ✅ (F2 repro + F3 fix, ver abajo) |
| 2 | El link de cada tarjeta preserva `?semestre=` al entrar al detalle de la línea (para no perder el filtro elegido) | `href` incluye `&semestre=` cuando hay filtro activo | ✅ (F3) |
| 3 | Borrar datos de prueba en LN5114 (vanos 1-11, 15: historial + reset a Pendiente) | Requiere DELETE sobre filas reales insertadas por usuarios reales del cliente (`alcides.giovannetti@instelec.com.co`, `admin@instelec.com.co`) — **NO es una fixture QA, es una escritura irreversible sobre datos de producción** | ⏸ **Fuera de alcance de F1-F3 de este RUN — requiere autorización explícita de Miguel antes de ejecutar el DELETE** (ver sección "Decisiones para Miguel") |

Fila #3 se declara ⏸ explícitamente, no ✅ ni ❌: el diagnóstico y la
evidencia están completos (ver F2), pero ejecutar el borrado es una acción
operativa sobre datos reales de un cliente, no un "fix de código" — excede
el alcance duro de este RUN (F1-F3, sin escrituras a BD prod) y amerita luz
verde explícita dado que ya hay 3 rebotes en este issue.

## F2 — Reproducción (múltiples registros, no 1 solo)

Vía Cloud SQL Auth Proxy (`127.0.0.1:5434`, solo lectura) contra
`instelec_db`:

```sql
SELECT l.codigo,
  (SELECT COUNT(*) FROM vanos v WHERE v.linea_id=l.id) AS total_vanos,
  (SELECT COUNT(DISTINCT v.id) FROM vanos v JOIN vano_semestres vs ON vs.vano_id=v.id WHERE v.linea_id=l.id AND vs.semestre='S1') AS s1,
  (SELECT COUNT(DISTINCT v.id) FROM vanos v JOIN vano_semestres vs ON vs.vano_id=v.id WHERE v.linea_id=l.id AND vs.semestre='S2') AS s2
FROM lineas l WHERE l.codigo IN ('LN5114','LN733','LN5156','LN5157','LN734');
```

| Línea | total_vanos | S1 real | S2 real | Lo que mostraba el selector en TODAS las capturas |
|---|---|---|---|---|
| LN5114 | 104 | 104 | 104 | 104 (coincide — línea "suerte", igual en ambos semestres) |
| LN5156 | 264 | 264 | **0** | 264 (❌ debería mostrar "Sin vanos en este período") |
| LN5157 | 264 | 264 | **0** | 264 (❌) |
| LN733 | 18 | 18 | **8** | 18 (❌ debería mostrar 8 en S2) |
| LN734 | 35 | 35 | **29** | 35 (❌ debería mostrar 29 en S2) |

Cuatro líneas con datos reales distintos (LN5156/LN5157/LN733/LN734)
confirman el bug — no es un artefacto de 1 solo registro (la lección del
post-mortem `validado_1_registro`). LN5114 es la línea "fixture con suerte"
que casualmente no expone el bug (mismo patrón que el post-mortem de
bounce=2), reforzando por qué validar con 1 sola línea es insuficiente.

**Causa raíz confirmada en código** (`apps/campo/views.py`,
`RegistroAvanceCreateView._build_context`, rama `if not linea_id:`): el
template `templates/campo/avance_registrar.html` (línea ~32-36, antes del
fix) usaba `{{ l.vanos.count }}` — cuenta TODOS los `Vano` de la línea sin
ningún filtro — completamente ajeno a `request.GET['semestre']`. La vista
nunca pasaba un conteo filtrado al contexto para esta rama.

### Datos de prueba en LN5114 (entregable #3, solo diagnóstico)

```sql
SELECT v.numero, v.estado FROM vanos v
WHERE v.linea_id='14d79066-060b-4713-a642-6580105a85f7'
  AND v.numero IN ('1','2','3','4','5','6','7','8','9','10','11','15')
ORDER BY v.numero::int;
```

Confirma: vanos 1-7 = `ejecutado`, 8-11 y 15 = `sin_permiso`. El historial
(`vanos_historial_estado`) muestra que fueron insertados por
`alcides.giovannetti@instelec.com.co` el 2026-06-24 (7 registros en <10s,
patrón de prueba/carga rápida) y por `admin@instelec.com.co` el 2026-07-03
con nota explícita `"prueba"` en el vano 15. Datos reales en BD prod, no
fixtures nuestras — de ahí la clasificación ⏸ en la tabla de entregables.

## F3 — Fix quirúrgico

`apps/campo/views.py` (`RegistroAvanceCreateView._build_context`):
1. El parseo de `?semestre=` se sube ANTES del early-return del selector
   (antes solo se parseaba en la rama "línea ya elegida").
2. En la rama `if not linea_id:`, se agrega 1 query agregada
   (`Vano.objects.filter(linea_id__in=..., semestres__semestre=semestre)
   .values('linea_id').annotate(n=Count('id', distinct=True))`) — evita
   N+1 sobre hasta ~30 líneas — y se anota `l.vanos_semestre_count` en cada
   objeto `Linea` de la lista.

`templates/campo/avance_registrar.html`:
1. Reemplaza `{{ l.vanos.count }}` (total fijo) por
   `{{ l.vanos_semestre_count }}` (ya filtrado).
2. `href="?linea_id={{ l.id }}"` → agrega `&semestre={{ semestre }}` cuando
   hay filtro activo, para no perder la selección al entrar al detalle.
3. Mensaje diferenciado: "Sin vanos en este período" (con filtro activo,
   count=0) vs "Sin vanos registrados" (sin filtro).

No se tocan modelos ni migraciones — reusa `VanoSemestre` ya existente.

## Fuera de alcance (declarado)

- Entregable #3 (borrado de datos de prueba LN5114) — ver tabla de
  entregables y sección de decisiones. Requiere autorización explícita y
  ejecución manual sobre BD prod (fuera de F1-F3).
- No se re-toca `RegistroAvanceCreateView` rama "línea elegida" ni
  `LineaDetailView` — ya cableadas y validadas en bounces 2 y 3
  respectivamente, sin evidencia de regresión en ellas.

## Decisiones para Miguel

1. **Autorizar el DELETE de datos de prueba en LN5114** (entregable #3).
   Es una escritura sobre filas reales insertadas por usuarios reales del
   cliente (no fixture QA) — requiere luz verde explícita antes de
   ejecutarse, y ejecutarse fuera de este RUN F1-F3 (ver protocolo
   "escrituras QA a prod: fixtures ≠ data-fix del cliente" — esto último
   SÍ aplica, pero prefiero confirmación dado el historial de 3 rebotes).
2. `grep -rn "_filtro_semestre" templates/ apps/` (corrido en este RUN)
   confirma que el partial `lineas/_filtro_semestre.html` solo se incluye
   en 2 templates: `templates/campo/avance_registrar.html` (2 ramas: grid
   con línea elegida + selector sin línea, ambas ahora cableadas) y
   `templates/lineas/detalle.html` (cableada en bounce=3). No queda ningún
   include sin cablear — las 3 ramas conocidas del dropdown quedan
   cubiertas tras este fix.
