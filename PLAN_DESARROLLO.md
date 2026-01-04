# Plan de Desarrollo - Sistema de Gestión de Mantenimiento de Líneas de Transmisión

## Resumen del Proyecto

**Nombre:** TransMaint - Sistema de Gestión Integral
**Cliente:** Instelec Ingeniería S.A.S.
**Duración estimada:** 22-26 semanas

---

## 1. Arquitectura Técnica

### 1.1 Stack Tecnológico

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                       │
├─────────────────────────────────┬───────────────────────────────────────┤
│         App Móvil               │            Portal Web                  │
│         Flutter 3.x             │            Next.js 14                  │
│         Dart                    │            React + TypeScript          │
│         SQLite (offline)        │            TailwindCSS                 │
└─────────────────────────────────┴───────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            BACKEND                                       │
│                         Node.js + NestJS                                 │
│                         TypeScript                                       │
│                         REST API + WebSockets                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          BASE DE DATOS                                   │
├─────────────────────────────────┬───────────────────────────────────────┤
│        PostgreSQL 15            │         Redis                          │
│        + PostGIS                │         (Cache + Sessions)             │
└─────────────────────────────────┴───────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SERVICIOS CLOUD                                  │
├──────────────────┬──────────────────┬───────────────────────────────────┤
│  Google Cloud    │  Cloud Storage   │  Cloud Functions                   │
│  Run             │  (Fotos/Docs)    │  (Procesamiento IA)                │
└──────────────────┴──────────────────┴───────────────────────────────────┘
```

### 1.2 Estructura de Repositorios

```
instelec-transmaint/
├── apps/
│   ├── mobile/                 # App Flutter
│   ├── web/                    # Portal Next.js
│   └── api/                    # Backend NestJS
├── packages/
│   ├── shared/                 # Tipos y utilidades compartidas
│   ├── ui/                     # Componentes UI compartidos
│   └── database/               # Esquemas Prisma/TypeORM
├── infrastructure/
│   ├── terraform/              # IaC para GCP
│   ├── docker/                 # Dockerfiles
│   └── k8s/                    # Configuración Kubernetes
├── docs/                       # Documentación
└── tools/                      # Scripts y herramientas
```

---

## 2. Fases de Desarrollo

### FASE 1: Fundamentos (Semanas 1-4)

#### Semana 1-2: Setup e Infraestructura

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F1.1 | Configurar monorepo con Turborepo/Nx | Estructura de proyecto |
| F1.2 | Setup proyecto NestJS con módulos base | API skeleton |
| F1.3 | Setup proyecto Flutter con arquitectura clean | App skeleton |
| F1.4 | Setup proyecto Next.js con App Router | Web skeleton |
| F1.5 | Configurar PostgreSQL + PostGIS | Base de datos inicial |
| F1.6 | Configurar CI/CD con GitHub Actions | Pipelines de build/test |
| F1.7 | Setup Docker Compose para desarrollo local | Ambiente de desarrollo |

#### Semana 3-4: Sistema de Autenticación y Usuarios

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F1.8 | Modelo de datos: usuarios, roles, permisos | Esquema de BD |
| F1.9 | API de autenticación (JWT + refresh tokens) | Endpoints auth |
| F1.10 | Pantalla de login móvil | UI Flutter |
| F1.11 | Pantalla de login web | UI Next.js |
| F1.12 | Gestión de sesiones offline (móvil) | Persistencia local |
| F1.13 | CRUD de usuarios (admin) | Panel administración |

**Roles del sistema:**
- `admin`: Administrador del sistema
- `director`: Director de proyecto
- `coordinador`: Coordinador de cuadrillas
- `ingeniero_residente`: Ingeniero residente
- `ingeniero_ambiental`: Ingeniero ambiental/forestal
- `supervisor`: Supervisor de cuadrilla
- `liniero`: Liniero/Técnico de campo
- `auxiliar`: Auxiliar/Ayudante

---

### FASE 2: Módulo de Captura en Campo (Semanas 5-10)

#### Semana 5-6: Estructura de Datos y API

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F2.1 | Modelo: líneas de transmisión | Tabla `lineas` |
| F2.2 | Modelo: torres/estructuras | Tabla `torres` |
| F2.3 | Modelo: actividades | Tabla `actividades` |
| F2.4 | Modelo: tipos de actividad | Tabla `tipos_actividad` |
| F2.5 | Modelo: registros de campo | Tabla `registros_campo` |
| F2.6 | Modelo: evidencias fotográficas | Tabla `evidencias` |
| F2.7 | Modelo: polígonos de servidumbre | Tabla `poligonos_servidumbre` |
| F2.8 | API CRUD completa para todos los modelos | Endpoints REST |

**Esquema de Base de Datos (Módulo Campo):**

```sql
-- Líneas de transmisión
CREATE TABLE lineas (
    id UUID PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    cliente VARCHAR(50) NOT NULL, -- 'TRANSELCA' | 'INTERCOLOMBIA'
    longitud_km DECIMAL(10,2),
    tension_kv INTEGER,
    activa BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Torres/Estructuras
CREATE TABLE torres (
    id UUID PRIMARY KEY,
    linea_id UUID REFERENCES lineas(id),
    numero VARCHAR(20) NOT NULL,
    tipo VARCHAR(50), -- 'SUSPENSION' | 'ANCLAJE' | 'TERMINAL'
    latitud DECIMAL(10,8) NOT NULL,
    longitud DECIMAL(11,8) NOT NULL,
    altitud DECIMAL(8,2),
    geometria GEOMETRY(Point, 4326),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Polígonos de servidumbre
CREATE TABLE poligonos_servidumbre (
    id UUID PRIMARY KEY,
    linea_id UUID REFERENCES lineas(id),
    torre_id UUID REFERENCES torres(id),
    nombre VARCHAR(100),
    geometria GEOMETRY(Polygon, 4326) NOT NULL,
    area_hectareas DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tipos de actividad
CREATE TABLE tipos_actividad (
    id UUID PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    categoria VARCHAR(50), -- 'PODA' | 'HERRAJES' | 'INSPECCION' | 'LIMPIEZA'
    requiere_fotos_antes BOOLEAN DEFAULT true,
    requiere_fotos_durante BOOLEAN DEFAULT true,
    requiere_fotos_despues BOOLEAN DEFAULT true,
    campos_formulario JSONB, -- Configuración dinámica de campos
    activo BOOLEAN DEFAULT true
);

-- Actividades programadas
CREATE TABLE actividades (
    id UUID PRIMARY KEY,
    linea_id UUID REFERENCES lineas(id),
    torre_id UUID REFERENCES torres(id),
    tipo_actividad_id UUID REFERENCES tipos_actividad(id),
    cuadrilla_id UUID REFERENCES cuadrillas(id),
    fecha_programada DATE NOT NULL,
    estado VARCHAR(20) DEFAULT 'PENDIENTE', -- 'PENDIENTE' | 'EN_CURSO' | 'COMPLETADA' | 'CANCELADA'
    prioridad VARCHAR(10) DEFAULT 'NORMAL', -- 'BAJA' | 'NORMAL' | 'ALTA' | 'URGENTE'
    observaciones_programacion TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Registros de campo (ejecución)
CREATE TABLE registros_campo (
    id UUID PRIMARY KEY,
    actividad_id UUID REFERENCES actividades(id),
    usuario_id UUID REFERENCES usuarios(id),
    fecha_inicio TIMESTAMP NOT NULL,
    fecha_fin TIMESTAMP,
    latitud_inicio DECIMAL(10,8),
    longitud_inicio DECIMAL(11,8),
    latitud_fin DECIMAL(10,8),
    longitud_fin DECIMAL(11,8),
    dentro_poligono BOOLEAN,
    datos_formulario JSONB, -- Datos dinámicos según tipo de actividad
    observaciones TEXT,
    observaciones_audio_url VARCHAR(500),
    firma_responsable_url VARCHAR(500),
    sincronizado BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Evidencias fotográficas
CREATE TABLE evidencias (
    id UUID PRIMARY KEY,
    registro_campo_id UUID REFERENCES registros_campo(id),
    tipo VARCHAR(20) NOT NULL, -- 'ANTES' | 'DURANTE' | 'DESPUES'
    url_original VARCHAR(500) NOT NULL,
    url_thumbnail VARCHAR(500),
    latitud DECIMAL(10,8),
    longitud DECIMAL(11,8),
    fecha_captura TIMESTAMP NOT NULL,
    validacion_ia JSONB, -- Resultado de validación: {nitidez, iluminacion, valida}
    metadata_exif JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Semana 7-8: App Móvil - Funcionalidades Core

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F2.9 | Lista de actividades asignadas | Pantalla principal |
| F2.10 | Detalle de actividad con información de torre | Pantalla detalle |
| F2.11 | Formulario dinámico según tipo de actividad | Componente formulario |
| F2.12 | Captura de fotos con validaciones | Módulo cámara |
| F2.13 | Captura y validación de coordenadas GPS | Servicio geolocalización |
| F2.14 | Validación de ubicación vs polígono servidumbre | Algoritmo PostGIS |
| F2.15 | Almacenamiento offline (SQLite + Hive) | Persistencia local |
| F2.16 | Cola de sincronización con reintentos | Servicio sync |

#### Semana 9-10: App Móvil - Funcionalidades Avanzadas

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F2.17 | Dictado por voz (Speech-to-Text) | Integración STT |
| F2.18 | Firma digital en pantalla | Componente firma |
| F2.19 | Estampado de metadatos en fotos | Procesamiento imagen |
| F2.20 | Modelo TFLite para validación de fotos | IA en dispositivo |
| F2.21 | Compresión inteligente de imágenes | Optimización |
| F2.22 | Indicadores de sincronización pendiente | UI estados |
| F2.23 | Modo offline completo | Testing offline |

**Flujo de Captura en Campo:**

```
┌─────────────────┐
│ Seleccionar     │
│ Actividad       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Validar GPS     │──── ❌ Fuera de zona ──→ Alerta
│ vs Polígono     │
└────────┬────────┘
         │ ✓
         ▼
┌─────────────────┐
│ Capturar Fotos  │
│ ANTES           │──── ❌ Foto borrosa ──→ Rechazar
└────────┬────────┘
         │ ✓
         ▼
┌─────────────────┐
│ Llenar          │
│ Formulario      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Capturar Fotos  │
│ DURANTE         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Capturar Fotos  │
│ DESPUÉS         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Observaciones   │
│ (Texto/Voz)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Firma Digital   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Guardar Local   │──→ Cola de Sync
└─────────────────┘
```

---

### FASE 3: Módulo de Programación y Control (Semanas 11-14)

#### Semana 11-12: Backend y Modelos

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F3.1 | Modelo: cuadrillas | Tabla `cuadrillas` |
| F3.2 | Modelo: miembros de cuadrilla | Tabla `cuadrilla_miembros` |
| F3.3 | Modelo: vehículos | Tabla `vehiculos` |
| F3.4 | Modelo: programación mensual | Tabla `programacion_mensual` |
| F3.5 | API de programación y asignación | Endpoints REST |
| F3.6 | WebSocket para actualizaciones en tiempo real | Servicio WS |
| F3.7 | Importación de plan desde Excel | Parser Excel |

**Esquema de Base de Datos (Módulo Programación):**

```sql
-- Cuadrillas
CREATE TABLE cuadrillas (
    id UUID PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    supervisor_id UUID REFERENCES usuarios(id),
    vehiculo_id UUID REFERENCES vehiculos(id),
    activa BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Miembros de cuadrilla
CREATE TABLE cuadrilla_miembros (
    id UUID PRIMARY KEY,
    cuadrilla_id UUID REFERENCES cuadrillas(id),
    usuario_id UUID REFERENCES usuarios(id),
    rol VARCHAR(50), -- 'LINIERO' | 'AYUDANTE'
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    activo BOOLEAN DEFAULT true
);

-- Vehículos
CREATE TABLE vehiculos (
    id UUID PRIMARY KEY,
    placa VARCHAR(10) UNIQUE NOT NULL,
    tipo VARCHAR(50),
    marca VARCHAR(50),
    modelo VARCHAR(50),
    capacidad_personas INTEGER,
    costo_dia DECIMAL(12,2),
    activo BOOLEAN DEFAULT true
);

-- Programación mensual (importada de Excel cliente)
CREATE TABLE programacion_mensual (
    id UUID PRIMARY KEY,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    linea_id UUID REFERENCES lineas(id),
    datos_excel JSONB, -- Plan original importado
    aprobado BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tracking de ubicación en tiempo real
CREATE TABLE tracking_ubicacion (
    id UUID PRIMARY KEY,
    cuadrilla_id UUID REFERENCES cuadrillas(id),
    usuario_id UUID REFERENCES usuarios(id),
    latitud DECIMAL(10,8) NOT NULL,
    longitud DECIMAL(11,8) NOT NULL,
    precision_metros DECIMAL(6,2),
    timestamp TIMESTAMP DEFAULT NOW()
);
```

#### Semana 13-14: Portal Web - Programación

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F3.8 | Vista calendario mensual/semanal | Componente calendario |
| F3.9 | Drag & drop para asignación de actividades | Interacción UI |
| F3.10 | Panel de cuadrillas y disponibilidad | Dashboard cuadrillas |
| F3.11 | Mapa con ubicación de cuadrillas en tiempo real | Integración mapas |
| F3.12 | Comparativo planeado vs ejecutado | Dashboard métricas |
| F3.13 | Alertas de actividades atrasadas | Sistema notificaciones |
| F3.14 | Exportación a Excel del plan | Generador Excel |

**Dashboard de Programación (Wireframe):**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PROGRAMACIÓN - ENERO 2026                      [Semana ▼] [Exportar]  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ RESUMEN        Planeadas: 156  Ejecutadas: 89  Pendientes: 67   │   │
│  │ ████████████████████████░░░░░░░░░░░░░░ 57%                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐        │
│  │ CUADRILL │ L 6  │ M 7  │ X 8  │ J 9  │ V 10 │ S 11 │ D 12 │        │
│  ├──────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤        │
│  │ Cuad. 1  │ T015 │ T016 │ T017 │ T018 │ T019 │  --  │  --  │        │
│  │          │ ✓    │ ✓    │ ●    │ ○    │ ○    │      │      │        │
│  ├──────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤        │
│  │ Cuad. 2  │ T023 │ T024 │ T025 │ T026 │ T027 │  --  │  --  │        │
│  │          │ ✓    │ ✓    │ ✓    │ ●    │ ○    │      │      │        │
│  ├──────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤        │
│  │ Cuad. 3  │ T031 │ T032 │  --  │ T033 │ T034 │  --  │  --  │        │
│  │          │ ⚠    │ ✓    │      │ ○    │ ○    │      │      │        │
│  └──────────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘        │
│                                                                         │
│  ✓ Completada   ● En curso   ○ Pendiente   ⚠ Atrasada                  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ MAPA EN TIEMPO REAL                                              │   │
│  │ ┌───────────────────────────────────────────────────────────┐   │   │
│  │ │                    🚗 Cuad.1                               │   │   │
│  │ │         🚗 Cuad.2                                          │   │   │
│  │ │                           🚗 Cuad.3                        │   │   │
│  │ │    [Mapa con ubicaciones GPS de cuadrillas]               │   │   │
│  │ └───────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### FASE 4: Módulo Ambiental y Forestal (Semanas 15-17)

#### Semana 15-16: Consolidación y Reportes

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F4.1 | Vista de consolidación de registros | Dashboard ambiental |
| F4.2 | Filtros por línea, torre, fecha, tipo | Componentes filtro |
| F4.3 | Validación de completitud de registros | Reglas de negocio |
| F4.4 | Galería de evidencias fotográficas | Visor de imágenes |
| F4.5 | Alertas de registros incompletos | Sistema alertas |
| F4.6 | Exportación a Excel formato Transelca | Generador Excel |

#### Semana 17: Generación de Informes

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F4.7 | Plantillas de informe configurables | Sistema plantillas |
| F4.8 | Generación automática de informe mensual | Motor de reportes |
| F4.9 | Inclusión automática de fotos y coordenadas | Anexos automáticos |
| F4.10 | Exportación a PDF profesional | Generador PDF |
| F4.11 | Gestión de permisos de servidumbre | CRUD permisos |
| F4.12 | Firma digital de autorizaciones | Captura firmas |

**Esquema de Informe Ambiental:**

```sql
-- Informes ambientales
CREATE TABLE informes_ambientales (
    id UUID PRIMARY KEY,
    periodo_mes INTEGER NOT NULL,
    periodo_anio INTEGER NOT NULL,
    linea_id UUID REFERENCES lineas(id),
    estado VARCHAR(20) DEFAULT 'BORRADOR', -- 'BORRADOR' | 'REVISION' | 'APROBADO' | 'ENVIADO'
    fecha_generacion TIMESTAMP,
    fecha_aprobacion TIMESTAMP,
    aprobado_por UUID REFERENCES usuarios(id),
    url_pdf VARCHAR(500),
    url_excel VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Permisos de servidumbre
CREATE TABLE permisos_servidumbre (
    id UUID PRIMARY KEY,
    torre_id UUID REFERENCES torres(id),
    propietario_nombre VARCHAR(200) NOT NULL,
    propietario_documento VARCHAR(20),
    predio_nombre VARCHAR(200),
    fecha_autorizacion DATE NOT NULL,
    fecha_vencimiento DATE,
    url_documento_firmado VARCHAR(500),
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### FASE 5: Módulo Financiero y Facturación (Semanas 18-20)

#### Semana 18-19: Control de Costos

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F5.1 | Modelo: costos por recurso | Tabla `costos_recursos` |
| F5.2 | Modelo: presupuesto mensual | Tabla `presupuestos` |
| F5.3 | Cálculo automático de costos por actividad | Motor de cálculo |
| F5.4 | Proyección de costos del mes | Dashboard financiero |
| F5.5 | Comparativo presupuesto vs real | Gráficos comparativos |
| F5.6 | Alertas de desviación presupuestal | Sistema alertas |

**Esquema de Base de Datos (Módulo Financiero):**

```sql
-- Costos de recursos
CREATE TABLE costos_recursos (
    id UUID PRIMARY KEY,
    tipo_recurso VARCHAR(50) NOT NULL, -- 'DIA_HOMBRE' | 'VEHICULO' | 'VIATICO'
    descripcion VARCHAR(200),
    costo_unitario DECIMAL(12,2) NOT NULL,
    unidad VARCHAR(20), -- 'DIA' | 'HORA' | 'UNIDAD'
    vigencia_desde DATE NOT NULL,
    vigencia_hasta DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Presupuesto mensual
CREATE TABLE presupuestos (
    id UUID PRIMARY KEY,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    linea_id UUID REFERENCES lineas(id),
    dias_hombre_planeados INTEGER,
    costo_dias_hombre DECIMAL(14,2),
    dias_vehiculo_planeados INTEGER,
    costo_vehiculos DECIMAL(14,2),
    viaticos_planeados DECIMAL(14,2),
    otros_costos DECIMAL(14,2),
    total_presupuestado DECIMAL(14,2),
    total_ejecutado DECIMAL(14,2),
    estado VARCHAR(20) DEFAULT 'PROYECTADO', -- 'PROYECTADO' | 'APROBADO' | 'CERRADO'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Ejecución de costos
CREATE TABLE ejecucion_costos (
    id UUID PRIMARY KEY,
    presupuesto_id UUID REFERENCES presupuestos(id),
    actividad_id UUID REFERENCES actividades(id),
    concepto VARCHAR(100) NOT NULL,
    cantidad DECIMAL(10,2) NOT NULL,
    costo_unitario DECIMAL(12,2) NOT NULL,
    costo_total DECIMAL(14,2) NOT NULL,
    fecha DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Semana 20: Cuadro de Facturación

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F5.7 | Generación de cuadro de costos | Reporte facturación |
| F5.8 | Formato compatible con Transelca/Intercolombia | Template Excel |
| F5.9 | Seguimiento del ciclo de facturación | Workflow estados |
| F5.10 | Dashboard de estado de facturas | Panel financiero |
| F5.11 | Histórico de días promedio de pago | Métricas |

**Ciclo de Facturación:**

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Informe    │───▶│ Validación  │───▶│   Orden     │───▶│  Factura    │───▶│   Pago      │
│  Generado   │    │  Cliente    │    │  Entrega    │    │  Emitida    │    │  Recibido   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                  │                  │                  │                  │
      ▼                  ▼                  ▼                  ▼                  ▼
   Día 1             Día 5-10          Día 10-15          Día 15-20          Día 25-30
```

---

### FASE 6: Módulo de Indicadores y ANS (Semana 21)

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F6.1 | Definición de KPIs contractuales | Configuración indicadores |
| F6.2 | Cálculo automático de ANS | Motor de métricas |
| F6.3 | Dashboard ejecutivo | Panel gerencial |
| F6.4 | Alertas cuando indicador < 85% | Sistema alertas |
| F6.5 | Generación de acta de seguimiento | Template acta |
| F6.6 | Proyección de cierre de mes | Predicciones |

**Indicadores ANS:**

| Indicador | Fórmula | Meta |
|-----------|---------|------|
| Gestión de Mantenimiento | (Actividades ejecutadas / Actividades programadas) × 100 | ≥ 95% |
| Ejecución de Mantenimiento | (Actividades completadas a tiempo / Total actividades) × 100 | ≥ 90% |
| Gestión Ambiental | (Informes entregados a tiempo / Informes requeridos) × 100 | ≥ 95% |
| Accidentalidad | Días sin accidentes incapacitantes | Meta variable |
| Calidad de Información | (Registros completos / Total registros) × 100 | ≥ 98% |

---

### FASE 7: Pruebas y QA (Semanas 22-23)

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F7.1 | Pruebas unitarias (cobertura > 80%) | Reportes de cobertura |
| F7.2 | Pruebas de integración | Suite de tests E2E |
| F7.3 | Pruebas de carga y estrés | Informe de rendimiento |
| F7.4 | Pruebas de usabilidad | Feedback usuarios |
| F7.5 | Pruebas offline (móvil) | Escenarios sin conexión |
| F7.6 | Pruebas de seguridad | Auditoría seguridad |
| F7.7 | Piloto con 2 cuadrillas | Validación en campo |
| F7.8 | Corrección de bugs críticos | Fixes |

---

### FASE 8: Despliegue y Capacitación (Semanas 24-26)

| Tarea | Descripción | Entregable |
|-------|-------------|------------|
| F8.1 | Configuración ambiente producción (GCP) | Infraestructura prod |
| F8.2 | Migración de datos históricos | Datos migrados |
| F8.3 | Configuración de backups automáticos | Política de respaldos |
| F8.4 | Configuración de monitoreo (logs, métricas) | Dashboards ops |
| F8.5 | Capacitación usuarios administrativos | Sesiones training |
| F8.6 | Capacitación personal de campo | Sesiones prácticas |
| F8.7 | Documentación de usuario | Manuales |
| F8.8 | Documentación técnica | Docs técnicos |
| F8.9 | Acompañamiento primera semana producción | Soporte on-site |

---

## 3. Modelo de Datos Completo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MODELO ENTIDAD-RELACIÓN                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   USUARIOS   │       │  CUADRILLAS  │       │  VEHÍCULOS   │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id           │◄──────│ supervisor_id│       │ id           │
│ nombre       │       │ id           │◄──────│ placa        │
│ email        │       │ codigo       │       │ tipo         │
│ rol          │       │ nombre       │───────│ costo_dia    │
│ telefono     │       │ vehiculo_id  │───────┤              │
└──────────────┘       └──────────────┘       └──────────────┘
       │                      │
       │                      │
       ▼                      ▼
┌──────────────┐       ┌──────────────┐
│  CUADRILLA   │       │  ACTIVIDADES │
│  MIEMBROS    │       ├──────────────┤
├──────────────┤       │ id           │
│ cuadrilla_id │       │ linea_id     │◄──────┐
│ usuario_id   │       │ torre_id     │◄──┐   │
│ rol          │       │ tipo_activ_id│   │   │
└──────────────┘       │ cuadrilla_id │   │   │
                       │ estado       │   │   │
                       │ fecha_prog   │   │   │
                       └──────────────┘   │   │
                              │           │   │
                              ▼           │   │
                       ┌──────────────┐   │   │
                       │  REGISTROS   │   │   │
                       │   CAMPO      │   │   │
                       ├──────────────┤   │   │
                       │ actividad_id │   │   │
                       │ usuario_id   │   │   │      ┌──────────────┐
                       │ lat/long     │   │   │      │   LÍNEAS     │
                       │ datos_form   │   │   │      ├──────────────┤
                       └──────────────┘   │   └──────│ id           │
                              │           │          │ codigo       │
                              ▼           │          │ nombre       │
                       ┌──────────────┐   │          │ cliente      │
                       │  EVIDENCIAS  │   │          └──────────────┘
                       ├──────────────┤   │                 │
                       │ registro_id  │   │                 │
                       │ tipo         │   │                 ▼
                       │ url          │   │          ┌──────────────┐
                       │ lat/long     │   │          │   TORRES     │
                       │ validacion_ia│   └──────────├──────────────┤
                       └──────────────┘              │ id           │
                                                     │ linea_id     │
                                                     │ numero       │
                                                     │ lat/long     │
                                                     └──────────────┘
                                                            │
                                                            ▼
                                                     ┌──────────────┐
                                                     │  POLÍGONOS   │
                                                     │ SERVIDUMBRE  │
                                                     ├──────────────┤
                                                     │ torre_id     │
                                                     │ geometria    │
                                                     └──────────────┘
```

---

## 4. APIs Principales

### 4.1 Endpoints REST

```yaml
# Autenticación
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout

# Usuarios
GET    /api/usuarios
POST   /api/usuarios
GET    /api/usuarios/:id
PUT    /api/usuarios/:id
DELETE /api/usuarios/:id

# Líneas
GET    /api/lineas
POST   /api/lineas
GET    /api/lineas/:id
GET    /api/lineas/:id/torres

# Torres
GET    /api/torres
GET    /api/torres/:id
GET    /api/torres/:id/poligono

# Actividades
GET    /api/actividades
POST   /api/actividades
GET    /api/actividades/:id
PUT    /api/actividades/:id
GET    /api/actividades/cuadrilla/:cuadrillaId
GET    /api/actividades/fecha/:fecha

# Registros de Campo
POST   /api/registros
GET    /api/registros/:id
PUT    /api/registros/:id
POST   /api/registros/:id/evidencias
POST   /api/registros/sync  # Sincronización batch

# Cuadrillas
GET    /api/cuadrillas
POST   /api/cuadrillas
GET    /api/cuadrillas/:id
GET    /api/cuadrillas/:id/ubicacion

# Programación
GET    /api/programacion/mes/:anio/:mes
POST   /api/programacion/importar-excel
GET    /api/programacion/comparativo/:anio/:mes

# Informes
GET    /api/informes/ambiental/:anio/:mes
POST   /api/informes/ambiental/generar
GET    /api/informes/ambiental/:id/pdf

# Financiero
GET    /api/presupuesto/:anio/:mes
POST   /api/presupuesto
GET    /api/costos/cuadro-facturacion/:anio/:mes
GET    /api/costos/comparativo/:anio/:mes

# Indicadores
GET    /api/indicadores/:anio/:mes
GET    /api/indicadores/dashboard
GET    /api/indicadores/acta/:anio/:mes
```

### 4.2 WebSocket Events

```typescript
// Servidor → Cliente
'cuadrilla:ubicacion'      // Actualización de ubicación GPS
'actividad:actualizada'    // Cambio de estado de actividad
'registro:sincronizado'    // Confirmación de sincronización
'alerta:nueva'             // Nueva alerta del sistema

// Cliente → Servidor
'ubicacion:actualizar'     // Enviar nueva ubicación
'actividad:iniciar'        // Marcar inicio de actividad
'actividad:finalizar'      // Marcar fin de actividad
```

---

## 5. Validaciones Críticas

### 5.1 Validación de Fotos (IA)

```python
# Modelo TensorFlow Lite para validación en dispositivo
class PhotoValidator:
    def validate(self, image) -> ValidationResult:
        return {
            'nitidez': float,      # 0-1, mínimo 0.7
            'iluminacion': float,  # 0-1, mínimo 0.5
            'blur_score': float,   # 0-1, máximo 0.3
            'valida': bool,
            'mensaje': str         # Razón si es inválida
        }
```

### 5.2 Validación de Geolocalización

```sql
-- Función PostGIS para validar punto dentro de polígono
CREATE FUNCTION validar_ubicacion_servidumbre(
    p_latitud DECIMAL,
    p_longitud DECIMAL,
    p_torre_id UUID
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM poligonos_servidumbre ps
        WHERE ps.torre_id = p_torre_id
        AND ST_Contains(
            ps.geometria,
            ST_SetSRID(ST_MakePoint(p_longitud, p_latitud), 4326)
        )
    );
END;
$$ LANGUAGE plpgsql;
```

---

## 6. Configuración de Infraestructura

### 6.1 Docker Compose (Desarrollo)

```yaml
version: '3.8'
services:
  postgres:
    image: postgis/postgis:15-3.3
    environment:
      POSTGRES_DB: transmaint
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: ./apps/api
    environment:
      DATABASE_URL: postgresql://admin:${DB_PASSWORD}@postgres:5432/transmaint
      REDIS_URL: redis://redis:6379
      JWT_SECRET: ${JWT_SECRET}
    ports:
      - "3000:3000"
    depends_on:
      - postgres
      - redis

  web:
    build: ./apps/web
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:3000
    ports:
      - "3001:3000"
    depends_on:
      - api

volumes:
  postgres_data:
```

### 6.2 Terraform (GCP Producción)

```hcl
# Resumen de recursos a provisionar
resource "google_cloud_run_service" "api" { }
resource "google_cloud_run_service" "web" { }
resource "google_sql_database_instance" "main" { }
resource "google_storage_bucket" "evidencias" { }
resource "google_redis_instance" "cache" { }
resource "google_cloud_scheduler_job" "backups" { }
```

---

## 7. Métricas de Éxito

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Tiempo de digitación informes | Reducir 80% | Horas/mes |
| Registros con información completa | > 95% | % registros |
| Actividades con geolocalización válida | > 98% | % actividades |
| Tiempo de sincronización offline | < 30 segundos | Tiempo promedio |
| Adopción de app móvil | 100% cuadrillas | % usuarios activos |
| Uptime del sistema | > 99.5% | Disponibilidad |
| Ciclo de facturación | < 20 días | Días promedio |

---

## 8. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Resistencia al cambio | Alta | Alto | Capacitación práctica, UI simple, acompañamiento |
| Conectividad en campo | Alta | Medio | Modo offline robusto, cola de sincronización |
| Pérdida de datos | Baja | Alto | Backups automáticos, sincronización incremental |
| Cambios de requerimientos | Media | Medio | Diseño modular, sprints cortos |
| Rendimiento de la app | Media | Alto | Optimización continua, pruebas de carga |

---

## 9. Entregables por Fase

| Fase | Entregables |
|------|-------------|
| Fase 1 | Arquitectura, BD inicial, autenticación funcional |
| Fase 2 | App móvil MVP con captura completa |
| Fase 3 | Portal web con programación y mapa |
| Fase 4 | Módulo ambiental con generación de informes |
| Fase 5 | Módulo financiero y facturación |
| Fase 6 | Dashboard de indicadores ANS |
| Fase 7 | Sistema probado y validado |
| Fase 8 | Sistema en producción, usuarios capacitados |

---

## 10. Próximos Pasos Inmediatos

1. **Validar este plan** con stakeholders de Instelec
2. **Definir prioridades** si se requiere ajustar alcance
3. **Configurar repositorio** y estructura de proyecto
4. **Iniciar Fase 1** con setup de infraestructura
5. **Agendar sesiones** de levantamiento detallado de requerimientos

---

*Documento generado: Enero 2026*
*Versión: 1.0*
