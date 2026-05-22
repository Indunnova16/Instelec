# Plan Sprint — Mantenimiento de Líneas

**Fecha:** 2026-05-18
**Repo:** Indunnova16/Instelec
**Issues alcance:** #38, #39, #40, #41, #42, #43
**Autor original issues:** anasofiamc1-cpu (sin comentarios, sin adjuntos en GitHub)
**Asistente:** Claude Opus 4.7

---

## Hallazgo crítico antes de planear

Los planes de implementación que vienen escritos dentro de cada issue **están desactualizados** — fueron redactados sobre una versión anterior del repo. La realidad actual del código:

| Issue | Texto del plan dice "implementar X" | Estado real en `main` |
|---|---|---|
| #38 | "función solo agrega torres, nunca elimina" | [_sincronizar_torres()](apps/contratos/views.py#L49-L98) **ya implementa** soft-delete (`archivada=True`), reactivación, bulk_create Predial/Ambiental con `ignore_conflicts`. Signal `post_save` ya existe en [apps/ingenieria/signals.py:12](apps/ingenieria/signals.py#L12) |
| #39 | "agregar `format='%Y-%m-%d'`" | Widgets de `ContratoForm` **ya tienen** `format='%Y-%m-%d'` en [forms.py:25-26](apps/contratos/forms.py#L25-L26). `DATE_INPUT_FORMATS` ya está en [base.py:156](config/settings/base.py#L156) |
| #40 | "crear `MaintenanceRecord`, `LineHistoryEvent`, 4 pantallas mobile" | App [campo/](apps/campo/) completa: `RegistroCampo`, `Evidencia`, `ReporteDano`, `Procedimiento`, `AvanceVano`. Modelo `HistorialIntervencion` ya existe en [actividades/models.py:424](apps/actividades/models.py#L424). Template [hoja_de_vida.html](templates/lineas/hoja_de_vida.html) ya existe |
| #41 | "crear mapa Leaflet + parser KMZ + 40 líneas/4586 torres" | [templates/lineas/mapa.html](templates/lineas/mapa.html) (302 líneas, Leaflet 1.9.4 + MarkerCluster). Command [import_lines_from_kmz.py](apps/lineas/management/commands/import_lines_from_kmz.py). Modelo `Torre` con `PointField` listo. Endpoint `torres_geojson` ya expuesto |
| #42 | "agregar campo `business_unit`, context processor, navbar selector" | `unidad_negocio` ya es campo de [Contrato](apps/contratos/models.py#L29). `get_unidad_negocio()`/`set_unidad_negocio()` en [core/utils.py:130-141](apps/core/utils.py#L130). Context processor [modulo_context](apps/core/context_processors.py#L9). Endpoint `core:set_unidad_negocio`. Selector ya en [sidebar.html:16](templates/components/sidebar.html#L16). Filtrado activo en actividades/lineas/preliminares/indicadores/api |
| #43 | "crear dashboard + Chart.js + exportar Excel" | [dashboard_mantenimiento.html](templates/indicadores/dashboard_mantenimiento.html) (110 líneas) + [indicadores/views.py](apps/indicadores/views.py) (366 líneas) ya existen. `openpyxl` ya en requirements |

**Implicación:** este sprint NO es "implementar 6 features from scratch". Es **auditar completitud y cerrar gaps reales**. Esto reduce mucho el alcance.

---

## Tabla maestra de issues priorizados

| # | Issue | Tipo | Prioridad | Esfuerzo real | Bloqueos | Estado entrada |
|---|---|---|---|---|---|---|
| 1 | #39 Bug fechas vacías | 🐛 Bug | Alta | 1-2h | — | Diagnóstico (plan obsoleto) |
| 2 | #38 Bug sync torres | 🐛 Bug | Alta | 2-3h | — | Validar comportamiento actual |
| 3 | #42 Filtros globales | ✨ Auditoría | Alta | 3-4h | — | Cobertura parcial — auditar resto |
| 4 | #41 Mapa + KMZ | ✨ Completar | Alta | 4-6h | ⏸ KMZ del cliente | UI y backend listos — falta validar import + tabs |
| 5 | #40 Registros + Hoja de Vida | ✨ Completar | Alta | 6-10h | Issue 41 (Torre con coords) | Modelos listos — falta UX mobile + alertas |
| 6 | #43 Reportes + Docs | ✨ Completar | Media | 4-6h | Issue 40 (datos) | Dashboard básico — falta export + guía completa |

**Total estimado revisado:** 20-31h (vs. 80h del estimado original sumado de los issues, que asumía from-scratch).

---

## Fase 1 — Bugs rápidos (paralelizables)

### #39 — Fechas vacías al editar contrato

**Plan original obsoleto** porque el fix propuesto ya está aplicado. Hay que **reproducir** primero para saber dónde está el bug real.

