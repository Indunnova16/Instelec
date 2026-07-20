# CLAUDE.md — Instelec / TransMaint

## Contexto del proyecto
Sistema de gestión de proyectos de **construcción y mantenimiento de líneas de
transmisión eléctrica** para Instelec SAS. Desarrollado por Indunnova S.A.S.

- **Cliente:** Instelec SAS (contacto: Gabriel Valencia — gabriel.valencia@instelec.com.co)
- **Stack:** Django 5.1, HTMX, Alpine.js, Google Cloud Run, PostgreSQL/PostGIS
- **Repo:** https://github.com/Indunnova16/Instelec
- **Desarrollador:** @mbrt26
- **Validador QA:** @anasofiamc1-cpu (principal) / @Indunnova

## Entorno de validación
- **URL base producción:** `https://instelec-api-rvfp6uj2va-uc.a.run.app`
- **Servicio Cloud Run:** `instelec-api` (región `us-central1`, proyecto `appsindunnova`)
- **Login:** `/usuarios/login/` — campo de usuario `username`
- **Proyecto QA de referencia:** QA test #49 — Puerta de Oro
  - UUID proyecto: `ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`
  - Torres: 64 (T-1 a T-64, con T-25/E25 marcada "No aplica")
- **Usuario QA:** Admin Instelec (Administrador legacy)

> En las rutas de abajo, reemplazar `{proyecto_uuid}` por
> `ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7` para QA, y `{torre_uuid}` /
> `{uuid}` por el id real del registro.

---

## Arquitectura de URLs (prefijos por app)

El ruteo raíz vive en `config/urls.py`. Cada app declara su `app_name`
(namespace) — usar `{% url 'namespace:name' %}` en templates y
`reverse("namespace:name", ...)` en vistas.

| App | Prefijo | Namespace | Alcance |
|-----|---------|-----------|---------|
| core | `/` | `core` | Home, health checks, presentación, unidad de negocio |
| usuarios | `/usuarios/` | `usuarios` | Login, perfil, gestión de usuarios |
| lineas | `/lineas/` | `lineas` | Líneas, torres, vanos, mapa, KMZ (mantenimiento) |
| cuadrillas | `/cuadrillas/` | `cuadrillas` | Cuadrillas, personal, asistencia, carga masiva S18 |
| actividades | `/actividades/` | `actividades` | Programación, calendario, eventos, importaciones |
| campo | `/campo/` | `campo` | Registros de campo, evidencias, daños, avances |
| ambiental | `/ambiental/` | `ambiental` | Informes y permisos ambientales |
| contratos | `/contratos/` | `contratos` | Gestión de contratos |
| financiero | `/financiero/` | `financiero` | Dashboards, costos, facturación, nómina, presupuesto |
| indicadores | `/indicadores/` | `indicadores` | KPIs, dashboard mantenimiento, actas, ANS |
| construccion | `/construccion/` | `construccion` | Proyectos, torres, obra civil, montaje, tendido, etc. |
| ingenieria | `/ingenieria/` | `ingenieria` | Civil / montaje / tendido por contrato |
| preliminares | `/preliminares/` | `preliminares` | Predial y ambiental por contrato |
| api | `/api/` | — | Django Ninja (OpenAPI, docs en `/api/docs`) |

---

## Mapa de rutas

### Construcción (`/construccion/`)

#### Proyectos y estructura
| Módulo | Ruta | Name |
|--------|------|------|
| Listado de proyectos | `/construccion/` | `construccion:lista` |
| Dashboard del proyecto | `/construccion/{proyecto_uuid}/` | `construccion:dashboard` |
| Contrato | `/construccion/{proyecto_uuid}/contrato/` | `construccion:contrato` |
| Torres (listado) | `/construccion/{proyecto_uuid}/torres/` | `construccion:torres_lista` |
| Nueva torre | `/construccion/{proyecto_uuid}/torres/crear/` | `construccion:torre_crear` |

