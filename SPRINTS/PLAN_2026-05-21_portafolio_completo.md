# Plan Sprint — Portafolio completo Instelec (27 issues abiertos)

**Fecha:** 2026-05-21
**Repo:** Indunnova16/Instelec
**Issues alcance:** #44 → #70 (27 abiertos)
**Autor original:** anasofiamc1-cpu — todos sin comentarios ni adjuntos en GitHub
**Asistente:** Claude Opus 4.7

---

## 1. Hallazgo crítico antes de planear (igual que sprint anterior)

Igual que en `PLAN_2026-05-18_mantenimiento_lineas.md`, varios issues están redactados como "implementar X from scratch" pero **el repo ya tiene scaffold**. Antes de implementar, hay que auditar:

| Issue dice "crear desde cero…" | Realidad en `main` |
|---|---|
| #49 ProyectoConstruccion + Torre + generación automática | [`apps/construccion/models.py`](apps/construccion/models.py): `ProyectoConstruccion`, `TorreConstruccion`, `PataObra`, `FaseTorre` (657 líneas, 11 clases) |
| #51 Sociopredial por torre con semáforo | Modelo `SocialPredial` ya existe en [apps/construccion/models.py](apps/construccion/models.py) |
| #52 Socioambiental por torre con semáforo | Modelo `AmbientalTorre` ya existe |
| #53 Obra Civil 6 bloques × 4 patas | Modelo `PataObra` ya existe |
| #44 RBAC 7 roles | `apps/usuarios/` y `apps/core/` ya tienen autenticación + `unidad_negocio` filtering; falta solo el RBAC granular |
| #48 Importación Excel programación | `apps/lineas/importers.py` ya tiene patrón `KMZImporter` extensible; falta el ExcelImporter equivalente |
| #62 Perfiles capataz/liniero mobile | App `apps/campo/` con formulario mobile multi-step ya existe (sprint anterior #40) |

**Implicación**: el ~30-40% del trabajo descrito en la épica CONSTRUCCIÓN ya está scaffolded. Hay que auditar antes de bombardear código.

---

## 2. Estado del Mac (pre-trabajo) — verificado 2026-05-21

Tras `git fetch`: `local..origin` y `origin..local` ambos vacíos → repo sincronizado. Único pendiente: `SPRINTS/` untracked (se commitea en este sprint para trazabilidad).

---

## 3. Tabla maestra — 27 issues priorizados

Esfuerzo: **S** = 1-3h | **M** = 4-8h | **L** = 2-3 días | **XL** = >3 días.

| # | Título corto | Bloque | Esfuerzo real (post-auditoría) | Depende de | Bloqueo externo |
|---|---|---|---|---|---|
| **44** | RBAC 7 roles | FieldService base | M | — | Matriz permisos cliente |
| **48** | Importación Excel flexible | FieldService | M | — | — |
| **47** | Presupuesto a avisos/actividades | FieldService | M | #46 | — |
| **46** | Cálculo automático costos fijos | FieldService | M | — | Estructura costos fijos cliente |
| **45** | Dashboard KPIs mensuales (Excel→DB) | FieldService | L | #46 | Template Excel Janeth |
| **49** | Proyecto/Contrato/Torre base | CONSTRUCCIÓN — Auditoría | S | — | Nomenclatura T001 vs E1 |
| **50** | Ingeniería: checklist 3 áreas | CONSTRUCCIÓN | M | #49 | — |
| **51** | Sociopredial por torre | CONSTRUCCIÓN — Auditoría | S | #49 | — |
| **52** | Socioambiental por torre | CONSTRUCCIÓN — Auditoría | S | #49 | — |
| **53** | Obra Civil 6 bloques × 4 patas | CONSTRUCCIÓN — Completar | L | #49, #50, #51, #52 | — |
| **54** | Control materiales diseño vs real | CONSTRUCCIÓN | M | #53 | — |
| **55** | Alertas cilindros concreto 7/14/21/51d | CONSTRUCCIÓN | M | #53 | — |
| **65** | Control kits cerramiento reutilizables | CONSTRUCCIÓN | S | #53 | — |
| **67** | Habilitar ejecución paralela OC/Montaje/SPT | CONSTRUCCIÓN | S | #53 | — |
| **56** | Montaje: recepción → izado | CONSTRUCCIÓN | M | #49, #67 | — |
| **57** | SPT + Pintura (cable, pólvora, franjas) | CONSTRUCCIÓN | M | #49, #67 | — |
| **58** | Tendido: conductor, OPGW, cable guarda | CONSTRUCCIÓN | M | #56 | — |
| **59** | Obras de Protección (trinchos, gaviones) | CONSTRUCCIÓN | S | #58 | — |
| **60** | Pruebas y cierre proyecto | CONSTRUCCIÓN | S | #58 | — |
| **68** | Programación: fechas planeadas | CONSTRUCCIÓN | M | #49 | — |
| **61** | Dashboard avance planeado vs ejecutado + curva S | CONSTRUCCIÓN | L | #53, #68 | — |
| **69** | Financiero: P&G, flujo caja, PDEO | CONSTRUCCIÓN | XL | #49 | Definición PDEO Claudia |
| **66** | Presupuesto planeado vs ejecutado (construcción) | CONSTRUCCIÓN | M | #69 | — |
| **70** | Dashboard KPIs financieros + gráficas | CONSTRUCCIÓN | L | #66, #69 | — |
| **62** | Perfiles mobile capataz/liniero | CONSTRUCCIÓN — Cross | M | #44, #53, #56, #57 | — |
| **64** | Planillas imprimibles + firma interventoría | CONSTRUCCIÓN — Cross | M | #53, #56 | — |
| **63** | Modo offline campo | CONSTRUCCIÓN — Cross | L | #62, #64 | Decisión arquitectura |

