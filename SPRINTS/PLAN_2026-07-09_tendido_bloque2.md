# PLAN — Instelec#147 · "Bloque 2" CANT TENDIDO (4 cambios)

- **Fecha:** 2026-07-09
- **Ruta:** sprint_path (decidida por F1)
- **Run:** RUN_2026-07-09_1838
- **Issue:** Indunnova16/Instelec#147 (8 bounces documentados — el issue más rebotado del portafolio)

## Por qué sprint_path y no 4 fix_path sueltos

F1 identificó la causa raíz del patrón crónico de este issue: cada corrida cierra 🟢/🟡
el scope que atacó, pero el propio comentario de validación del cliente deja anunciado
un remanente ("Bloque 2") que nunca se agenda como corrida dedicada — se acumula hasta
que el cliente lo repite días después. Eso es exactamente lo que pasó acá: el cliente
anunció Cambio 1 y Cambio 2 el 2026-07-01 al validar el sprint A1-A9; nunca se tocaron;
el 2026-07-07 el cliente los repite y agrega Cambio 3 y Cambio 4 como "complemento".

**Gate anti-FIX_INCOMPLETO no negociable para este issue:** las 4 filas de la tabla de
entregables de abajo deben tener evidencia ✅ antes de que F6 cierre 🟢. Si queda alguna
sin evidencia, el cierre es 🟡 explícito con el pendiente nombrado (o ❌ fuera de scope),
nunca se omite en silencio.

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada (URL/campo/comportamiento) | ✅/❌ |
|---|---|---|---|
| 1 | Cambio 1 — Circuito 2 gana checks propios (vestida + 4 checks) antes de las 3 fases | Detalle de torre `/construccion/{proyecto}/tendido/{torre}/` → sub-card "CONDUCTOR — Circuito 2" con checkbox+fecha "Vestida de torres" y grid de 4 checks (Riega manila, Riega guaya, Grapado/amarre final, Accesorios) ANTES de las 3 fases C2; persisten en BD (campos `c2_*` en `FaseTorre`); NO aparecen FT-046/047/931/932/918 ni Placas en esta sub-card (son del Tiro) | ❌ |
| 2 | Cambio 2 — Cuadrilla informativa read-only en Circuito 1 | Detalle de torre, tope de la sección "Circuito 1" → texto read-only "Cuadrilla tendido (informativo — desde Tiro): {valor}" reflejando el mismo valor guardado en `fase.cuadrilla_tendido` (sección Tiro), SIN campo de edición nuevo, SIN nueva columna en BD | ❌ |
| 3 | Cambio 3 — Renombrar "CANT TENDIDO" → "Tendido" | `<title>` y `<h1>` de `/construccion/{proyecto}/tendido/` dicen "Tendido" (no "CANT TENDIDO"); ítem del sidebar dice "Tendido" (no "CANT Tendido"); NO afecta el renombrado A6 (Fibra OPGW→Cable de guarda, ya ✅) | ❌ |
| 4 | Cambio 4 — Freeze-header de la matriz Tendido | En `/construccion/{proyecto}/tendido/`, al hacer scroll vertical con >15 torres, la fila/franja de encabezados de la tabla permanece visible (sticky); columna Torre sigue fija a la izquierda (patrón ya existente, sin regresión); mencionar issue #183 en el cierre | ❌ |

**Regla de cierre:** F6 solo puede reportar 🟢 si las 4 filas quedan ✅ con evidencia
concreta (URL smokeada + screenshot). Si Cambio 4 queda pendiente de reconciliar con el
componente compartido de #150 F2 (ver sección "Cambio 4" abajo), se declara 🟡 explícito
nombrando el pendiente — nunca se cierra 🟢 con esa fila vacía.

## Spec visual vigente

