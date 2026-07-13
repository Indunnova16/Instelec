# PLAN — Instelec#183 (mejoras visuales, ejecutado con 4 agentes en paralelo)

## Alcance (tras el consolidado del cliente 2026-07-10, #147/#166 ya cerrados aparte)

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| 1 | Navbar agrupado: 3 grupos colapsables nuevos (Tendido/Obra Civil/Montaje), mismo patrón que Financiero | Journey E2E: clic expande grupo Tendido, muestra sus 3 sub-items | ⬜ |
| 2 | Freeze-header: causa raíz encontrada y corregida en 13 templates (4 rotos + 9 sin implementar) | Journey E2E + inspección visual de screenshots post-scroll (Actividades Finales, Tendido) | ⬜ |
| 3 | Form Obras de Protección cerca del clic (no arriba de la página) | Ya resuelto en #166, sin cambios acá | ✅ (previo) |
| 4 | SPT y Pintura: clic-en-torre reemplaza columna Editar | Journey E2E: clic en torre navega al detalle, columna Editar ausente | ⬜ |
| 5 | Reubicar acceso a Cronograma al dashboard general del proyecto | Journey E2E: tarjeta nueva navega a /cronograma/ | ⬜ |

## Causa raíz freeze-header (confirmada por agente Explore, ver investigación previa)
`position: sticky top-0` en el `<thead>` se ata al ancestro scrolleable MÁS CERCANO.
Un `<div class="overflow-x-auto">` interno activa implícitamente `overflow-y: auto`
(spec CSS: cuando un eje es auto/hidden y el otro visible, el visible también pasa
a auto) — pero como ese div no tiene altura fija, NUNCA scrollea de verdad
(scrollTop=0 siempre), así que el sticky queda atado a un contenedor muerto en vez
del scroll real de la página (`main#main-content` en base.html). Un `overflow-hidden`
en el wrapper exterior (para redondear esquinas) agrava el mismo problema.

**Fix (13 archivos, mecánico):** `overflow-x-auto` → `overflow-x-auto overflow-y-visible`
en el div interno; quitar `overflow-hidden` del div exterior; agregar `sticky top-0 z-20`
al thead donde faltaba.

## Ejecución
4 agentes F3 en paralelo, archivos disjuntos, sin colisión:
- Agente 1: freeze-header (13 templates)
- Agente 2: navbar agrupado (sidebar.html)
- Agente 3: SPT y Pintura clic-en-torre (spt_pintura_index.html)
- Agente 4: tarjeta Cronograma (proyecto_dashboard.html)

## Verificado post-agentes
- `manage.py check` + `makemigrations --check --dry-run`: limpio.
- Suite relevante (tests_issue_147, tests_issue_150_actividades_finales_cierre,
  test_issue_123_sidebar_financiero, test_sidebar_modulos, test_issue_164,
  test_spt_pintura, tests_issue_154, test_issue_149): sin regresiones.

## Hallazgo no solicitado (fuera de scope)
`spt_pintura_index.html` tiene un `<td>` pre-existente con DOS atributos `class=""`
duplicados (HTML inválido, el navegador ignora el primero) — no tocado por este fix
(no relacionado, no reportado por el cliente). Candidato a limpieza aparte.

## Nota de herramienta
El linter de journeys (`lint_journey.py`) marcó una advertencia (no bloqueante) en
el journey de freeze-header: la aserción `assert_visible_count` en `thead` es
técnicamente tautológica (is_visible() de Playwright no chequea posición en
viewport, solo CSS display/visibility) — el DSL de `run_journey.py` no tiene hoy
una aserción de "elemento dentro del viewport" (equivalente a `assert_canvas_painted`
pero para posición, no pintura). Se compensa con inspección VISUAL manual real de
los screenshots post-scroll. Se identificó el fix (nueva acción `assert_in_viewport`
vía `getBoundingClientRect()`) pero no se aplicó — modifica el árbol compartido de
`claude-skills`, fuera del alcance de este issue de Instelec. Candidato a issue en
claude-skills (kaizen) para una futura sesión.