**Estimado bruto antes de auditoría:** 173h (~4-5 semanas a tiempo completo).
**Estimado revisado tras auditoría esperada:** 100-130h (~3-4 semanas) — descontando ~30% por scaffold existente en CONSTRUCCIÓN.

---

## 4. Plan por sprints (1 semana cada uno)

### Sprint 0 — Esta semana (resto): Bugs/base FieldService — *3-5 días*
**Objetivo:** Cerrar issues sueltos del módulo MANTENIMIENTO antes de entrar a la épica.
- **#44 RBAC** — implementar 7 roles + middleware + matriz permisos. **PRE-REQ:** validar matriz con cliente.
- **#48 Importador Excel flexible** — autodetección columnas, soporte "Programación - S18.xlsx" real.
- **#46 Costos fijos automáticos** — modelo `EstructuraCostosFijos` + cálculo en Aviso.
- **#47 Presupuesto a Aviso** — asignación + alertas umbral + barra visual.

Cierre: 4 issues en prod (mantenimiento sigue operativo, Ana Sofía valida).

### Sprint 1 — Próxima semana: Dashboard KPI + Auditoría CONSTRUCCIÓN — *5 días*
- **#45 Dashboard KPIs Excel→DB** — consumir #46/#47, generar reportes mensuales. ⏸ Template Janeth.
- **#49 Auditoría ProyectoConstruccion** — confirmar que el modelo existente cubre criterios; agregar lo faltante (nomenclatura torres, generación automática de filas en submodelos).
- **#51 Auditoría Sociopredial** — confirmar SocialPredial vs criterios (4 actas, semáforo). Completar UI.
- **#52 Auditoría Socioambiental** — confirmar AmbientalTorre vs criterios. Completar UI.

Cierre esperado: 4 issues más.

### Sprint 2 — Semana 3: Núcleo Obra Civil — *5 días*
- **#50 Ingeniería checklist 3 áreas** — modelo + UI (Civil/Montaje/Tendido con 3 estados).
- **#53 Auditoría + completar Obra Civil 6 bloques × 4 patas** — usar `PataObra` existente; agregar bloques faltantes (Cerramiento → Compactación).
- **#54 Control materiales (desviación ≥5%)** — alerta + observación obligatoria.
- **#55 Alertas cilindros concreto** — Celery task con triggers 7/14/21/51d.
- **#65 Kits cerramiento reutilizables** — inventario por ubicación.
- **#67 Ejecución paralela** — lógica de prerequisitos no bloqueante.

### Sprint 3 — Semana 4: Montaje + SPT + Tendido — *5 días*
- **#56 Módulo Montaje** — 4 sub-fases con pesos.
- **#57 SPT + Pintura** — cable diseño vs real, pólvora teórica vs consumida.
- **#58 Tendido** — vestida, riega, tendido conductor/OPGW.
- **#68 Programación** — cronograma con fechas planeadas/sección.

### Sprint 4 — Semana 5: Cierre técnico + Dashboards técnicos — *5 días*
- **#59 Obras de Protección**.
- **#60 Pruebas y cierre proyecto**.
- **#61 Dashboard avance + curva S** — pesos editables, % avance general.
- **#62 Perfiles mobile capataz/liniero** — vistas filtradas por rol.

### Sprint 5 — Semana 6: Financiero + Presupuesto — *5 días*
- **#69 Financiero P&G + flujo caja + PDEO** — modelo contable base. ⏸ Definición PDEO.
- **#66 Presupuesto construcción**.

### Sprint 6 — Semana 7: Dashboards financieros + Cross-cutting — *5 días*
- **#70 Dashboard KPIs financieros + gráficas**.
- **#64 Planillas imprimibles + firma** (WeasyPrint).
- **#63 Modo offline** — solo si arquitectura validada; si no, diferir a v2.