#### Bloques de avance (vista matriz + detalle por torre)
| Módulo | Ruta | Name |
|--------|------|------|
| **Obra Civil** (matriz) | `/construccion/{proyecto_uuid}/obra-civil/` | `construccion:obra_civil_lista` |
| Obra Civil — detalle torre | `/construccion/{proyecto_uuid}/obra-civil/{torre_uuid}/` | `construccion:obra_civil_torre` |
| Dashboard Obra Civil | `/construccion/{proyecto_uuid}/dashboard-obra-civil/` | `construccion:dashboard_obra_civil` |
| **Montaje** (matriz) | `/construccion/{proyecto_uuid}/montaje/` | `construccion:montaje_lista` |
| Montaje — detalle torre | `/construccion/{proyecto_uuid}/montaje/{torre_uuid}/` | `construccion:montaje_torre` |
| Dashboard Montaje | `/construccion/{proyecto_uuid}/dashboard-montaje/` | `construccion:dashboard_montaje` |
| **Tendido** (matriz) | `/construccion/{proyecto_uuid}/tendido/` | `construccion:tendido_lista` |
| Tendido — detalle torre | `/construccion/{proyecto_uuid}/tendido/{torre_uuid}/` | `construccion:tendido_torre` |
| Dashboard Avance (global) | `/construccion/{proyecto_uuid}/dashboard-avance/` | `construccion:dashboard_avance` |
| **Hochiminh Fase 1** (matriz Marcación/Replanteo) | `/construccion/{proyecto_uuid}/hochiminh/` | `construccion:hochiminh_lista` |

