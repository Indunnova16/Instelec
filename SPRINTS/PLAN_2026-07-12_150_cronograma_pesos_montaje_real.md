# PLAN — Instelec#150 (bounce=5): Cronograma pesos + Montaje % real

## Contexto
#150 acumuló 5 bounces sobre "Aplica/No aplica por torre". Los primeros 4 ya están
resueltos y validados (toggle fila+casilla, exclusión global de torres no-aplica,
denominador de Obra Civil). El freeze-header (B1/B4) se movió a #183. Lo que queda
en ESTE issue son 2 items del QA report 2026-07-10 (comment 15), no relacionados
entre sí:

## Tabla de entregables

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| 1 | Curva "Planeado" del Dashboard Avance no se infla cuando los pesos de Cronograma no suman 100% | `curva_s_data()` normaliza por peso total; unit test con pesos 100+100 confirma tope 100 (`tests_issue_150_cronograma_pesos_montaje.py`) | ✅ |
| 2 | Guardado de Cronograma sigue funcionando igual (sin bloqueo nuevo) — decisión Miguel 2026-07-12 | `CronogramaView.post()` sin diff — no se tocó | ✅ |
| 3 | Columna "% real" de Montaje en Cronograma muestra el valor real (no "—%") | `pct_avance_real` para MONTAJE usa `_pct_montaje()` (ya excluye no-aplica); 2 unit tests + pendiente smoke E2E con proyecto QA real | ✅ (unit) — smoke E2E pendiente F5 |
| 4 | Tendido/Obra Civil NO se tocan (no reportados rotos, fuera de scope) | `git diff` confirma cero cambios en su mapeo de `pct_avance_real` | ✅ |

## Causa raíz confirmada (vía Explore agent + lectura directa de código)

**Item 1**: `ProyectoConstruccion.curva_s_data()` (models.py ~355-418) acumula
`esperado += fase.peso_pct` sin dividir por el total de pesos. Con pesos que suman
200%, la curva "planeado" queda inflada. `avance_general()` (calculators_avance_real.py)
YA normaliza (`global_pct = sum(pct*peso)/total_peso`) — mismo patrón a copiar.

**Item 3**: `ProgramacionFase.pct_avance_real` (models.py:2575-2584) mapea MONTAJE a
`ProyectoConstruccion.porcentaje_avance_montaje` — propiedad LEGACY que lee
`FaseTorre.porcentaje_montaje` (checklist de 6 campos que el editor de detalle
actual, `MontajeEstructuraTorreDetalle`, ya NO escribe — el signal de sync solo
propaga `entrega_carga_ok`). Esos 6 campos quedan en False → 0.0 → `|default:"—"`
lo esconde como "sin dato". `_pct_montaje(proyecto)` en calculators_avance_real.py
YA lee la fuente correcta (`MontajeEstructuraTorreDetalle.avance_ponderado`,
excluye `torre.aplica=False`) — reusar esa función.

## Decisión Miguel (gate 2026-07-12)
Item 1: **arreglar el cálculo (normalizar), NO bloquear el guardado** — el bloqueo
duro es una regla de negocio nueva no pedida explícitamente por el cliente, solo
preguntada. Se documenta en el comentario de cierre y se invita a Indunnova a abrir
issue aparte si de verdad quieren el bloqueo.

## Fuera de scope (explícito)
- Tendido y Obra Civil de `pct_avance_real`: NO se tocan (no reportados rotos;
  cambiar su fuente sería un cambio de comportamiento no pedido, riesgo de bounce 6).
- B1/B4 (freeze-header, eje de fechas Gantt): en #183.

## Fix

1. `apps/construccion/models.py` — `curva_s_data()`: normalizar `esperado` por
   `total_pesos = sum(f.peso_pct for f in fases) or 100` (fallback 100 si están
   todos en 0, para no dividir por cero — preserva comportamiento actual cuando
   nadie cargó pesos).
2. `apps/construccion/models.py` — `ProgramacionFase.pct_avance_real`: cambiar el
   mapeo de `'MONTAJE'` de `p.porcentaje_avance_montaje` a
   `calculators_avance_real._pct_montaje(p)`.
3. `templates/construccion/cronograma.html` — cambiar `{{ f.pct_avance_real|default:"—" }}%`
   a un check explícito `is not None` (para no esconder un 0.0% real, aunque hoy
   no debería pasar con la fuente corregida — igual es más correcto).
4. Tests: unit test para `curva_s_data()` con pesos que suman 200% (assert
   `esperado <= 100`), unit test para `pct_avance_real` MONTAJE contra datos reales
   de `MontajeEstructuraTorreDetalle`.