`tendido_mockup_v2.html` (bajado en F1 a
`$RUN_DIR/attachments/Instelec_147/tendido_mockup_v2.html`, ya disponible — no
requiere descarga nueva) es la ÚNICA fuente de verdad visual para Cambio 1 y 2:

- Líneas ~192-266: sección "Tiro" (N° tiro + Cuadrilla + fechas, sin cambios en esta
  ronda — ya implementado en A1-A9).
- Líneas ~307-311: "Cuadrilla tendido (informativo — desde Tiro)" al tope de Circuito 1
  — confirma literal el texto de Cambio 2.
- Líneas ~401-494: sección "Circuito 2 (3 fases adicionales)" con sub-card
  "CONDUCTOR — Circuito 2" (checkbox+fecha Vestida + 4 checks: riega-manila,
  riega-guaya, grapado, accesorios) ANTES de las 3 fases C2 — confirma literal el
  layout de Cambio 1. La nota de la línea ~494 confirma que si "Circuito 2 aplica"
  está desmarcado, TODA la sección (incluida la nueva sub-card) se oculta.

## Modelo actual confirmado (grep `apps/construccion/models.py`)

`FaseTorre` (clase completa ~línea 1290-1889) ya tiene el patrón `c2_*` establecido
para `regulacion_flechado_c2_ok` / `regulacion_flechado_c2_fecha` (líneas 1744-1746) y
el patrón base a replicar para Circuito 1 en líneas 1718-1760:
`vestida_torres_ok/fecha`, `riega_manila_ok`, `riega_guaya_ok`, `grapado_ok`,
`accesorios_ok`. El bloque Circuito 2 (líneas 1783-1794: `circuito_2_aplica`,
`tendido_conductor_c2_{a,b,c}_ok/fecha`) NO tiene hoy checks propios de vestida/riega/
grapado/accesorios — son estos los que agrega Cambio 1.

---

## Sub-item 1 — Cambio 1: Circuito 2 checks propios

**Complexity:** medium · **Sprint:** 1 · **Deployable solo:** sí (pero se agrupa con
2/3/4 en el mismo deploy del nodo, ver Variables `deploy: per_node`)

### Modelo — `apps/construccion/models.py`

Agregar 6 campos nuevos a `FaseTorre`, inmediatamente antes de
`circuito_2_aplica` (línea 1785) o justo después de él y antes de
`tendido_conductor_c2_a_ok` (línea 1786), siguiendo el patrón exacto de Circuito 1
(líneas 1718-1719, 1722, 1731, 1758-1760) pero con sufijo `c2_` (mismo prefijo que
`regulacion_flechado_c2_ok`):

```python
c2_vestida_ok = models.BooleanField('Vestida de torres — Circuito 2', default=False)
c2_vestida_fecha = models.DateField(null=True, blank=True)
c2_riega_manila_ok = models.BooleanField('Riega de manila — Circuito 2', default=False)
c2_riega_guaya_ok = models.BooleanField('Riega de guaya — Circuito 2', default=False)
c2_grapado_ok = models.BooleanField('Grapado / amarre final — Circuito 2', default=False)
c2_accesorios_ok = models.BooleanField('Accesorios instalados — Circuito 2', default=False)
```

**NO incluir** FT-046/047/931/932/918 ni Placas de señalización en Circuito 2 — F1
confirmó explícitamente que esos son del Tiro (compartidos, no se duplican por
circuito).

### Migración — `apps/construccion/migrations/0042_circuito2_checks_propios.py`

Additive, `0041_tiro_unico_ft931.py` es la última (`ls migrations/` confirmado). Migración
simple `AddField` × 6, sin `RunPython` (todos tienen default, no requiere backfill).

### Forms — `apps/construccion/forms.py`

`FaseTorreTendidoForm.Meta.fields` (líneas 195-233): agregar los 6 campos nuevos en
la sección "# Circuito 2" (línea 222-226), antes de `tendido_conductor_c2_a_ok`. El
`__init__` (líneas 239-249) ya aplica `CHECK_CLS`/`DATE_ATTRS` genéricamente por tipo
de widget — no requiere código adicional ahí.