> **Hochiminh — flujo clic-torre (#171, confirmado con el cliente el
> 2026-07-14, NO es un bug):** el clic en el **número de torre** de la matriz
> Hochiminh abre "Editar torre" general (Tipo / Cimentación / Peso /
> Cuadrillas — `torre_form.html`, mismo form que `torres_lista`). Las 4
> columnas propias de Hochiminh (**Marcación** A/B/C/D, **Replanteo** A/B/C/D,
> **Estado Predial**, **Estado Ambiental**) se editan **directo en la
> matriz** con checks inline (AJAX, `HochiminhToggleView`) — no tienen ni
> necesitan una pantalla de detalle dedicada. Si un usuario reporta "no
> encuentro dónde editar Marcación/Replanteo desde el detalle de la torre",
> la respuesta es: se edita desde la matriz, no desde "Editar torre".
>
> **Backlog Tipo/Cimentación vacíos (#171): declarado ❌ fuera de alcance de
> este issue.** El QA de Hochiminh Fase 1 (2026-07-14) encontró 64/65 torres
> del proyecto QA con `tipo`/`tipo_cimentacion` vacíos (diligenciamiento
> pendiente, no un bug de datos). El issue #171 no pidió explícitamente una
> carga masiva de estos 2 campos — el diligenciamiento manual torre-por-torre
> ya es posible hoy vía "Editar torre" (Sprint A, `torre_form.html`). Si
> Gabriel pide carga masiva (import Excel) para estos campos, es un **issue
> nuevo aparte**, no un follow-up de #171.

#### Actividades Finales y Obras de Protección  *(antes "⚠️ por confirmar")*
| Módulo | Ruta | Name |
|--------|------|------|
| **Actividades Finales** (matriz) | `/construccion/{proyecto_uuid}/actividades-finales/` | `construccion:actividades_finales` |
| Actividades Finales — toggle aplica/no aplica | `/construccion/{proyecto_uuid}/actividades-finales/{torre_uuid}/toggle/` | `construccion:actividades_finales_toggle` |
| **Obras de Protección** (listado) | `/construccion/{proyecto_uuid}/protecciones/` | `construccion:protecciones_lista` |
| Obras de Protección — crear | `/construccion/{proyecto_uuid}/protecciones/crear/` | `construccion:protecciones_crear` |
| **Trinchos y Cunetas** (versión moderna, listado) | `/construccion/{proyecto_uuid}/trinchos-cunetas/` | `construccion:trinchos_cunetas` |
| SPT y Pintura | `/construccion/{proyecto_uuid}/spt-pintura/` | `construccion:spt_pintura` |
| Pruebas Técnicas | `/construccion/{proyecto_uuid}/pruebas/` | `construccion:pruebas_lista` |
| Kits de Cerramiento | `/construccion/{proyecto_uuid}/kits/` | `construccion:kits_lista` |

> Nota: existe un modelo **legacy** `ObraProteccion` (rutas `/protecciones/`) y la
> versión moderna **Trinchos y Cunetas** (`TrinchoCuneta`, rutas `/trinchos-cunetas/`,
> issue #80). Para nuevos cambios usar la versión moderna salvo que el issue pida lo legacy.

#### Seguimiento, financiero e indicadores de construcción
| Módulo | Ruta | Name |
|--------|------|------|
| Seguimiento diario | `/construccion/{proyecto_uuid}/seguimiento/` | `construccion:seguimiento_diario` |
| Cronograma | `/construccion/{proyecto_uuid}/cronograma/` | `construccion:cronograma` |
| Financiero del proyecto (grid PDEO) | `/construccion/{proyecto_uuid}/financiero/` | `construccion:financiero_grid` |
| Dashboard Financiero | `/construccion/{proyecto_uuid}/dashboard-financiero/` | `construccion:dashboard_financiero` |
| Indicadores financieros (B2) | `/construccion/{proyecto_uuid}/indicadores/financieros/` | `construccion:b2_indicador_financiero_lista` |
| Indicadores técnicos (B2) | `/construccion/{proyecto_uuid}/indicadores/tecnicos/` | `construccion:b2_indicador_tecnico_lista` |
| Indicadores de desempeño (B2) | `/construccion/{proyecto_uuid}/indicadores/desempeno/` | `construccion:b2_indicador_desempeno_lista` |

#### Programación de cuadrillas (namespace `construccion`)
| Módulo | Ruta | Name |
|--------|------|------|
| Programación cuadrillas (listado) | `/construccion/programacion-cuadrillas/` | `construccion:programacion_cuadrillas_index` |
| Dashboard programación | `/construccion/programacion-cuadrillas/dashboard/` | `construccion:programacion_cuadrillas_dashboard` |
| Nueva programación | `/construccion/programacion-cuadrillas/crear/` | `construccion:programacion_cuadrilla_crear` |
| Detalle programación | `/construccion/programacion-cuadrillas/{uuid}/` | `construccion:programacion_cuadrilla_detalle` |

### Mantenimiento / Indicadores (`/indicadores/`)  *(antes "⚠️ por confirmar")*
| Módulo | Ruta | Name |
|--------|------|------|
| Dashboard Indicadores | `/indicadores/` | `indicadores:dashboard` |
| **Dashboard Mantenimiento (v1)** | `/indicadores/mantenimiento/` | `indicadores:dashboard_mantenimiento` |
| Exportar mantenimiento (xlsx) | `/indicadores/mantenimiento/export-xlsx/` | `indicadores:dashboard_mantenimiento_xlsx` |
| **Dashboard Mantenimiento (v2, con CRUD)** | `/indicadores/mantenimiento-v2/` | `indicadores:dashboard_mantenimiento_v2` |
| Mantenimiento v2 — financiero | `/indicadores/mantenimiento-v2/financiero/` | `indicadores:mant_fin_list` |
| Mantenimiento v2 — técnico | `/indicadores/mantenimiento-v2/tecnico/` | `indicadores:mant_tec_list` |
| Mantenimiento v2 — ANS | `/indicadores/mantenimiento-v2/ans/` | `indicadores:ans_list` |
| Actas | `/indicadores/actas/` | `indicadores:actas` |

### Líneas y torres de mantenimiento (`/lineas/`)
| Módulo | Ruta | Name |
|--------|------|------|
| Listado de líneas | `/lineas/` | `lineas:lista` |
| Detalle de línea | `/lineas/{uuid}/` | `lineas:detalle` |
| Torres de la línea | `/lineas/{uuid}/torres/` | `lineas:torres` |
| Detalle de torre | `/lineas/torre/{uuid}/` | `lineas:torre_detalle` |
| Mapa de líneas | `/lineas/mapa/` | `lineas:mapa` |
| Importar KMZ | `/lineas/importar-kmz/` | `lineas:importar_kmz` |
| Avance de línea | `/lineas/{uuid}/avance/` | `lineas:avance` |
| Mi avance (campo) | `/lineas/mi-avance/` | `lineas:mi_avance` |

### Cuadrillas (`/cuadrillas/`)
| Módulo | Ruta | Name |
|--------|------|------|
| Listado | `/cuadrillas/` | `cuadrillas:lista` |
| Nueva cuadrilla | `/cuadrillas/crear/` | `cuadrillas:crear` |
| Detalle | `/cuadrillas/{uuid}/` | `cuadrillas:detalle` |
| Carga masiva S18 | `/cuadrillas/masiva/upload/` | `cuadrillas:masiva_upload` |
| Plantilla S18 | `/cuadrillas/masiva/plantilla/` | `cuadrillas:descargar_plantilla` |
| Asistencia | `/cuadrillas/{uuid}/asistencia/` | `cuadrillas:asistencia_update` |
| Mapa de cuadrillas | `/cuadrillas/mapa/` | `cuadrillas:mapa` |

### Actividades (`/actividades/`)
| Módulo | Ruta | Name |
|--------|------|------|
| Listado | `/actividades/` | `actividades:lista` |
| Calendario | `/actividades/calendario/` | `actividades:calendario` |
| Programación | `/actividades/programacion/` | `actividades:programacion` |
| Importar programación | `/actividades/programacion/importar/` | `actividades:importar` |
| Exportar avance | `/actividades/reportes/avance/` | `actividades:exportar_avance` |

### Campo (`/campo/`)
| Módulo | Ruta | Name |
|--------|------|------|
| Registros | `/campo/` | `campo:lista` |
| Reportar daño | `/campo/reportar-dano/` | `campo:reportar_dano` |
| Procedimientos | `/campo/procedimientos/` | `campo:procedimientos` |
| Mis avances | `/campo/mis-avances/` | `campo:mis_avances` |

### Financiero (`/financiero/`)
| Módulo | Ruta | Name |
|--------|------|------|
| Dashboard | `/financiero/` | `financiero:dashboard` |
| Cuadro de costos | `/financiero/cuadro-costos/` | `financiero:cuadro_costos` |
| Facturación | `/financiero/facturacion/` | `financiero:facturacion` |
| Checklist de facturación | `/financiero/checklist-facturacion/` | `financiero:checklist_facturacion` |
| Presupuesto planeado | `/financiero/presupuesto-planeado/` | `financiero:presupuesto_planeado` |
| Presupuesto real | `/financiero/presupuesto-real/` | `financiero:presupuesto_real` |
| Nómina | `/financiero/nomina/` | `financiero:nomina` |

### Ambiental, Contratos, Ingeniería, Preliminares
| Módulo | Ruta | Name |
|--------|------|------|
| Ambiental — informes | `/ambiental/` | `ambiental:lista` |
| Ambiental — consolidado | `/ambiental/consolidado/` | `ambiental:consolidado` |
| Contratos | `/contratos/` | `contratos:lista` |
| Ingeniería (seleccionar contrato) | `/ingenieria/` | `ingenieria:seleccionar` |
| Ingeniería — civil / montaje / tendido | `/ingenieria/{contrato_uuid}/{civil\|montaje\|tendido}/` | `ingenieria:civil` … |
| Preliminares (seleccionar contrato) | `/preliminares/` | `preliminares:seleccionar` |
| Preliminares — predial / ambiental | `/preliminares/{contrato_uuid}/{predial\|ambiental}/` | `preliminares:predial` … |

### Globales
| Módulo | Ruta | Name |
|--------|------|------|
| Home | `/` | `core:home` |
| Health check | `/health/` | `core:health` |
| API docs (Swagger) | `/api/docs` | — |

---

## Modelos clave

| App | Modelo | Qué representa |
|-----|--------|----------------|
| construccion | `ProyectoConstruccion` | Proyecto de construcción vinculado a un contrato; agrupa torres y fases. Id = UUID (`{proyecto_uuid}` en URLs). |
| construccion | `TorreConstruccion` | Torre del proyecto: `numero` (T-001…), `aplica` (bool — si es False se excluye del % de avance), tipo de estructura, cimentación, cuadrillas. Id = UUID (`{torre_uuid}`). |
| construccion | `ObraCivilTorre` | Avance de obra civil por torre/pata (6 bloques: excavación, vaciado, relleno…). |
| construccion | `MontajeEstructuraTorre` | Avance de montaje de estructura por torre. |
| construccion | `TendidoTorre` | Avance de tendido (conductores + OPGW) por torre / circuito. |
| construccion | `ObraProteccion` / `TrinchoCuneta` | Obras de protección de suelo (trincho/cuneta). `ObraProteccion`=legacy, `TrinchoCuneta`=moderno (#80). |
| lineas | `Linea` / `Torre` / `Vano` | Línea de transmisión, sus torres (con GIS/PostGIS) y los vanos (tramos entre torres) — lado mantenimiento. |
| cuadrillas | `Cuadrilla` / `PersonalCuadrilla` | Equipo de trabajo (encargado, miembros, costo/día) y su personal con rol/tarifa. |
| actividades | `Actividad` / `TipoActividad` | Actividad programada (línea/torre/cuadrilla/estado) y su tipo configurable. |
| indicadores | `Indicador` / `MedicionIndicador` | KPI/SLA (código, fórmula, meta, peso) y su medición mensual. |
| financiero | `Presupuesto` / `CostoRecurso` | Presupuesto por proyecto/línea y costos unitarios de recurso. |

---

## Comandos de desarrollo y deploy

```bash
make install     # instalar dependencias (requirements/local.txt)
make migrate     # aplicar migraciones
make run         # runserver local
make test        # pytest
make coverage    # pytest --cov
make lint        # ruff check
make format      # ruff format
```

- **Settings:** `config/settings/{base,local,dev_lite,production}.py` (vía `DJANGO_SETTINGS_MODULE`).
- **Tests:** `pytest` (`tests/unit`, `tests/integration`, `tests/e2e`); el repo corre **ruff check** *y* **ruff format --check** en CI — formatear antes de commitear.
- **Deploy:** workflow `.github/workflows/deploy-cloudrun.yml` (`workflow_dispatch`), servicio Cloud Run `instelec-api`, job de migración `instelec-migrate`. Tras el deploy, verificar que la revisión nueva tenga el 100% del tráfico.
- **Base de datos:** Cloud SQL Postgres + PostGIS (instancia consolidada). Acceso de lectura/diagnóstico vía proxy `127.0.0.1:5434`.

---

## Protocolo de validación QA

### Al validar exitosamente
Comentar en el issue con el resultado y el screenshot de la pantalla validada en producción.

### Al encontrar un bug
Reportar con: **descripción**, **URL exacta donde se reproduce**, **comportamiento esperado vs. real**, **screenshot** y, si se conoce, el **archivo probable** (ej. `apps/<modulo>/views.py`).

### Reglas
- **Nunca cerrar un issue sin validación explícita del cliente.** El desarrollador deja el issue OPEN y asignado al validador (`@anasofiamc1-cpu` / `@Indunnova`).
- Siempre adjuntar screenshot al reportar un bug.
- Siempre incluir la URL donde se reproduce.
- Probar contra el proyecto QA de referencia (Puerta de Oro, UUID arriba) e incluir ≥1 registro pre-existente, no solo datos nuevos.

---

## Glosario

| Término | Significado |
|---------|-------------|
| Tiro | Tanda de tendido — tramo de torres en el que se divide el tendido del conductor |
| Cuadrilla | Equipo de trabajo con encargado, miembros, cargo y costo/día |
| JT / JT/CTA | Jefe de Trabajo / Capacitado — cargo jerárquico del encargado de cuadrilla |
| Pata | Cada una de las 4 bases de una torre (A, B, C, D) |
| Vano | Distancia entre una torre y la siguiente |
| ANS | Acuerdo de Nivel de Servicio |
| OPGW | Fibra óptica integrada en el cable de guarda |
| Trincho | Obra de protección de suelo (contención) |
| Cuneta | Canal de drenaje en la base de torres |
| Semana ISO | Número de semana del año según estándar ISO 8601 |
| Bloque | Macro-etapa del proyecto: Obra Civil / Montaje / Tendido |
| No aplica | Torre o casilla excluida del cálculo de avance (`TorreConstruccion.aplica = False`) |
| PDEO | Presupuesto detallado de ejecución de obra (grid financiero por proyecto) |
| S18 | Formato de carga masiva de cuadrillas/personal |
