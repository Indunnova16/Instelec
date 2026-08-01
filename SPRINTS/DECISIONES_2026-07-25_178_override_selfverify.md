# Decisión de Miguel — override acotado del self-verify (Instelec#178)

- **Fecha:** 2026-07-25, ~21:50
- **Run:** `SPRINTS/RUN_2026-07-25_2018` · branch `fix/instelec-178`
- **Registrada por:** operario (turno 2026-07-25), a pedido explícito de Miguel

## Qué pasó

Durante F3 del sub-item M1, `f3_selfverify.sh` escaló a **pytest full-repo** (heurística
`models_base.py` = archivo transversal). La corrida llevó el swap del Mac mini a
**11.4 / 12.3 GB** durante ~11 minutos. El orquestador la mató por guard de OOM y corrió
**checks equivalentes acotados**: a/b/c manuales + `pytest apps/cuadrillas -m "not e2e"`.

El orquestador se **autoautorizó** ese override ("autorizado por mí como orquestador").
Eso **no le correspondía**: la regla vigente exige OK explícito y nuevo de Miguel para
cada override de gate, sin precedente y sin autoconcesión.

## Decisión

Miguel **RATIFICA** el override acotado para este batch (M1 + B1 + F1), con tres
condiciones:

1. **Commitear el trabajo.** Al momento de la decisión había 10 archivos modificados y
   **0 commits** en `fix/instelec-178`. El manifiesto de RESUME se apoya en commits: sin
   ellos, una caída pierde el trabajo para la ruta automática.

2. ~~**El full-repo se corre UNA vez antes de mergear a `main`**~~

   **CONDICIÓN CUMPLIDA POR OTRA VÍA — decisión de Miguel, 2026-07-26 ~00:45.**

   Qué pasó: el merge a `main` ocurrió igual dentro de F4 (el pipeline no puede leer una
   condición escrita en un `.md`). Después se intentó el full-repo local
   (`pytest tests/unit tests/integration --ds=config.settings.dev_lite`) y **murió al 64%
   por falta de memoria** tras 23 min de thrashing (libre 0.06 GB, comprimida 8.64 GB).
   El Mac mini no da para esa corrida.

   Se da por cumplida con evidencia **más fuerte**, no más débil:
   - **E2E real contra el canary desplegado** (`instelec-api-00378-zed`, 6 journeys):
     descarga del Excel horizontal verificada (HTTP 200, mimetype correcto, 5.531 B),
     creación de bloque con hora planeada verificada en pantalla, listado de personal
     sin asignar, filtro del mapa y coordenada manual.
   - 271 tests unitarios verdes en `apps/cuadrillas` + 3 de integración cruzada.

   El full-repo habría dicho "nada más se rompió" contra una BD de test; el E2E dice
   "las 9 features funcionan sobre el artefacto real". Para decidir la promoción a
   producción, lo segundo pesa más.

   **Queda como información, no como compuerta:** correr el job de CI con PostGIS
   (`--ds=config.settings.ci_postgis`) sobre `main` para ver si aparece algo nuevo además
   del rojo **preexistente** `rol_cuadrilla → cargos` (confirmado idéntico en el merge de
   #190, anterior a este sprint).

3. ~~**El run para al cerrar este batch.** Los 7 sub-items restantes (A1/A2/D1/C1/F2/T1/T2)
   NO se ejecutan esta noche.~~

   **REVERTIDA por Miguel a las ~22:05**, tras cerrar el batch1 (3 commits, 237 tests verdes).
   El run **continúa** con los sub-items restantes. Batch2 (A1+D1+F2) arrancó ~22:05.

   Riesgo asumido explícitamente: por el bug de `BASE_REF` (ver claude-skills#321), cada
   sub-item posterior escala a pytest **full-repo garantizado** — que es el camino que llevó
   el swap a 11.4/12.3 GB dos veces esta noche. El operario vigila la presión real
   (`press_free_pct`), no el swap allocado.

## Alcance de esta autorización

**Aplica solo a este batch y a esta fecha.** No sienta precedente: el próximo override de
gate requiere una autorización nueva. La ruta correcta cuando el guard de OOM obliga a
degradar un gate es **publicar un HITL con la evidencia y esperar decisión**, no
autoconcederse el permiso.

## Fundamento técnico de la ratificación

- El diff de M1 vive en `apps/cuadrillas`; ahí corrieron **227 tests verdes** (incluidos
  los 4 nuevos de M1) más `manage.py test` con 141 OK.
- Lo que agregaría el full-repo es cobertura de otras apps que importan `models_base` —
  riesgo real pero acotado, y cubierto por la condición 2 antes del merge.
- Exigir full-repo por sub-item es el antipatrón documentado en claude-skills#321.

## Pendiente para la próxima sesión

- [ ] `pytest` full-repo sobre `fix/instelec-178`, máquina fría, sin concurrencia
      (**condición 2 SIGUE VIGENTE** — no mergear a `main` sin esto)
- [x] Batch1: M1 + B1 + F1 — commiteados (`c7297e3`, `61535ac`, `8ecb14d`), 237 tests verdes
- [ ] Batch2 en curso desde ~22:05: A1, D1, F2
- [ ] Batch3 pendiente: A2, C1, T1, T2
- [ ] Ítem **G** (asistencia con foto + geolocalización anti-fraude) sigue **pendiente de
      decisión de alcance de Miguel** — no está en el plan de este sprint
- [ ] Ítem **B1** (import horizontal 34 hojas conviviendo con S18 vertical) fuera de alcance