### Template — `templates/construccion/tendido_torre.html`

Dentro del `<details>` "Circuito 2" (líneas 134-178), insertar una nueva sub-card
"CONDUCTOR — Circuito 2" ANTES del grid de 3 fases (antes de la línea 146),
replicando la estructura de Circuito 1 (líneas 49-65: bloque vestida + grid de
checks) pero acotada a los 4 checks + vestida de Cambio 1. Debe quedar DENTRO del
`x-show="aplica"` existente (línea 146-147) para que se oculte junto con el resto de
Circuito 2 cuando "Circuito 2 aplica" está desmarcado (confirmado por la nota de la
línea ~494 del mockup).

### Views — `apps/construccion/views.py`

`TendidoTorreView.form_valid` (líneas 1397-1432) ya tiene el patrón de limpieza
cuando `circuito_2_aplica` es `False` (líneas 1406-1421): agregar los 6 campos
nuevos (`c2_vestida_ok`, `c2_vestida_fecha`, `c2_riega_manila_ok`,
`c2_riega_guaya_ok`, `c2_grapado_ok`, `c2_accesorios_ok`) a esa misma limpieza y a
la lista `cambios` para `update_fields` — mismo comentario de la línea 1400-1404
aplica (la limpieza debe ir DESPUÉS de `super().form_valid()`, no antes).

### Tests — `apps/construccion/tests_issue_147.py`

Agregar sección nueva siguiendo el patrón de fixtures existentes
(`proyecto_i147`/`torre_i147`, líneas 26-52) y del test análogo
`test_post_ft931_ok_persiste` (línea ~200): `test_circuito2_checks_propios_persisten`
(POST con los 6 campos → GET recarga → valores persistidos) y
`test_circuito2_checks_se_limpian_si_no_aplica` (mismo patrón que la limpieza C2
existente, líneas 1406-1421, pero verificando los 6 campos nuevos). **Dato legacy
obligatorio:** correr contra proyecto QA real (UUID `ec2a68aa-...`, torre T-1) además
del fixture propio, para no repetir el patrón de "solo fixtures propias" que generó
bounces anteriores.

---

## Sub-item 2 — Cambio 2: Cuadrilla informativa Circuito 1

**Complexity:** trivial · **Sprint:** 1 · **Deployable solo:** sí

Solo template — **NO requiere campo BD nuevo, NO requiere cambios en forms.py ni
views.py.** `TendidoTorreView.get_context_data` (líneas 1387-1395) YA expone
`ctx['fase'] = fase` (línea 1392), y `fase.cuadrilla_tendido` ya existe como campo
del modelo (línea 1804) — es el mismo valor que se edita en la sección "Tiro"
(línea 44 del template, `{{ form.cuadrilla_tendido }}`).

### Template — `templates/construccion/tendido_torre.html`

Al tope del `<details>` "Circuito 1" (después de la línea 78, antes del grid de
3 fases en la línea 80), insertar párrafo read-only:

```html
<p class="text-sm text-gray-600 dark:text-gray-400 mb-2">
  Cuadrilla tendido
  <span class="text-xs text-purple-500">(informativo — desde Tiro)</span>:
  <strong>{{ fase.cuadrilla_tendido|default:"—" }}</strong>
</p>
```

Texto literal tomado del mockup v2 (línea ~310: "Cuadrilla tendido (informativo —
desde Tiro)"). Usar `fase.cuadrilla_tendido` (no `form.cuadrilla_tendido.value`) para
que sea explícitamente read-only (no un input deshabilitado que pueda confundirse
con editable).

### Tests