**Pasos:**
1. **Reproducir en local** (BD `instelec_local` o `db.sqlite3`):
   - Crear contrato con fechas `2026-01-15` / `2026-12-31`
   - Verificar BD: `SELECT fecha_inicio, fecha_fin FROM contratos_contrato`
   - Editar el contrato y abrir DevTools → ver atributo `value` del `<input type="date">`
2. **Hipótesis a verificar** (ordenadas por probabilidad):
   - El template `templates/contratos/form.html` puede tener `value="{{ form.fecha_inicio.value|date:'d/m/Y' }}"` override
   - El input puede estar usando `instance.fecha_inicio` directo sin pasar por widget
   - Bug en otra app: `apps/construccion/forms.py` también usa `DateInput` ([reportado por Explore])
   - Browser locale o caching del navegador (descartar último)
3. **Fix surgical** según diagnóstico.
4. **Smoke E2E**: crear → editar → guardar → re-editar (3 ciclos) por `feedback_qa_smoke_crawl_maestros`.

**Riesgo:** Bajo (cambio localizado).

---

### #38 — Sincronización torres

**Plan original obsoleto.** El código actual hace soft-delete con `archivada=True` cuando se reduce, y reactiva cuando vuelve al rango. Hay que **validar si el comportamiento esperado por el cliente es ese**, o si quiere algo diferente.

**Pasos:**
1. **Reproducir escenario real**:
   - Crear contrato con 10 torres → entrar datos en Predial/Ambiental para T6..T10
   - Editar contrato a 5 torres → verificar BD: ¿T6..T10 quedan con `archivada=True`?
   - Verificar UI: ¿la vista de Ingeniería oculta o muestra las archivadas?
2. **Decisión de scope**:
   - Si UI muestra archivadas → "filas fantasmas" del issue confirmadas → filtrar por `archivada=False` en `TorreContrato.objects.filter(...)` en vistas de Ingeniería y Preliminares
   - Si UX requiere advertencia al reducir → JS en `templates/contratos/form.html` que compare valor actual vs `numero_torres` del contrato
3. **Fix surgical** + test que cubra el ciclo 10→5→10 (recuperar datos archivados).
4. **Smoke E2E** post-deploy.

**Riesgo:** Medio (afecta visualización en módulos dependientes).

---

## Fase 2 — Auditoría `unidad_negocio` (#42)

Infraestructura completa. Lo que falta es **garantizar cobertura uniforme**.

**Pasos:**
1. **Auditar cada vista lista** y validar filtrado por `unidad_negocio`:
   - ✅ Ya implementan: actividades, lineas, preliminares, indicadores, api
   - ❓ Verificar: campo, cuadrillas, ingenieria, ambiental, financiero, construccion
2. **Visibilidad del selector** en navbar: confirmar que es accesible en todas las vistas (no solo sidebar).
3. **Tests** de filtrado por contexto:
   - Login → setear MANTENIMIENTO → listar contratos → solo MANTENIMIENTO
   - Cambiar a CONSTRUCCION → listas se refrescan
4. **Documentar** cómo agregar `unidad_negocio` filter a nuevas vistas (1 página en `Documentacion/`).

**Riesgo:** Bajo. Aditivo, no modifica datos existentes.

**Sub-bloqueo de scope:** preguntar a Miguel si campos como `RegistroCampo`, `Evidencia`, `Cuadrilla` deben tener `unidad_negocio` propio (default vía `linea.contrato.unidad_negocio`) o si basta filtrar por relación FK.

---

## Fase 3 — Completar Mapa + KMZ (#41)

**Pasos:**
1. **Solicitar KMZ del cliente** (`Torres Transelca.kmz` o equivalente actual de Alcides). ⏸ Bloqueo
2. **Validar import** en local:
   ```
   python manage.py import_lines_from_kmz "<ruta>" --dry-run
   python manage.py import_lines_from_kmz "<ruta>"
   ```
   Confirmar que 40 líneas + 4,586 torres importan con coordenadas correctas.
3. **Validar mapa**:
   - Abrir `/lineas/mapa/` → confirmar render
   - Verificar clustering en zoom-out (4586 puntos)
   - Probar filtros por voltaje (34.5/110/220 kV)
   - Click en línea → detalle; click en torre → popup
4. **Tabs Mantenimiento/Construcción**:
   - El selector global de #42 ya filtra. Verificar que el mapa respeta `?unidad=MANTENIMIENTO`
   - Si no respeta → agregar filtro en `torres_geojson` y `listar_lineas`
5. **Performance**: medir tiempo carga inicial del mapa con 4586 torres; si > 3s → activar lazy load por bbox.

**Riesgo:** Medio. Carga inicial puede ser pesada; cluster mitiga.

**Entregables**: mapa funcional, import exitoso, smoke crawl en prod del módulo Líneas (lista + detalle + mapa).

---

## Fase 4 — Registros campo + Hoja de Vida (#40)

App `campo` ya tiene los modelos. `HistorialIntervencion` actúa de "LineHistoryEvent". Template `hoja_de_vida.html` ya existe.

