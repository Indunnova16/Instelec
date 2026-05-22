# PLAN — UIs faltantes: Obra Civil, Montaje, Tendido

**Fecha**: 2026-05-22
**Autor**: Miguel + Claude
**Origen**: cliente reporta "no se desplegó" → diagnóstico real es scope incompleto. El deploy de ayer (commits #53–#58 + bff95a4) creó el **schema** (40+ campos en `FaseTorre` + 6 bloques de `PataObra`) pero las **UIs** de Obra Civil, Montaje y Tendido nunca se construyeron como tabs/módulos navegables.

## Estado actual vs esperado

| Cliente espera | Estado real |
|---|---|
| Tab "Obra civil" | Migración 0003 aplicada (`PataObra` con 6 bloques + `CerramientoDetalle`/`ExcavacionDetalle`/`SoladoDetalle`/`AceroDetalle`/`VaciadoDetalle`/`CompactacionDetalle`). **Sin form, sin vista, sin tab.** |
| Tab "Montaje" | Migración 0004 (`FaseTorre.seleccion_estructura_*`, `transporte_*`, `prearmado_*`, `montaje_*`, `torsion_*`, `entrega_wsp_*`, `entrega_carga_*`, `pct_montaje`, + SPT + Pintura). **Sin UI.** |
| Tab "Tendido" | Migración 0004 (`FaseTorre.vestida_*`, `riega_manila/guaya_ok`, FT-046/047/932/918, regulación, conductor C1 A/B/C, OPGW izq/der, conductor C2 A/B/C, guarda, `pct_tendido`). **Sin UI.** |
| Dashboard financiero | **Ya desplegado** como tab "💰 Dashboard fin" → `/construccion/<id>/dashboard-financiero/`. Solo validar que carga. |

## Alcance Iteración 1 — entrega mínima funcional

3 tabs nuevas con patrón **lista por torre → editar por torre** (mismo patrón que Kits / Protecciones / Pruebas).

### 1. Tab `🏗️ Obra civil` — `/construccion/<proyecto>/obra-civil/`

- **Lista** `ObraCivilListView` (TemplateView): tabla torres × KPI OC.
  - Columnas: `numero` · `cuadrilla_civil` · `% avance OC` (`porcentaje_avance_civil` ya existe) · `bloque actual` (max de los 4 patas) · `alarma materiales` (rojo si alguna pata) · `cilindros pendientes` · acción "Detalle 4 patas".
  - Filtro: solo torres con `puede_iniciar_obra_civil=True` (toggle).
- **Detalle** `ObraCivilTorreView` (TemplateView con 4 forms): muestra patas A/B/C/D en tabs verticales/acordeón.
  - Por pata, secciones colapsables por bloque secuencial:
    1. Cerramiento (`cerramiento_finalizado_ok`, `cerramiento_fecha`)
    2. Excavación (`tipo_excavacion`, `aplica_pilotes`, `excavacion_*`)
    3. Solado (`solado_*`)
    4. Acero (`acero_*`, `acero_solicitado_kg`, `acero_instalado_kg`, alerta `desviacion_acero_pct ≥ 5%`)
    5. Vaciado (`vaciado_*`, `concreto_*`, cilindros 7/14/21/51d MPa con alerta `cilindros_pendientes`)
    6. Compactación (`relleno_compactacion_*`, `spt_base_ok`, `spt_modulos_ok`)
  - Cada bloque tiene su POST que guarda solo sus campos (form parcial vía HTMX o submit por sección).

### 2. Tab `🔩 Montaje` — `/construccion/<proyecto>/montaje/`

- **Lista** `MontajeListView`: tabla torres × hitos.
  - Columnas: `numero` · `funcion_torre` · `tipo_torre_montaje` · `cuadrilla_montaje` · `recepción patio` (✓/fecha) · `pct_completitud_estructura` · `prearmado_pct` · `montaje_ok` · `torsion_ok` · `entrega_wsp_ok` · `entrega_carga_ok` (gate Tendido) · `pct_montaje` · `spt_pct` · `pintura_ft912_ok` · acción "Editar".
  - Filtro: torres con OC completa (`obra_civil_completa=True`) — mismo gate del modelo.
- **Detalle** `MontajeTorreView` (UpdateView sobre `FaseTorre`): un solo form en 3 secciones:
  - Info estructura: `funcion_torre`, `tipo_torre_montaje`, `cuerpo_torre`.
  - Montaje: 8 hitos OK + fechas + crews + `pct_completitud_estructura` + `observaciones_recepcion`.
  - SPT: cantidades cable/pólvora + diferencia + FT-068/029 + informe + `spt_pct` + alerta `spt_polvora_sobreconsumo`.
  - Pintura: `pintura_ft912_ok` + observaciones.

### 3. Tab `⚡ Tendido` — `/construccion/<proyecto>/tendido/`

- **Lista** `TendidoListView`: tabla torres × hitos.
  - Columnas: `numero` · `tramo_tendido` · `cuadrilla_tendido` · `vestida_torres_ok` · `regulacion_flechado_ok` · Conductor C1 (A/B/C semáforos) · OPGW (izq/der) · Conductor C2 (A/B/C) · Guarda · `pct_tendido` · acción "Editar".
  - Filtro/badge: deshabilitar acción "Editar" en torres con `puede_iniciar_tendido=False` (mostrar tooltip "Falta entrega para carga del Montaje").
- **Detalle** `TendidoTorreView` (UpdateView sobre `FaseTorre`): un solo form en 4 secciones:
  - Vestida + sub-flujo conductor (riega manila/guaya, FT-046/047/932/918, regulación, grapado, accesorios, placas, distancia vano).
  - Circuito 1 (3 fases A/B/C OK+fecha) + OPGW (izq/der OK+fecha).
  - Circuito 2 (3 fases A/B/C OK+fecha).
  - Cable de guarda + regulación final + cuadrilla + observaciones + `pct_tendido`.

## Archivos a tocar

### Nuevos
```
templates/construccion/
├── obra_civil_lista.html       (~80 líneas)
├── obra_civil_torre.html       (~180 líneas, 6 bloques colapsables × 4 patas)
├── montaje_lista.html          (~70 líneas)
├── montaje_torre.html          (~140 líneas, 3 secciones)
├── tendido_lista.html          (~70 líneas)
└── tendido_torre.html          (~150 líneas, 4 secciones)
```

### Modificar
```
apps/construccion/forms.py     (+3 ModelForms: PataObraBloque*Form / FaseTorreMontajeForm / FaseTorreTendidoForm)
apps/construccion/views.py     (+6 views: 3 ListView/TemplateView + 3 UpdateView/TemplateView)
apps/construccion/urls.py      (+6 routes con namespaces `obra_civil_lista`, `obra_civil_torre`, `montaje_lista`, `montaje_torre`, `tendido_lista`, `tendido_torre`)
templates/construccion/_proyecto_tabs.html  (+3 tabs entre "Torres" y "Protecciones")
```

### Tests (nuevos)
```
apps/construccion/tests.py — agregar:
- test_obra_civil_lista_renderiza
- test_obra_civil_torre_render_4_patas
- test_obra_civil_guardar_bloque_cerramiento
- test_obra_civil_alerta_materiales_acero
- test_montaje_lista_renderiza
- test_montaje_torre_guarda_entrega_carga_habilita_tendido
- test_tendido_lista_renderiza
- test_tendido_torre_bloqueado_si_no_carga
- test_tendido_torre_guarda_3_fases
```

Test contra dato legacy: cada test usa al menos 1 torre creada vía fixture pre-migración 0003/0004 (campos en default NULL/False/0).

## NO se requiere

- **Migraciones**: 0003 y 0004 ya aplicadas. Defaults manejan datos legacy.
- **Crear PataObra/FaseTorre en runtime**: `TorreCreateView.form_valid()` ya los crea. Para torres legacy sin patas/fase: `get_or_create` defensivo en cada list view.
- **Permisos nuevos**: reusar `allowed_roles=['admin','director','coordinador']`.
- **Cambios al modelo**: cero. Todo lo que hace falta está en `models.py` líneas 387-859.

## Plan de ejecución por sub-tareas (orden, ~6h total estimado)

| # | Tarea | Estimado | Bloqueos |
|---|---|---:|---|
| 1 | Forms (3 ModelForms con Tailwind, sección por sección) | 60min | — |
| 2 | Views Obra Civil (lista + detalle 4 patas + POST bloque) | 90min | — |
| 3 | Template `obra_civil_lista.html` + `obra_civil_torre.html` | 60min | task 2 |
| 4 | Views Montaje + templates (lista + torre) | 60min | task 1 |
| 5 | Views Tendido + templates (lista + torre) | 60min | task 1 |
| 6 | URLs + agregar 3 tabs en `_proyecto_tabs.html` | 15min | tasks 2-5 |
| 7 | Tests (9 tests pytest + run local) | 45min | tasks 2-5 |
| 8 | Pre-deploy lint (skill `/pre-deploy` portafolio) | 5min | task 7 |
| 9 | Commit + push + workflow_dispatch deploy | 5min | task 8 |
| 10 | Smoke E2E prod con `qa_claude` (Playwright) | 20min | task 9 |
| 11 | Comentar en issues #53 #56 #58 + asignar `Indunnova` | 10min | task 10 |

## Smoke E2E prod (post-deploy obligatorio)

Login: `qa_claude@instelec.com` / `Margarita28` en `/usuarios/login/`.

Crawlear (HTTP 200 esperado en todo):
1. `/construccion/` — lista proyectos
2. `/construccion/<proy>/` — dashboard proyecto (no romper)
3. `/construccion/<proy>/obra-civil/` ← nueva
4. `/construccion/<proy>/obra-civil/<torre>/` ← nueva
5. `/construccion/<proy>/montaje/` ← nueva
6. `/construccion/<proy>/montaje/<torre>/` ← nueva
7. `/construccion/<proy>/tendido/` ← nueva
8. `/construccion/<proy>/tendido/<torre>/` ← nueva
9. `/construccion/<proy>/torres/` — no romper
10. `/construccion/<proy>/dashboard-financiero/` — validar que ya carga (lo que cliente esperaba ver)
11. `/construccion/<proy>/cronograma/`, `/financiero/`, `/cilindros/` — no regresiones

Editar 1 campo por cada nueva tab y verificar persistencia (POST + GET refresca).

Test contra dato legacy: usar 1 torre creada antes de mayo 2026 (preexistente) y verificar que se renderiza sin errores aunque sus campos nuevos estén en NULL/False.

## Riesgos / consideraciones

- **Torres legacy sin `FaseTorre`/`PataObra`**: si en prod hay torres creadas vía loader/import que se saltaron `TorreCreateView`, hay que correr una vez `get_or_create` para todas. Mitigación: management command idempotente `python manage.py construccion_seed_relaciones_torres` (opcional, agregar si smoke detecta torres rotas).
- **Tabla de tendido es ancha (12+ columnas)**: usar `overflow-x-auto` y agrupar (C1, C2, OPGW, Guarda como cabeceras).
- **Form de Montaje es largo** (~25 campos): partir en `<details>` colapsables por sección.
- **Bloque Vaciado de OC necesita 4 cilindros**: si vaciado_fecha es NULL, deshabilitar inputs MPa (no tiene sentido cargarlos).

## Iteración 2 (NO entra en este sprint, solo registrada)

- Edición masiva de fechas por cuadrilla.
- PDF de planilla por torre × módulo (ya existe pattern en `apps/construccion/planillas.py` + `templates/construccion/planillas/`).
- Dashboard de traslape paralelo (usa `fases_en_curso` property que ya existe).
- Drag & drop de prioridad por tramo.

## Cierre — comentario para issues

Después del deploy + smoke OK:
- Issues #53, #54, #55 (Obra Civil): comentar `🟢 UIs desplegadas en prod` + lista URLs + screenshots + datos legacy probados + asignar Indunnova.
- Issues #56, #57: comentar para Montaje + SPT + Pintura.
- Issue #58: comentar para Tendido.
- NO cerrar (cliente cierra al validar).

---

**Estimado total**: 5–7 horas de implementación + 30 min smoke + 15 min cierre = ~7h.
**Sin BD prod**: no requiere autorización ni cambios de schema.
**Sin costos adicionales GCP**: misma revisión Cloud Run, sin instancias nuevas.