`test_circuito1_muestra_cuadrilla_informativa_readonly`: GET al detalle de torre con
`fase.cuadrilla_tendido = "Instelec"` guardado → assert `"Instelec"` aparece en el
body en la sección Circuito 1 y NO hay un segundo `<input>` editable para
cuadrilla fuera de la sección Tiro (grep de `name="cuadrilla_tendido"` debe dar
exactamente 1 ocurrencia en el HTML).

---

## Sub-item 3 — Cambio 3: Renombrar "CANT TENDIDO" → "Tendido"

**Complexity:** trivial · **Sprint:** 1 · **Deployable solo:** sí

Explícitamente distinto del renombrado A6 (Fibra OPGW→Cable de guarda, ya ✅ y
validado por `test_matriz_renombra_fibra_opgw_a_cable_de_guarda`).

### Archivos a tocar

1. `templates/construccion/tendido_matriz.html` línea 4: `{% block title %}CANT
   TENDIDO — {{ proyecto.nombre }}{% endblock %}` → `{% block title %}Tendido —
   {{ proyecto.nombre }}{% endblock %}`.
2. `templates/construccion/tendido_matriz.html` línea 34: `<h1 ...>⚡ CANT
   TENDIDO</h1>` → `<h1 ...>⚡ Tendido</h1>`.
3. `templates/components/sidebar.html` línea 398: `CANT Tendido` → `Tendido` (ítem
   de menú "6. CANT Tendido", líneas 393-400). No confundir con "Dashboard Tendido"
   (línea 407, ya dice "Tendido", sin tocar).
4. **NO hay breadcrumb block override** en `tendido_matriz.html` (confirmado —
   solo `{% block title %}` y `{% block content %}`) y **NO hay tab** en
   `_proyecto_tabs.html` que mencione Tendido — el scope de "menú" se agota en el
   ítem del sidebar (punto 3).

### Riesgo — golden stale (ver sección dedicada abajo)

El journey permanente `~/.claude/skills/qa-prod/journeys/Instelec.yaml`, escenario
`i147_tendido_entra_al_detalle` (línea ~1614-1615), hace
`assert_contains: [CANT TENDIDO]` contra `/construccion/.../tendido/` — **este
assert queda stale con Cambio 3** y debe actualizarse a `Tendido` en la misma PR
(ver `golden_stale_a_corregir`).

### Verificado que NO rompe nada más

- `apps/construccion/tests_issue_147.py` línea 477 y
  `tests/unit/test_tendido_matriz.py` línea 1: solo docstrings/comentarios con
  "CANT TENDIDO", no asserts — no se rompen.
- `tests/unit/test_sidebar_modulos.py` línea 40:
  `("construccion:tendido_lista", "CANT Tendido")` — el `_label` del tuple es
  metadata de `pytest.mark.parametrize` (nombra el test case), y
  `test_url_resuelve` (línea 57-59) **solo** assertea
  `url.startswith("/construccion/")`, nunca el label contra contenido renderizado.
  No se rompe, pero por prolijidad F3 puede actualizar el string del tuple a
  `"Tendido"` (cosmético, no bloquea el gate).

---

## Sub-item 4 — Cambio 4: Freeze-header de la matriz Tendido

**Complexity:** simple · **Sprint:** 1 · **Deployable solo:** sí

### Decisión de Miguel (componente compartido)

