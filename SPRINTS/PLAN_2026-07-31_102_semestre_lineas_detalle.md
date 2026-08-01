# PLAN — Instelec#102 (bounce=3): filtro Período no reacciona en `lineas:detalle`

## Contexto (F1)

Issue #102 ("Segmentar Vanos por Semestre S1/S2/TA") ya pasó por DOS
intervenciones previas:

1. **B2.1 (mayo 2026)** — creó `VanoSemestre`, `SeguimientoVanoSemestre`,
   migración 0011 (solo cargó LN5114 con un CONTEO, no la lista real).
2. **PR #192 (bounce=2, 2026-07-22, commit `37d2808`/`dcc149e`, ya en
   `main`)** — cableó `?semestre=` en `RegistroAvanceCreateView`
   (`apps/campo/views.py`) + migración 0017 (carga la LISTA REAL desde el
   Excel del cliente, ~5600 filas `VanoSemestre` para 22/24 líneas).

**Verificado contra prod (F1/F2, 2026-07-31, solo lectura vía proxy
`127.0.0.1:5434`, DB `instelec_db`):**
- Migración 0017 aplicada: `2026-07-22 16:01:58 UTC` (`django_migrations`).
- `vano_semestres` tiene 5659 filas.
- LN733: S1=18, S2=8 (**distintos**, tal como reclama el Excel/PR#192 —
  el fix de `RegistroAvanceCreateView` SÍ funciona en prod).
- Revisión Cloud Run actual (`instelec-api-00393-lex`, 2026-07-31, 100%
  tráfico) es varios deploys posterior a `dcc149e` → el fix de #192 lleva
  días en prod, no es un problema de "deploy verde no promovido".

**Pero el cliente (comentarios 2026-07-24) reportó que el filtro "sigue sin
funcionar"** ("pongo un filtro de un semestre y no me organiza los vanos").
Esto contradice lo verificado en `campo:avance_registrar`. Causa raíz real
(F2, lectura de código): el dropdown `lineas/_filtro_semestre.html` (mismo
partial, mismo `x-data`/`irA()`) está incluido en **DOS** páginas:

| Página | View | ¿Lee `?semestre=`? |
|---|---|---|
| `campo:avance_registrar` (`/campo/avance/registrar/`) | `RegistroAvanceCreateView` | ✅ (PR #192) |
| `lineas:detalle` (`/lineas/<uuid>/`) | `LineaDetailView` | ❌ — nunca lo leyó. La única cifra de "vanos" en esa página es `linea.cantidad_vanos` (contador fijo, no filtrable). |

En `lineas:detalle`, el dropdown navega a `?semestre=S1` sobre LA MISMA
ruta (`window.location.href` solo modifica el query param), pero
`LineaDetailView.get_context_data()` nunca leía ese parámetro — el filtro
es un "gancho visual sin efecto real" **en esa página específica**,
exactamente el síntoma descrito por el cliente. Root cause confirmado en
`apps/lineas/views_b21.py` (comentario propio: *"B1.2 no agregó soporte de
`?semestre=`"*, gap conocido pero nunca cerrado para `lineas:detalle`).

## Decisión de scope (F2→F3)

No hay bug en el fix de #192 ni en los datos — se completa el wiring que
faltaba en la OTRA página donde el mismo dropdown está expuesto, para que
el filtro tenga efecto real sin importar cuál de las dos páginas use el
cliente. Fix quirúrgico: reusa `VanoSemestre.objects.avance_consolidado()`
(ya construido y testeado en B2.1, `apps/lineas/models_b21.py`), no
introduce modelos/migraciones nuevas.

## Cambios

1. `apps/lineas/views.py` — `LineaDetailView.get_context_data()`: lee y
   normaliza `?semestre=`, agrega `context['semestre']` y
   `context['avance_semestre']` (buckets s1/s2/ta/total vía
   `avance_consolidado`).
2. `templates/lineas/detalle.html` — sección "Vanos": nuevo bloque
   "Vanos por semestre" (3 tarjetas S1/S2/TA), resalta la tarjeta del
   semestre activo. No toca el contador `cantidad_vanos` existente.
3. `apps/lineas/tests_issue_102.py` — nueva clase
   `LineaDetailViewFiltroSemestreTests` (6 tests): wiring, normalización
   minúsculas, semestre inválido, discriminante S1≠S2, no-regresión de
   `cantidad_vanos`.

## Fuera de alcance (declarado, no bug)

- Reescribir el dropdown para que redirija a otra página según el
  contexto — cambiaría la navegación esperada por el usuario.
- Persistir un vano-grid completo en `lineas:detalle` (esa página nunca
  mostró un grid, solo un contador — agregar un grid completo sería
  refactor amplio, no quirúrgico).

## Evidencia (F3)

- `manage.py check`: sin issues.
- `manage.py makemigrations --check --dry-run`: sin cambios (no se tocó
  ningún modelo).
- `pytest apps/lineas/tests_issue_102.py apps/campo/tests_issue_102.py
  apps/lineas/tests_b21.py`: 80/80 OK.
- `pytest apps/lineas/ apps/campo/tests_b12.py apps/campo/tests_issue_102.py
  tests/unit/test_views.py tests/unit/test_permissions.py`: 244 passed, 1
  error preexistente y no relacionado (`TestCuadrillasViews.
  test_cuadrilla_detail_view`, FK `cargos`/`cuadrilla_miembros` — ya
  reportado como deuda preexistente en el propio PR #192, confirmado
  también en `main` sin este diff).
- Render E2E real (`django.test.Client`, login admin,
  `GET /lineas/<uuid>/?semestre=S1`): HTTP 200, contiene "Vanos por
  semestre", `context['avance_semestre']['s1']['total']==18`,
  `['s2']['total']==8` (script ad-hoc, no commiteado).
- `ruff check`/`ruff format --check`: 0 violaciones NUEVAS atribuibles a
  este diff (verificado línea por línea contra el mismo check corrido en
  `main` sin el diff — mismo conteo pre-existente en `views.py`; el único
  finding nuevo, `S106` hardcoded-password en el fixture de test, sigue el
  mismo patrón ya presente y mergeado en `apps/campo/tests_issue_102.py`).

`ready_to_deploy`: sí (bajo criterio F3) — pendiente de que Miguel autorice
el paso F4 (deploy), que está fuera de alcance de este RUN (`--no-deploy`).
