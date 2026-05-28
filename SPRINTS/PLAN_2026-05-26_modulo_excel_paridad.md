# PLAN — Re-hacer Obra Civil (#74) y Montaje (#76) con paridad al Excel del cliente

**Fecha**: 2026-05-26
**Autor**: Miguel + Claude (planning agent)
**Repo**: Indunnova16/Instelec
**Issues**: #74 (Obra Civil — CANT OOCC), #76 (Montaje — CANT MONTAJE)
**Origen**: Ana Sofía documentó en los issues la estructura completa del Excel (`Documentacion/Obra civil.xlsx`, `Documentacion/Montaje.xlsx`) — el primer pass entregó matrices simplificadas (6 columnas / 4 etapas) cuando el cliente espera paridad campo-a-campo con el Excel (100 columnas OOCC, 30 columnas MONTAJE).
**Sucesor de**: `PLAN_2026-05-22_uis_oc_montaje_tendido.md` (entregó iteración 1 simplificada).

---

## 0. Resumen ejecutivo

- **Approach elegido**: **C** — reemplazar el simplificado por modelos detallados con paridad Excel, y dejar la matriz actual como **vista RESUMEN auto-calculada** que derive su % por fase de los detalles. Las URLs `/obra-civil/` y `/montaje/` siguen siendo las puertas de entrada (el cliente no aprende rutas nuevas), pero su contenido cambia.
- **Topología /modulo** (4 bloques, B2∥B3 en paralelo):
  - **B1** (scaffolding): pestañas reusables, breadcrumb, pre-asignación de números de migration, partial stubs sin `{# multilínea #}`.
  - **B2** (Obra Civil paridad) ∥ **B3** (Montaje paridad).
  - **B4** (resumen auto-calculado + integración dashboards #75/#77 + E2E final).
- **Modelos nuevos**: 2 (`ObraCivilTorreDetalle`, `MontajeEstructuraTorreDetalle`) + 1 enum (`FuncionMontajeTorre`).
- **Modelos modificados**: `ObraCivilTorre` y `MontajeEstructuraTorre` → se convierten en **caches calculados** (avance_* deja de ser editable manual; se recalcula desde el detalle vía signal o property).
- **URLs**: 0 nuevas obligatorias (todo bajo `/obra-civil/` y `/montaje/`). +4 internas para drill-down a sección/pestaña.
- **Templates nuevos**: 10 (5 OC: 1 índice de pestañas + 6 pestañas tab content + 1 resumen; 5 MONTAJE: 1 índice + 7 secciones + 1 resumen). Templates legacy (`obra_civil_matriz.html`, `montaje_matriz.html`) se RE-PROPÓSITAN como resumen.
- **Estimado total**: 5–6 días-Claude (B1: 0.5d, B2: 2d, B3: 2d, B4: 1d, buffer integración +0.5d).
- **Gotchas críticos**: pre-asignar números de migration (B2=0019, B3=0020), prohibir `{% include ... ignore missing %}`, prohibir `{# multi-línea #}` en partials, respetar allowlist de 13 acciones del runner /qa-prod, verificar nombres de tabla con `psql \dt construccion_*` antes de emitir journey YAML.

---

## 1. Decisión arquitectónica: por qué Approach C

| Aspecto | A (reemplazo duro) | B (coexistir) | **C (reemplazar + resumen)** ✅ |
|---|---|---|---|
| URLs que el cliente conoce | rompe `/obra-civil/` y `/montaje/` (cambio de semántica sin warning) | preserva ambas + agrega `/obra-civil-detalle/` (cliente no sabe cuál usar) | **preserva slug y cambia contenido a vista útil (resumen calculado)** |
| Datos legacy en prod | drop tablas (riesgo pérdida) | duplica capa (matriz vieja queda dead-code) | **migración suave: pesos del proyecto sobreviven, avances manuales se mueven a defaults del detalle** |
| Dashboards #75/#77 ya conectados | rompe inputs del dashboard | sigue leyendo matriz vieja (NO refleja datos detallados) | **dashboard lee el resumen auto-calculado → siempre coherente** |
| Sidebar (`obra-civil`, `dashboard-obra-civil`, `montaje`, `dashboard-montaje`) | requiere relabel | requiere relabel y add nuevo item | **NO cambia sidebar** (4 entries existentes mantienen URLs) |
| Soporte a `OPERARIO_ROLES` y `filtrar_torres_por_cuadrilla` | tienes que reaplicarlo | duplicado | **se hereda igual** |
| Esfuerzo | alto (rompe contratos) | medio (más código) | **medio (pero contrato preservado)** |
| Riesgo regresión | alto | bajo | **medio (sólo el cálculo del resumen)** |

C gana porque preserva 3 contratos críticos: la URL que el cliente memorizó, los inputs del dashboard que ya consume el resumen, y los roles operario/admin sin redoble. El riesgo se concentra en un solo punto (el cálculo del resumen) que es testeable unit.

**Salvedad**: si la data manual en `ObraCivilTorre.avance_*` o `MontajeEstructuraTorre.avance_*` ya tiene valores capturados por el cliente en prod, hay que preservarlos como SEED de los detalles (no perderlos). Ver §3 (migración de datos).

---

## 2. Inventario de campos derivado del Excel real

> Fuente: `Documentacion/Obra civil.xlsx` hoja **CANT OOCC** (100 columnas) y **OOCC** (dashboard resumen).
> Fuente: `Documentacion/Montaje.xlsx` hoja **CANT MONTAJE** (30 columnas) y **MONTAJE** (dashboard resumen).
> Las dos `.xlsx` contienen el mismo workbook (mismas 7 hojas).

### 2.1 CANT OOCC — 100 columnas reales

Pesos (fila R2 del Excel, suman 1.00):
- Y (Excavación) = 0.4
- AR (Solado) = 0.05
- BE (Acero) = 0.1
- CK (Vaciado) = 0.4
- CR (Compactación) = 0.05
- Cerramiento NO tiene peso explícito en el Excel (está dentro del bloque de Excavación) — **decisión**: dejarlo configurable (default 0%) y advertir al cliente.

Total columnas por **sección**:

| # | Sección | Cols Excel | Campos Django (resumen) |
|---|---|---|---|
| Identidad | TORRE (B), DISEÑO CONSTRUIDO (C), Replanteo topo (D), Patas (E) | 4 | FK + diseño constructivo (helicoidal/zapatas/etc), boolean replanteo topo, pata (A/B/C/D) |
| **Cerramiento** (F–J) | Madera (F), lona/alambre (G), señalización/baño (H), notas (I), finalizado (J) | 5 | 2 PositiveSmallInteger + 1 boolean + 1 textfield + 1 boolean |
| **Excavación** (K–Z) | Cuadrilla (K), FT-022 (L), FT-023 (M), FT-058 (N), tipo excavación (O), metros m³ (P), penetrómetro (Q), FT-922 (R), FT-926 (S), FT-927 (T), FT-925 (U), FT-928 (V), FT-929 (W), monitoreo arqueológico (X), ejecución (Y, peso 0.4), observaciones (Z) | 16 | 1 CharField + 12 booleans (formatos) + 1 Decimal m³ + 1 choice (manual/maquina/pila helicoidal) + 1 choice (en ejecución/liberada) + 1 % avance + 1 TextField |
| **Solado** (AA–AT) | Ingreso materiales (AA), 4 sub-bloques (agua/arena/grava/cemento) × 4 campos (calc/real/desv/obs) = 16, ejecución (AR, peso 0.05), observaciones (AS), soldadura prolongas STUB (AT) | 20 | 1 choice ingreso + 4×(Decimal calc + Decimal real + Decimal desv computed + TextField obs) + 1 % avance + 1 TextField + 1 boolean |
| **Acero** (AU–BF) | Ingreso acero (AU), FT-028 (AV), FT-930 (AW), corte/flejado (AX), armado (AY), SPT/varilla (AZ), kg solicitado (BA), kg instalado (BB), desv kg (BC), obs (BD), ejecución (BE, peso 0.1), obs (BF) | 12 | 1 choice + 5 booleans (formatos+armado) + 2 Decimal kg + 1 Decimal desv computed + 2 TextField + 1 % avance |
| **Vaciado en Concreto** (BG–CL) | FT-916 (BG), nivelación STUB (BH), encofrado (BI), ingreso materiales (BJ), IT-380 (BK), FT-056 (BL), tipo concreto (BM), MPa teórica (BN), 4 sub-bloques agua/arena/grava/cemento × 4 (calc/real/desv/obs) = 16, slump (CE), fecha vaciado (CF), fecha cilindros (CG), inspección final stub (CH), encargado puntas diamante (CI), desencofrado/resane (CJ), ejecución (CK, peso 0.4), obs (CL) | 32 | 6 booleans formatos + 1 choice tipo concreto + 1 Decimal MPa + 4×(Decimal calc + Decimal real + Decimal desv + TextField) + 1 boolean slump + 2 DateField + 1 boolean + 1 CharField encargado + 1 boolean + 1 % avance + 1 TextField |
| **Compactación** (CM–CS) | FT-914 (CM), suelo natural (CN), suelo cemento (CO), suelo préstamo (CP), volumen m³ (CQ), finalizada (CR, peso 0.05), obs (CS) | 7 | 1 boolean formato + 3 booleans tipo + 1 Decimal m³ + 1 % avance + 1 TextField |
| Trailer | TOTAL (CT, formula SUMPRODUCT), ejecutado por (CU), comentario (CV) | 3 | calculado + CharField + TextField |

**Granularidad clave**: el Excel tiene **una fila por pata × torre** (R5–R8 muestran E1 con patas A/B/C/D), no una fila por torre. Esto coincide con la granularidad legacy `PataObra` que ya tenemos. **Decisión**: `ObraCivilTorreDetalle` tendrá granularidad torre × pata (igual que PataObra). 4 patas × 64 torres = 256 filas.

### 2.2 CANT MONTAJE — 30 columnas reales

Pesos (fila R2 del Excel, suman 1.00):
- I (Estructura en sitio) = 0.1
- L (Prearmada) = 0.2
- R (Torre montada) = 0.45
- W (Revisada) = 0.25

(Coincide con los pesos que ya tiene el modelo simplificado.)

| Sección Excel | Cols Excel | Campos Django |
|---|---|---|
| **1. Info General** (A–D) | Estructura (A), Función (B fórmula), Tipo (C), Cuerpo (D) | FK a TorreConstruccion (la estructura = numero de torre); Función auto-calculado @property (`Suspensión` si tipo ∈ {A, A especial} else `Retención`); CharField tipo (choices A/A especial/B/C/D/Pórtico/...); CharField cuerpo (C4/C5/C6/...) |
| **2. Recepción Patio** (E–G) | Fecha recibida (E), patiero sin pendientes (F), observaciones pendientes (G) | DateField + BooleanField + TextField |
| **3. Pre-armado** (H–M) | Encargado (H), estructura en sitio (I, peso 0.1), fecha inicio (J), fecha fin (K), prearmada (L, peso 0.2), % avance (M) | CharField + Boolean + 2 DateField + Boolean + DecimalField % |
| **4. Montaje** (N–S) | Encargado (N), fecha inicio (O), fecha fin (P), días montaje (Q computed = P-O), torre montada (R, peso 0.45), observaciones (S) | CharField + 2 DateField + @property days + Boolean + TextField |
| **5. Controles Calidad** (T–X) | FT-032 (T), FT-913 (U), FT-920 (V), Revisada (W, peso 0.25), Entregada para carga (X) | 5 Boolean |
| **6. Pesos** (Y–Z) | Peso diseño kl (Y), peso instalado kl (Z) | 2 DecimalField + @property validación ±5% (warning, no bloqueante per Ana Sofía) |
| **7. Facturación** (AA–AC) | Total estructuras (AA, formula SUMPRODUCT), facturada a dueño (AB), facturada por contratista (AC) | @property avance_ponderado + 2 Boolean (con AC: ¿booleano? El Excel real tiene strings tipo "Cruz"/"Higuita"/"Instelec" → CharField facturador, no boolean) |

**Nota importante sobre AC**: el plan de Ana Sofía dice `0/1`, pero el Excel real R3–R8 tiene strings ("Cruz", "Higuita", "Instelec", "Cruz") — son **nombres de subcontratistas**. **Decisión**: usar CharField `facturado_por_contratista` (max_length=100, blank=True). Más útil para reporting.

**Granularidad**: una fila por torre completa (no por pata). Modelo OneToOne TorreConstruccion ↔ MontajeEstructuraTorreDetalle.

### 2.3 Diferencias vs plan Ana Sofía (a confirmar con cliente, pero proceder con Excel real)

| Campo | Ana Sofía dijo | Excel real | Plan |
|---|---|---|---|
| AC Facturadas por contratista | boolean 0/1 | string (nombre) | usar CharField (más útil) |
| AC vs AB | "0/1" ambos | AB es 0/1, AC es nombre | AB BooleanField, AC CharField |
| Validación pesos Y/Z | "Z ≥ Y" (no puede pesar menos) | spec dice ±5% | **mantener regla ±5% (warning); fórmula = `|Z-Y|/Y ≤ 0.05`** |
| OC pestañas | "estructura como Ingeniería con pestañas dinámicas" | Excel es 1 hoja única CANT OOCC con secciones | usar PESTAÑAS UI (Cerramiento/Excavación/Solado/Acero/Vaciado/Compactación) que filtran columnas del mismo modelo (no 6 modelos distintos) |

---

## 3. Modelos Django — diseño detallado

### 3.1 Modelo `ObraCivilTorreDetalle` (nuevo)

Granularidad: **torre × pata** (4 patas: A/B/C/D). 64 torres × 4 = 256 filas.

Total campos: ~110 (5 cerramiento + 16 excavación + 20 solado + 12 acero + 32 vaciado + 7 compactación + 3 trailer + 5 identidad).

Secciones, derivadas literalmente del Excel:

- **Cerramiento** (5): `cerr_madera_un`, `cerr_lona_m`, `cerr_senalizacion_ok`, `cerr_notas`, `cerr_finalizado_ok`.
- **Excavación** (16): `exc_cuadrilla`, `exc_ft022_ok` (MARCACIÓN), `exc_ft023_ok` (PLANILLA), `exc_ft058_ok` (CONTROL EXCAVACIONES), `exc_tipo` choices manual/maquina/helicoidal, `exc_metros_m3`, `exc_penetrometro_ok`, `exc_ft922_ok` (CONCEPTO ENTIBADO), `exc_ft926_ok` (MARCACIÓN PILOTES), `exc_ft927_ok` (REGISTRO CANTIDADES), `exc_ft925_ok` (PRUEBA CARGA PILOTES), `exc_ft928_ok` (TORQUE), `exc_ft929_ok` (LOCALIZACIÓN FINAL), `exc_monitoreo_arq` choices ejecucion/liberada, `exc_ejecutada_pct` (Y peso 0.4), `exc_observaciones`.
- **Solado** (20): `sol_ingreso_materiales` choices vehiculo/manual/mular/teleferico, 4 sub-bloques agua/arena/grava/cemento × (calc + real + obs) = 12 campos + 4 @property desv, `sol_ejecutado_pct` (AR peso 0.05), `sol_observaciones`, `sol_soldadura_prolongas_ok`.
- **Acero** (12): `ace_ingreso`, `ace_ft028_ok` (CARTILLA REFUERZO), `ace_ft930_ok` (REV REFUERZO/FORMALETA/SPT), `ace_corte_flejado_ok`, `ace_armado_sitio_ok`, `ace_spt_herramientas_ok`, `ace_solicitado_kg`, `ace_instalado_kg`, `ace_observaciones`, `ace_instalacion_pct` (BE peso 0.1), `ace_instalacion_obs`, @property `ace_desviacion_kg`.
- **Vaciado** (32): `vac_ft916_ok`, `vac_nivelacion_stub_ok`, `vac_encofrado_ok`, `vac_ingreso_materiales`, `vac_it380_ok` (INSTRUCTIVO CIMENTACIÓN), `vac_ft056_ok` (CONTROL FUNDACIONES), `vac_tipo_concreto` choices premezclado/obra, `vac_mpa_teorica`, 4 sub-bloques agua/arena/grava/cemento × (calc + real + obs), `vac_slump_ok`, `vac_fecha_vaciado`, `vac_fecha_cilindros`, `vac_inspeccion_stub_ok`, `vac_encargado_puntas`, `vac_desencofrado_ok`, `vac_ejecutado_pct` (CK peso 0.4), `vac_observaciones`.
- **Compactación** (7): `com_ft914_ok`, `com_suelo_natural_ok`, `com_suelo_cemento_ok`, `com_suelo_prestamo_ok`, `com_volumen_m3`, `com_finalizada_pct` (CR peso 0.05), `com_observaciones`.
- **Trailer** (3): `ejecutado_por`, `comentario_general`, @property `avance_ponderado` (SUMPRODUCT con pesos del proyecto).

Constraints:
- `unique_together = [('torre', 'pata')]`
- `db_table = 'construccion_oc_detalle'`
- `ordering = ['torre__numero', 'pata']`

### 3.2 Modelo `MontajeEstructuraTorreDetalle` (nuevo)

Granularidad: **OneToOne con TorreConstruccion**.

Campos derivados del Excel CANT MONTAJE (30 columnas):

- **Info General**: `tipo_torre` choices A/A_esp/B/C/D/portico, `cuerpo`, @property `funcion` (Suspensión si tipo ∈ {A, A_esp} else Retención).
- **Recepción Patio**: `fecha_recibida_patio`, `recepcion_sin_pendientes_ok`, `recepcion_observaciones`.
- **Pre-armado**: `prearmado_encargado`, `estructura_en_sitio_ok` (I peso 0.1), `prearmado_fecha_inicio`, `prearmado_fecha_fin`, `prearmada_ok` (L peso 0.2), `prearmado_pct`.
- **Montaje**: `montaje_encargado`, `montaje_fecha_inicio`, `montaje_fecha_fin`, @property `dias_montaje` (P-O), `torre_montada_ok` (R peso 0.45), `montaje_observaciones`.
- **Controles Calidad**: `ft032_control_montaje_ok`, `ft913_verticalidad_torsion_ok`, `ft920_recepcion_montaje_ok`, `revisada_ok` (W peso 0.25), `entregada_para_carga_ok` (gate Tendido).
- **Pesos**: `peso_diseno_kl`, `peso_instalado_kl`, @property `peso_desviacion_pct`, @property `peso_alerta` (True si desv > 5%).
- **Facturación**: `facturada_a_dueno_ok`, `facturada_por_contratista` (CharField, no Boolean), @property `avance_ponderado` (SUMPRODUCT con pesos 10/20/45/25).

Constraints:
- `OneToOneField(TorreConstruccion, related_name='mont_detalle')`
- `db_table = 'construccion_mont_detalle'`

### 3.3 Modelos modificados

**`ObraCivilTorre`** (modelo simplificado actual): mantiene los 6 DecimalField `avance_*` pero ahora son **caches calculados**. Método `recalcular_desde_detalles()` que promedia las 4 patas del detalle. Signal `post_save` en `ObraCivilTorreDetalle` lo llama. Endpoint `ObraCivilAvanceUpdateView` se cambia a devolver 410 Gone con mensaje claro.

**`MontajeEstructuraTorre`**: idéntico tratamiento.

**`ProyectoConstruccion`** (campos `peso_*_pct`): NO cambian — los pesos siguen viviendo aquí y se reutilizan tanto para el detalle como para el resumen.

### 3.4 Borrar / deprecar

Nada se borra en B2/B3. El cleanup (drop tablas `construccion_obra_civil_torre` y `construccion_montaje_estructura_torre`) se difiere a una iteración 3 cuando el cliente haya validado el detalle por 2+ semanas en prod.

---

## 4. Migración de datos existentes

> Estado de prod: F1 de B1 debe verificar con `psql \dt construccion_*` + count de filas con data útil ANTES de aplicar.

### 4.1 Plan de migración (forward)

**Migration `0019_obracivil_detalle.py`** (B2, pre-asignada):
1. `CreateModel(ObraCivilTorreDetalle)`.
2. `RunPython` data migration:
   - Para cada `ObraCivilTorre`, crear 4 `ObraCivilTorreDetalle` (uno por pata A/B/C/D).
   - Seed: poner `cerr_finalizado_ok=True` si `obra_civil_torre.avance_cerramiento >= 0.99`, `exc_ejecutada_pct = obra_civil_torre.avance_excavacion`, etc. (mapeo 1:1 de las 6 columnas legacy a los 6 % de avance del detalle).
   - Si `PataObra` existe para esa torre/pata, leer los booleans `cerramiento_finalizado_ok`, `excavacion_ok`, `solado_ok`, `acero_refuerzo_ok`, `vaciado_ok`, `relleno_compactacion_ok` y propagarlos al detalle.
3. `RunPython` reverse: no-op (forward-only, los detalles persisten).

**Migration `0020_montaje_detalle.py`** (B3, pre-asignada):
1. `CreateModel(MontajeEstructuraTorreDetalle)`.
2. `RunPython` data migration:
   - Para cada `MontajeEstructuraTorre`, crear 1 `MontajeEstructuraTorreDetalle`.
   - Seed: `estructura_en_sitio_ok = avance_estructura_sitio >= 0.99`, `prearmada_ok = avance_prearamada >= 0.99`, `torre_montada_ok = avance_torre_montada >= 0.99`, `revisada_ok = avance_revisada >= 0.99`.
   - Si `FaseTorre` tiene `entrega_carga_ok`, propagar a `entregada_para_carga_ok`.
3. Reverse: no-op.

### 4.2 Validación pre-migración

Antes de aplicar en prod, F1 verifica:
```bash
PGPASSWORD=Margarita28 psql -h 130.211.117.166 -U postgres -d instelec_db -c \
  "SELECT COUNT(*) FILTER (WHERE avance_cerramiento > 0 OR avance_excavacion > 0 OR avance_solado > 0 OR avance_acero > 0 OR avance_vaciado > 0 OR avance_compactacion > 0) AS rows_con_data, COUNT(*) AS total FROM construccion_obra_civil_torre"
```
Si `rows_con_data > 0`, confirmar con Miguel que el seed map (avance → ejecutado_pct) es semánticamente correcto antes del deploy.

### 4.3 Merge migration anti-conflict

Para prevenir `multiple leaf nodes` (`feedback_modulo_f3_migration_conflict`), F4 crea:

`apps/construccion/migrations/0021_merge_b2_b3.py`:
```python
class Migration(migrations.Migration):
    dependencies = [
        ('construccion', '0019_obracivil_detalle'),
        ('construccion', '0020_montaje_detalle'),
    ]
    operations = []
```

---

## 5. URLs

### 5.1 Preservadas (NO cambian — contrato del cliente)

```python
path('<uuid:proyecto_id>/obra-civil/', views.ObraCivilResumenView.as_view(), name='obra_civil_lista'),
path('<uuid:proyecto_id>/montaje/', views.MontajeResumenView.as_view(), name='montaje_lista'),
path('<uuid:proyecto_id>/obra-civil/pesos/', views.ObraCivilPesosUpdateView.as_view(), name='obra_civil_pesos_update'),
path('<uuid:proyecto_id>/montaje/pesos/', views.MontajePesosUpdateView.as_view(), name='montaje_pesos_update'),
path('<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/patas/', views.ObraCivilTorreView.as_view(), name='obra_civil_torre_patas'),
path('<uuid:proyecto_id>/montaje/<uuid:torre_id>/fase/', views.MontajeTorreView.as_view(), name='montaje_torre_fase'),
```

### 5.2 Nuevas (4)

```python
path('<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/detalle/', views.ObraCivilDetalleView.as_view(), name='obra_civil_detalle'),
path('<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/detalle/<str:pata>/<str:seccion>/', views.ObraCivilDetalleSeccionView.as_view(), name='obra_civil_detalle_seccion'),
path('<uuid:proyecto_id>/montaje/<uuid:torre_id>/detalle/', views.MontajeDetalleView.as_view(), name='montaje_detalle'),
path('<uuid:proyecto_id>/montaje/<uuid:torre_id>/detalle/<str:seccion>/save/', views.MontajeDetalleSaveView.as_view(), name='montaje_detalle_save'),
```

### 5.3 Sidebar

NO se toca. Las 4 entries (`obra-civil`, `dashboard-obra-civil`, `montaje`, `dashboard-montaje`) siguen apuntando a las mismas URL names.

---

## 6. Templates

### 6.1 Re-propósito (2)

| Template existente | Nuevo propósito | Cambios |
|---|---|---|
| `templates/construccion/obra_civil_matriz.html` | **Vista resumen auto-calculada** (cliente la abre desde sidebar) | Mostrar matriz 64×6 read-only con % derivado; cada celda es link al detalle (`obra_civil_detalle?pata=A&seccion=cerramiento`); panel pesos sigue editable |
| `templates/construccion/montaje_matriz.html` | **Vista resumen auto-calculada** | Mostrar matriz 64×4 read-only; cada celda → link al detalle por sección; panel pesos sigue editable |

### 6.2 Nuevos (10 + 13 partials)

```
templates/construccion/
├── obra_civil_detalle.html              (~180 líneas, tabs verticales A/B/C/D + tabs horizontales secciones)
├── partials/oc_seccion_cerramiento.html (5 inputs)
├── partials/oc_seccion_excavacion.html  (16 inputs incluye fts)
├── partials/oc_seccion_solado.html      (20 inputs, sub-bloque agua/arena/grava/cemento × 4)
├── partials/oc_seccion_acero.html       (12 inputs)
├── partials/oc_seccion_vaciado.html     (32 inputs sub-bloques)
├── partials/oc_seccion_compactacion.html (7 inputs)
├── montaje_detalle.html                 (~200 líneas, tabs horizontales por sección)
├── partials/mont_seccion_general.html
├── partials/mont_seccion_recepcion.html
├── partials/mont_seccion_prearmado.html
├── partials/mont_seccion_montaje.html
├── partials/mont_seccion_controles.html
├── partials/mont_seccion_pesos.html
├── partials/mont_seccion_facturacion.html
```

**Reglas anti-bug** que cada template y partial DEBE cumplir:
- **Prohibido** `{% include "x.html" ignore missing %}` — usar include simple sin `ignore missing`. Si el partial no existe aún (timing F2→F3), F2 planta un stub vacío en el mismo commit (`{% comment %}stub plantado por F2 — sobrescrito por <SUB_FEATURE> en F3{% endcomment %}`).
- **Prohibido** `{# multi-línea \n #}` para docstrings. Usar `{% comment %}...{% endcomment %}`.
- Test estático `tests/unit/test_templates_no_multiline_django_comments.py` ya valida esto. NO romperlo.

---

## 7. Tests mínimos

### 7.1 Unit `tests/unit/test_oc_detalle.py` (~15 tests, B2)

- Creación de detalle con defaults → todos los % en 0, `avance_ponderado = 0`.
- Set `cerr_finalizado_ok=True` y `exc_ejecutada_pct=0.5` con pesos 5/30/5/15/30/15 → `avance_ponderado = (1×5 + 0.5×30) / 100 = 20%`.
- Properties: `sol_agua_desv_m3`, `sol_arena_desv_m3`, `sol_grava_desv_m3`, `sol_cemento_desv_kg`, `ace_desviacion_kg`.
- `unique_together(torre, pata)` enforced.
- Signal recalcula `ObraCivilTorre` resumen tras `post_save` del detalle.
- Data migration 0019: fixture con 1 `ObraCivilTorre` que tiene `avance_excavacion=0.7` → tras migrar, 4 detalles existen con `exc_ejecutada_pct=0.7`.

### 7.2 Unit `tests/unit/test_montaje_detalle.py` (~12 tests, B3)

- `funcion` property: A → Suspensión; A_esp → Suspensión; B → Retención.
- `dias_montaje`: ambas fechas → diferencia días; una falta → None.
- `peso_desviacion_pct`: 100 vs 105 → 5.0; 100 vs 110 → 10.0; peso_diseno_kl=0 → None.
- `peso_alerta`: True si desviacion > 5%.
- `avance_ponderado` con pesos 10/20/45/25 y 4 booleans True → 100%.
- Signal recalcula `MontajeEstructuraTorre` resumen tras `post_save`.
- Migration 0020: `MontajeEstructuraTorre` con `avance_torre_montada=1` → detalle con `torre_montada_ok=True`.

### 7.3 Integration `tests/integration/test_oc_montaje_views.py` (~10 tests, B4)

- GET `/obra-civil/` (resumen) → 200, contiene 6 columnas con % derivado del detalle.
- GET `/obra-civil/<torre>/detalle/` → 200, 6 pestañas visibles, pata A por default.
- POST `/obra-civil/<torre>/detalle/A/cerramiento/` con `cerr_finalizado_ok=on` → 200, recalcula resumen.
- GET `/montaje/<torre>/detalle/` → 200, 7 secciones visibles.
- POST `/montaje/<torre>/detalle/pesos/save/` con `peso_diseno_kl=100&peso_instalado_kl=106` → 200, returns `peso_alerta=true`.

### 7.4 Smoke runner /qa-prod (B4, journey YAML)

Usando solo las **13 acciones soportadas**: `goto`, `assert_status`, `assert_contains`, `assert_selector`, `fill`, `click`, `screenshot`, `psql_select` (read-only), etc.

Journey:
- GET `/construccion/<p>/obra-civil/` → assert 200, contiene las 6 secciones.
- `psql_select` `"SELECT id FROM construccion_oc_detalle LIMIT 1"` → captura uuid.
- GET `/construccion/<p>/obra-civil/<torre_id>/detalle/?pata=A&seccion=excavacion`.
- `fill exc_metros_m3 "12.5"`, `click submit`, assert 200.
- Análogos para `/montaje/` (7 secciones).
- **NO usar** `psql_insert`, `psql_update`, `http_post`, `upload_file`.

---

## 8. Topología /modulo

```
B1 scaffolding (0.5d)
  └── B2 obra_civil_paridad (2d) ─┐
  └── B3 montaje_paridad   (2d) ──┤── B4 integracion (1d)
                                   └─→ deploy bundle
```

### B1 — Scaffolding compartido (~0.5d)

**F1 (planner)** salidas:
- BLUEPRINT.md.json con sub-features B2 y B3 y migration filenames pre-asignados (`0019_obracivil_detalle.py`, `0020_montaje_detalle.py`) y merge migration `0021_merge_b2_b3.py` para F4.
- Inventario verificado: lista de db_table reales con `psql \dt construccion_*` (espera ver `construccion_obra_civil_torre`, `construccion_montaje_estructura_torre`, `construccion_torre`, `construccion_pataobra`, `construccion_fasetorre`).
- URL names exactos del módulo construccion (lectura literal de `apps/construccion/urls.py` actual).
- Journey YAML stub con solo las 13 acciones soportadas.

**F2 (scaffolding)** entregas:
- Crear partial stubs vacíos: 6 `oc_seccion_*.html` + 7 `mont_seccion_*.html` — todos con `{% comment %}stub plantado por F2{% endcomment %}`.
- Crear componente reusable `partials/_tabs_navegacion.html` para pestañas verticales/horizontales (OC y Montaje lo usan).
- NO tocar `_proyecto_tabs.html` (ya funciona post-fix #111).

### B2 — Obra Civil paridad (~2d)

**F3 sub-agent** en worktree `worktree-b2-obracivil`:
1. Crear `ObraCivilTorreDetalle` en `models.py`.
2. `makemigrations construccion --name obracivil_detalle` → renombrar a `0019_obracivil_detalle.py`.
3. Agregar `RunPython` data migration con seed map.
4. Views: `ObraCivilResumenView` (re-propósito del actual `ObraCivilMatrizView` → read-only), `ObraCivilDetalleView`, `ObraCivilDetalleSeccionView`.
5. Actualizar `urls.py` (2 URLs nuevas).
6. Forms (`forms.py`): `ObraCivilDetalleSeccionForm` × 6 (uno por sección).
7. Templates: reescribir `obra_civil_matriz.html` como resumen + `obra_civil_detalle.html` + 6 partials de sección.
8. Signal `post_save` en `ObraCivilTorreDetalle` recalcula `ObraCivilTorre`.
9. Tests: 15 unit tests.

### B3 — Montaje paridad (~2d) (paralelo a B2)

**F3 sub-agent** en worktree `worktree-b3-montaje`:
1. Crear `MontajeEstructuraTorreDetalle`.
2. `makemigrations` → renombrar a `0020_montaje_detalle.py`.
3. Data migration con seed map.
4. Views: `MontajeResumenView` (re-propósito), `MontajeDetalleView`, `MontajeDetalleSaveView`.
5. URLs (2 nuevas).
6. Forms × 7 (uno por sección).
7. Templates: reescribir `montaje_matriz.html` + `montaje_detalle.html` + 7 partials.
8. Signal `post_save`.
9. Tests: 12 unit tests.

### B4 — Integración + dashboards + E2E (~1d)

**F4 integración**:
1. Merge worktrees b2 + b3 → branch `final/excel_paridad`.
2. Crear `0021_merge_b2_b3.py` (anti `multiple leaf nodes`).
3. Verificar `python manage.py makemigrations --check --dry-run`.
4. Actualizar `DashboardObraCivilView` y `DashboardMontajeView` para leer del resumen calculado.
5. Confirmar sidebar sin cambios.
6. Ejecutar suite completa (unit + integration + estáticos).
7. `/qa-prod instelec --journey=oc_montaje_paridad` post-deploy.

**F5 deploy**: bundle PR único.

**Closeout paralelo** (#74 y #76): F7 cierra ambos mostrando paridad campo-a-campo con el Excel + smoke OK + dashboards #75/#77 alineados.

---

## 9. Gotchas críticos (memorias aplicadas)

| Gotcha | Memoria | Prevención en este plan |
|---|---|---|
| F1 inventa tablas/URLs | `feedback_modulo_f1_schema_url_inventados` | F1 en B1 verifica con `psql \dt construccion_*` y lee `apps/construccion/urls.py` real ANTES de emitir nombres. Lista en BLUEPRINT |
| F2 planta `{% include ... ignore missing %}` | `feedback_modulo_f2_ignore_missing` | F2 planta stubs VACÍOS con include simple sin `ignore missing`. F3 sobreescribe. Test estático regresión existente protege |
| F3 ∥ migrations clash | `feedback_modulo_f3_migration_conflict` | B1 pre-asigna `0019_obracivil_detalle.py` (B2) y `0020_montaje_detalle.py` (B3). F4 crea `0021_merge_b2_b3.py` |
| F1 inventa acciones runner | `feedback_modulo_f1_qa_prod_acciones_soportadas` | F1 emite journey YAML usando solo las 13 acciones (lista pegada en F1 prompt). Mutaciones via `goto`+`fill`+`click`, no `psql_insert` |
| `{# multi-línea #}` en partials → leak visible | `feedback_django_multiline_comment_partials` (NUEVO 2026-05-26) | F2 y F3 usan `{% comment %}...{% endcomment %}` en todos los partials. Test estático regresión existente protege |
| Cliente ve "404" tras deploy | nuevo | URL names preservados (obra_civil_lista, montaje_lista); sidebar no cambia; backwards-compat AJAX endpoints (410 Gone con mensaje claro si cliente JS antiguo intenta POST a editar la matriz) |
| Data perdida al cambiar matriz a resumen | nuevo | Data migration en 0019/0020 lee `avance_*` legacy y lo seedea en el detalle |
| Suma de pesos OC ≠ 100 (Cerramiento sin peso en Excel) | nuevo | Default `peso_cerramiento_pct=5` se mantiene (suma 100). Si cliente valida que Cerramiento es 0 (parte del bloque Excavación), ajustar default a 0 y peso_excavacion=35. **Decisión a confirmar con cliente en closeout** |

---

## 10. Estimado de tiempo

| Bloque | Trabajo | Estimado |
|---|---|---|
| B1 scaffolding | F1 inventario + F2 stubs + BLUEPRINT + journey YAML stub | 0.5 día |
| B2 obra civil paridad | Modelo (110 fields) + migration + data migration + 3 views + 6 forms + 7 templates + signal + 15 tests | 2 días |
| B3 montaje paridad | Modelo (30 fields) + migration + data migration + 3 views + 7 forms + 8 templates + signal + 12 tests | 2 días |
| B4 integración | Merge migration + dashboards alineados + E2E /qa-prod + cleanup + closeout #74/#76 | 1 día |
| Buffer | Migration conflicts, regresiones, ajustes Ana Sofía | 0.5 día |
| **Total** | | **6 días** |

Wall-clock con B2 y B3 paralelos reales (2 sub-agents F3 distintos en worktrees aislados): **3.5 días** (B1 0.5 + max(B2,B3) 2 + B4 1).

---

## 11. Pre-requisitos para arrancar /modulo

- `gh` autenticado como mbrt26.
- Runner self-hosted `vm-indunnova` vivo.
- `~/Desktop/Repos/Instelec` clean, branch `main` al día.
- Acceso a `instelec_db` (host 130.211.117.166, user postgres, pass Margarita28) para F1 verificar schema real.
- `qa_claude@instelec.com` válido para el runner /qa-prod.
- Última migration confirmada: `0018_merge_b1_b2_0017.py` (próxima libre = 0019).

---

## 12. Comando de invocación

```bash
/modulo instelec excel_paridad_oc_montaje 74 76
```

Pasa este plan persistido como input de F1 vía `--plan=SPRINTS/PLAN_2026-05-26_modulo_excel_paridad.md`.