Cambio 4 se implementa como **componente compartido**, reusado también en
Instelec#150 (B4, matriz Actividades Finales) e Instelec#166 (B1). El agente F2 de
#150 está diseñando el componente base. **Verificado en esta sesión:** a la fecha de
este plan (2026-07-09 18:5x) **NO existe todavía** un plan con "sticky"/"freeze" en
`Instelec/SPRINTS/` ni un `agents/Instelec_150_f2.json` — el diseño del componente de
#150 aún no está listo. Por lo tanto, este plan documenta la implementación concreta
que F3 debe aplicar a la matriz Tendido AHORA (acotada, no bloqueada por #150), y dejar
explícito el patrón para que #150/#166 lo reusen — no reimplementarlo desde cero si
para cuando corra su F3 el componente de #150 ya está resuelto; en ese caso F3 de #147
debe alinear su CSS al de #150 en vez de duplicar convenciones distintas. **Citar #183
en el cierre** (issue abierto "Mejoras visuales: navbar agrupado, tablas con filas/
columnas fijas...") para que Indunnova no espere doble trabajo transversal.

### Hallazgo técnico clave para el componente compartido

`tendido_matriz.html` tiene un `<thead>` de **DOS filas** (línea 106-131: fila 1 con
`rowspan="2"` + grupos `colspan`, fila 2 con las sub-columnas). Un patrón ingenuo de
`sticky top-0` **por `<th>` individual** requeriría calcular un offset `top` distinto
para cada fila (fila 2 necesita `top: <alto de fila 1>`), lo cual es frágil si el
alto de fila 1 cambia (texto que wrappea, dark mode, etc.). **Recomendación
(verificada, navegadores modernos Chrome/Firefox/Safari soportan `position: sticky`
directamente sobre `<thead>` como bloque):** aplicar `sticky top-0 z-20` al **`<thead>`
completo** (línea 106), no a cada `<th>`. Esto pega las DOS filas juntas como una
unidad al hacer scroll vertical, sin necesidad de matemática de offsets por fila.

**CORRECCIÓN a la hipótesis de F1 de #150 (confianza "alta" pero incorrecta):** F1 de
#150 afirmó "no existe ningún patrón `position: sticky` ni freeze-header en el repo
hoy (grep 'position: sticky|sticky top-0' sobre `apps/` sin matches)". Ese grep
buscó solo en `apps/`, no en `templates/` — **SÍ existe precedente**:
`templates/lineas/mapa.html` línea 107 ya tiene
`<thead class="bg-gray-50 dark:bg-gray-900 sticky top-0">` (lista de torres del
mapa, dentro de un contenedor `<div class="max-h-64 overflow-y-auto">`). Confirma
exactamente el mismo enfoque (`sticky` en el `<thead>` completo, no por `<th>`) —
es un thead de una sola fila y sin columna congelada a la izquierda, por lo que no
necesita `z-20` ni maneja el caso de "esquina congelada"; la extensión con `z-20`
para el caso combinado top+left es específica de `tendido_matriz.html` y debe
sumarse al componente compartido, no reemplazar el hallazgo de mapa.html.

**Este hallazgo es el insumo más valioso de este plan para el componente compartido
de #150** — si la matriz de Actividades Finales de #150 también tiene thead
multi-fila, el mismo patrón (`sticky` en `<thead>`, no en `<th>`) aplica; si tiene
una sola fila de headers, el precedente de `mapa.html` aplica literalmente sin
cambios. Recomendación: extraer eventualmente esto a un snippet/convención
documentada (ej. comentario en el CLAUDE.md de Instelec o un include reusable) para
que #150/#166 no reinventen la rueda ni diverjan en el enfoque.

### Implementación concreta — `templates/construccion/tendido_matriz.html`

Línea 106, cambiar:
```html
<thead class="bg-gray-50 dark:bg-gray-900">
```
por:
```html
<thead class="bg-gray-50 dark:bg-gray-900 sticky top-0 z-20">
```

Contenedor: el scroll vertical de esta página ocurre dentro de `<main
class="flex-1 overflow-y-auto p-6">` (`templates/base.html` línea 130) — **no** en
el viewport del documento ni en un div interno con altura fija — por lo que
`position: sticky; top: 0` calculado contra ese `<main>` funciona sin necesidad de
envolver la tabla en un contenedor adicional con altura fija. El
`<div class="overflow-x-auto">` (línea 104) sigue intacto — maneja el eje
horizontal, no interfiere con el eje vertical del `<thead>` sticky.

**No tocar** el `sticky left-0` existente de la columna Torre (líneas 108, 153) — ya
funciona y debe seguir funcionando sin regresión (columna fija a la izquierda +
ahora también encabezado fijo arriba = "esquina congelada").

### Riesgo a verificar visualmente (no solo assert HTTP 200)

Corroborar con captura real que:
1. Al hacer scroll vertical con las 64 torres del proyecto QA, la franja de
   encabezados permanece visible y legible (no transparente — el `bg-gray-50
   dark:bg-gray-900` del `<thead>` debe cubrir el contenido que pasa debajo).
2. La esquina superior-izquierda (columna "Torre" del `<th>` con `rowspan="2"`,
   línea 108) se ve correctamente superpuesta sin parpadeo ni corte al hacer scroll
   simultáneo horizontal+vertical.

---

## DAG de dependencias

Los 4 cambios son **independientes entre sí** (F1 lo confirmó: `deployable_solo:
true` en los 4). Se agrupan en **un solo sprint / un solo PR / un solo deploy**
(no 4 fix_path sueltos) porque `deploy: per_node` en `PLAN.json` del run — el nodo
`Instelec#147` deploya una sola vez — y porque tratarlos como sprint unificado con
tabla de entregables es la lección anti-reproceso de este issue (ver justificación
arriba). No hay orden de ejecución obligatorio entre ellos; F3 puede implementarlos
en el orden que prefiera dentro del mismo commit/PR.

```
Cambio 1 (circuito2_checks)      ─┐
Cambio 2 (cuadrilla_informativa) ─┼─→ mismo PR → mismo deploy (instelec-api) → smoke conjunto
Cambio 3 (rename_tendido)        ─┤
Cambio 4 (freeze_header)         ─┘
```

## Golden stale a corregir

| Archivo | Línea | Assert actual | Acción |
|---|---|---|---|
| `~/.claude/skills/qa-prod/journeys/Instelec.yaml` | ~1614-1615 (escenario `i147_tendido_entra_al_detalle`) | `assert_contains: [CANT TENDIDO]` contra `/construccion/.../tendido/` | actualizar a `assert_contains: [Tendido]` en la misma PR que hace el rename (Cambio 3) |

## Riesgo global

**Medio** (heredado de F1: `riesgo: "medio"`, `tiempo_estimado_h: 5`). El único
sub-item con migración de modelo es Cambio 1 (additive, sin backfill, bajo riesgo).
Cambio 4 tiene riesgo de reconciliación con el componente compartido de #150 (no
bloqueante — implementación acotada documentada arriba) y riesgo visual (no cubierto
por HTTP 200 — requiere captura). Cambio 3 tiene riesgo de golden stale (mitigado,
ver tabla arriba).

## Validación esperada (smoke prod, paso 5 del protocolo)

1. Detalle de torre QA (T-1, `3cf707c8-306d-4e33-948c-bcf8cc220ef6`): Circuito 2
   muestra sub-card "CONDUCTOR — Circuito 2" con vestida+4 checks ANTES de las 3
   fases; togglear un check, guardar, recargar → persiste (Cambio 1). Circuito 1
   muestra "Cuadrilla tendido (informativo — desde Tiro): Instelec" (o el valor
   real guardado) sin poder editarlo ahí (Cambio 2).
2. Matriz Tendido (`/construccion/{proyecto}/tendido/`): `<title>`/`<h1>` dicen
   "Tendido"; sidebar dice "Tendido" (Cambio 3). Screenshot con scroll vertical
   mostrando encabezados fijos + columna Torre fija simultáneamente (Cambio 4).
3. Repetir contra ≥1 torre pre-existente del proyecto QA real (no solo fixture
   propio) — regla del dato legacy obligatorio.
4. Correr journey `Instelec_147.yaml` (ver abajo) + confirmar que el golden
   actualizado (`i147_tendido_entra_al_detalle`) sigue en verde con el texto nuevo.