---

## 5. Camino crítico

```
#49 (auditoría) → #50/#51/#52 → #53 → #56 → #58 → #59/#60
```

Si todo va serial: ~30 días hábiles. Con paralelización de bloques independientes (sociopredial vs socioambiental vs ingeniería, montaje vs SPT) y delegando issues "auditoría" (S) en lotes → realista en **6-7 semanas**.

---

## 6. Convenciones por protocolo Indunnova (vigentes)

- **Asignar a `anasofiamc1-cpu`** al cerrar (memoria `feedback_instelec_asignar_anasofia`).
- **No cerrar issues**; cliente cierra al validar.
- **Comentario estructurado** con 🟢/🟡/🔵/⚠️ + root cause + smoke + registro legacy.
- **Smoke E2E** cubre **todos los módulos del aplicativo**, no solo lo tocado (`feedback_qa_smoke_crawl_maestros`).
- **Test contra dato legacy** en cada fix.
- **Deploy** via `gh workflow run deploy-cloudrun.yml --ref main` + `gh run watch`.
- **Sin costos GCP** sin autorización.
- **Sin anglicismos** en UI o comentarios.

---

## 7. Decisiones de scope pendientes (5 preguntas)

1. **¿#44 RBAC bloquea inicio de la épica CONSTRUCCIÓN o se desarrolla en paralelo?**
   - Bloquea: retrasa épica ~5 días pero #62 (perfiles mobile) sale limpio.
   - Paralelo: arranca antes pero #62 puede requerir refactor.

2. **¿#66 Presupuesto construcción avanza sin definición de Claudia, o lo dejamos en backlog hasta tener input?**

3. **¿#63 Modo offline es MVP crítico o v2?** Impacta arquitectura (caché, Service Workers/PWA).

4. **¿KPIs de #45 (mantenimiento) y #70 (construcción) comparten infra/modelo base o se desarrollan separados?**

5. **Generación automática de torres en #49: ¿cascada POST_SAVE a submodelos o lazy-load al acceder?** Impacta performance con KMZ de 4586 torres.

---

## 8. Inputs del cliente — auditoría adjuntos `Documentacion/` (2026-05-21)

Tras revisar `Documentacion/`, **la mayoría de inputs que parecían pendientes ya están**:

| Pregunta original | Adjunto que la responde | Estado |
|---|---|---|
| #44 Matriz de permisos | 3 VTT (`instelec reu`, `Seguimiento aplicativo`, `INstelec 1 abril`) describen roles: admin, técnico/campo (solo registro+mapa), finanzas, ambiental, supervisor cuadrilla | ✅ accionable |
| #45 Template Excel KPIs | `01022026-REPORTE DIARIO-F01 v1 -.xlsx` (5 sheets: Programacion 740×58, Seg Diario 228×462, SOCIO-PREDIAL, SOCIO-AMBIENTAL, H.Lluvia 99×589) + 13 CSVs derivados | ✅ accionable |
| #46 Estructura costos fijos | `AVANCES.xlsx` por tramo (136 cols) + sheet `Seg Diario` del Reporte Diario | ⚠️ revisar más a fondo |
| #47 Avisos para presupuesto | `2026.01.06 1877 Avisos Abiertos.xlsx` — 1878 registros reales, 38 columnas | ✅ accionable |
| #48 Formato Excel programación | `Programación S06.xlsx` con sheets `02`..`06` (53×16 c/u, semanas del año) | ✅ accionable |
| #49 Nomenclatura torres | `csv_Programacion.csv` y `csv_SOCIO-PREDIAL.csv` muestran convención real del cliente | ✅ leer al iniciar |
| #69 PDEO | `Copia de AVANCE PDO 24-11-2025.xlsx` (sheets: Proyecto, Ingenieria, Actividades preliminares, CANT OOCC, OOCC) — **es el PDO de Claudia** (P=Plan, D=De, O=Obra). | ✅ accionable |
| Torres geo | `Torres Transelca.kmz` (212 KB, 40 líneas, 4586 torres) | ✅ ya en uso |

**Bloqueos externos reales restantes:** ninguno crítico para arrancar Sprint 0.

---

## 9. Acción inmediata

- [x] Verificado sync con `origin/main`.
- [x] `SPRINTS/` commiteado + pusheado en este sprint.
- [ ] Confirmar con Miguel orden de Sprint 0:
  - Opción A: arrancar **#48 (Importador Excel)** — independiente, sin bloqueos, desbloquea Programación.
  - Opción B: arrancar **#44 (RBAC)** — marcado "Urgente" por cliente, pero más invasivo (toca todo).
  - Opción C: arrancar **#46 → #47** (costos + presupuesto) — usan datos reales de `AVANCES.xlsx` + Avisos.