**Pasos:**
1. **Auditar `hoja_de_vida.html`** ([templates/lineas/hoja_de_vida.html](templates/lineas/hoja_de_vida.html)):
   - ¿Renderiza timeline cronológica?
   - ¿Muestra info base de la línea (código, voltaje, cliente, ubicación)?
   - ¿Muestra estadísticas (count revisiones, severidad)?
   - Brechas → completar.
2. **Validar formulario mobile multi-step** ([templates/campo/crear.html](templates/campo/crear.html) - 638 líneas):
   - ¿Tiene flow 4 pantallas (línea → detalles → hallazgos → fotos)?
   - ¿Responsivo en mobile?
   - Brechas → ajustar.
3. **Alertas automáticas**:
   - Celery task (existe Celery): "línea sin revisión > 30 días" → email/notificación
   - Escalado automático: severidad CRÍTICO → notif a supervisor
   - Sugerencia: usar `apps/campo/tasks.py` (ya existe).
4. **Permisos por rol**: validar que `inspector_mantenimiento` puede crear; `supervisor` puede ver dashboard.
5. **Smoke E2E** completo: crear revisión → ver en hoja de vida → ver en mapa con color por severidad.

**Riesgo:** Medio. Cambios de UX visibles al cliente.

---

## Fase 5 — Reportes + Docs (#43)

**Pasos:**
1. **Auditar [dashboard_mantenimiento.html](templates/indicadores/dashboard_mantenimiento.html)** (110 líneas — probablemente esqueleto):
   - Métricas existentes vs requeridas (total líneas, vencidas >30d, avisos pendientes, inspecciones mes, severidad)
   - Gráficas existentes vs requeridas (tendencia 6 meses, distribución por tipo, cuadrillas activas, voltaje)
2. **Export Excel**: agregar botón "Exportar" usando `openpyxl` (ya disponible). Reusar patrón si existe en `apps/contabilidad`/`apps/financiero`.
3. **Filtros por rango fecha** en dashboard.
4. **Ampliar [guia-usuario-mantenimiento.md](Documentacion/guia-usuario-mantenimiento.md)** (82 → ~250 líneas):
   - Cómo registrar revisión móvil (con screenshots)
   - Cómo interpretar timeline
   - Cómo leer alertas
   - Cómo usar el mapa
   - Troubleshooting + referencia rápida
   - Screenshots: tomar en local antes del deploy
5. **Chart.js**: agregar via CDN al template del dashboard (no instalar en requirements).

**Riesgo:** Bajo. Aditivo.

---

## Convenciones por protocolo Indunnova

- **No cerrar issues** — al terminar, comentar con checklist 🟢/🟡/🔵 + asignar `Indunnova` (`gh issue edit --add-assignee Indunnova`)
- **Test contra dato legacy** obligatorio en cada fix (issue #38 especialmente — datos antiguos de Predial/Ambiental)
- **Deploy** via `gh workflow run deploy-cloudrun.yml --ref main` + `gh run watch`
- **Smoke prod**: crawlear lista+nuevo+detalle de **Contratos, Líneas, Actividades, Campo, Indicadores** (no solo el módulo tocado) — `feedback_qa_smoke_crawl_maestros`
- **Causa raíz** vía BD prod (psql `postgres-consolidated` → BD instelec) y logs Cloud Run; nunca shotgun fix
- **Sin costos GCP** sin autorización (`feedback_sin_costos_cloud`)
- **Sin anglicismos** en UI o comentarios (`feedback_no_anglicismos`)

---

## Secuencia recomendada de ejecución

**Día 1 (3-5h):** Fase 1 — Bugs #38 y #39. Reproducir → fix → smoke → deploy → comentar issue → asignar Indunnova.

**Día 2 (3-4h):** Fase 2 — Auditoría #42. Documentación de patrón + 1 PR cubriendo apps faltantes.

**Día 3 (4-6h):** Fase 3 — Mapa #41. Requiere KMZ del cliente — **pedir antes de iniciar**.

**Día 4-5 (6-10h):** Fase 4 — Hoja de vida + mobile #40.

**Día 6 (4-6h):** Fase 5 — Dashboard + docs #43.

---

## Preguntas para Miguel antes de ejecutar

1. **#38**: ¿El cliente quiere ver torres archivadas marcadas (ej. "T6-OBSOLETA") o quiere que desaparezcan totalmente cuando se reduce el número de torres?
2. **#40**: ¿Alcides ya está usando el módulo actual o este es greenfield para él? Eso define cuánta validación móvil necesitamos.
3. **#41**: ¿Tienes el KMZ "Torres Transelca.kmz" actualizado? El doc del issue lo describe pero no está en el repo.
4. **#42**: Para apps `cuadrillas`, `financiero`, `construccion` — ¿la unidad de negocio se hereda vía contrato (filtro indirecto) o debe ser campo propio en esos modelos?
5. **Orden**: ¿Confirmas la secuencia bugs → #42 → #41 → #40 → #43, o prefieres priorizar diferente (ej. #41 antes por el deadline del cliente)?
