# Comparativo de Infraestructura Tecnológica

## Propuesta Inicial vs Estándar Indunnova

---

## 1. Resumen Ejecutivo

| Aspecto | Propuesta Inicial | Estándar Indunnova | Recomendación |
|---------|-------------------|-------------------|---------------|
| **Backend** | Node.js + NestJS | Python + Django 5.1 | **Indunnova** ✓ |
| **Frontend Web** | Next.js + React | HTMX + Alpine.js + Tailwind | **Indunnova** ✓ |
| **App Móvil** | Flutter | No especificado | **Mantener Flutter** |
| **Base de Datos** | PostgreSQL + PostGIS | PostgreSQL 16/17 | **Ambos** (añadir PostGIS) |
| **Cache** | Redis | Redis 7.x | **Igual** ✓ |
| **Tareas Async** | No especificado | Celery + Redis | **Indunnova** ✓ |
| **Cloud** | GCP | DigitalOcean/Railway | **Indunnova** (más simple) |

---

## 2. Comparativo Detallado por Capa

### 2.1 Backend

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Lenguaje | TypeScript/Node.js | Python 3.12/3.13 | Python tiene mejor ecosistema para procesamiento de datos, reportes y IA |
| Framework | NestJS | Django 5.1 LTS | Django es más maduro, incluye ORM, admin, auth out-of-the-box |
| API REST | Express custom | Django REST Framework + Ninja | DRF es estándar de la industria, Ninja añade rendimiento |
| ORM | TypeORM/Prisma | Django ORM | Django ORM es más simple y bien integrado |
| Autenticación | JWT custom | Django Auth + OTP + OIDC | Django tiene sistema robusto integrado |
| Admin Panel | Construir desde cero | Django Admin | Ahorra semanas de desarrollo |

**Ventajas de Django para este proyecto:**
- Admin panel listo para gestión de datos maestros
- ORM maduro con soporte geoespacial (GeoDjango)
- Generación de reportes más simple (ReportLab, WeasyPrint)
- Mejor integración con librerías de IA/ML (TensorFlow, PyTorch)
- Comunidad más grande en Latinoamérica

### 2.2 APIs

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| REST API | Custom NestJS | Django REST Framework 3.15+ | DRF es más maduro |
| Alto rendimiento | - | Django Ninja | Pydantic validation, async support |
| GraphQL | - | Strawberry | Útil para dashboards complejos |
| Documentación | Swagger manual | drf-spectacular (automático) | Mejor DX |
| WebSockets | Socket.io | Django Channels | Integrado con Django |

### 2.3 Frontend Web

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Framework | Next.js 14 (React) | HTMX + Alpine.js | HTMX más simple, menos JS |
| CSS | TailwindCSS | TailwindCSS + daisyUI | Igual, daisyUI añade componentes |
| Bundle Size | ~200KB+ (React) | ~30KB (HTMX + Alpine) | Indunnova más ligero |
| SEO | SSR complejo | Nativo en Django | Más simple |
| Curva aprendizaje | Alta (React) | Baja (HTML + attrs) | Más accesible |
| Complejidad | Alta | Baja-Media | Menor mantenimiento |

**¿Por qué HTMX + Alpine.js es mejor para este proyecto?**
- El portal web es principalmente CRUD y dashboards
- No requiere interactividad extrema tipo SPA
- Menor tiempo de desarrollo
- Templates Django reutilizables
- Personal de campo no necesita SPA pesado

### 2.4 App Móvil

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Framework | Flutter | No especificado | **Mantener Flutter** |
| Offline | SQLite + Hive | - | Necesario para campo |
| GPS/Cámara | Plugins Flutter | - | Bien soportado |

**Recomendación:** Mantener Flutter para la app móvil porque:
- Modo offline es crítico para zonas rurales
- Acceso nativo a GPS y cámara
- Una sola codebase para Android/iOS
- El estándar Indunnova no especifica móvil

### 2.5 Base de Datos

| Componente | Propuesta Inicial | Estándar Indunnova | Propuesta Unificada |
|------------|-------------------|-------------------|---------------------|
| Motor | PostgreSQL 15 | PostgreSQL 16/17 | PostgreSQL 17 |
| Geoespacial | PostGIS | No especificado | **Añadir PostGIS** |
| Connection Pool | - | pgBouncer | pgBouncer |
| Cache Queries | - | django-cachalot | django-cachalot |

### 2.6 Cache y Rendimiento

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Cache | Redis | Redis 7.x | Igual |
| Broker | - | Redis (Celery) | Añadir Celery |
| Static Files | Cloud Storage | WhiteNoise | WhiteNoise más simple |
| CDN | GCP CDN | CloudFlare | CloudFlare más económico |

### 2.7 Tareas Asíncronas

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Sistema | No definido | Celery + Beat | **Crítico para reportes** |
| Colas | - | Múltiples (high, default, reports) | Necesario |
| Scheduler | - | django-celery-beat | Para informes programados |

**Tareas asíncronas necesarias:**
- Generación de informes PDF/Excel
- Procesamiento de fotos (compresión, validación IA)
- Sincronización de datos desde app móvil
- Envío de notificaciones
- Backups automáticos

### 2.8 Infraestructura Cloud

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Plataforma | GCP (Cloud Run, etc) | DigitalOcean/Railway | Indunnova más simple y económico |
| Archivos | Google Cloud Storage | MinIO / S3 | MinIO self-hosted más económico |
| Deploy | Kubernetes | App Platform | Menos complejidad operativa |
| Costo estimado/mes | $300-500 USD | $100-200 USD | 50-60% menos |

### 2.9 Seguridad

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Brute force | - | django-axes | Incluir |
| CSP | - | django-csp | Incluir |
| 2FA | - | django-otp | Importante para supervisores |
| Secretos | Env vars | Vault/AWS Secrets | Vault en producción |
| CORS | - | django-cors-headers | Necesario para app móvil |

### 2.10 Testing y Calidad

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Framework | Jest | pytest-django | pytest más expresivo |
| Coverage | 80% | 80% | Igual |
| E2E | - | Playwright | Incluir |
| Linting | ESLint | Ruff | Ruff es ultrarrápido |
| Types | TypeScript | mypy | Ambos válidos |
| Pre-commit | - | pre-commit hooks | Importante |

### 2.11 Monitoreo

| Componente | Propuesta Inicial | Estándar Indunnova | Análisis |
|------------|-------------------|-------------------|----------|
| Errores | - | Sentry | Crítico en producción |
| Métricas | - | Prometheus + Grafana | Para SLAs |
| Logs | - | Loki | Centralización |
| Uptime | - | Uptime Kuma | Simple y efectivo |
| Profiling | - | django-silk | Útil en desarrollo |

---

## 3. Arquitectura Propuesta Unificada

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ARQUITECTURA HÍBRIDA RECOMENDADA                      │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   CloudFlare    │
                              │   (CDN + WAF)   │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │     NGINX       │
                              │  (Reverse Proxy)│
                              └────────┬────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
    │   Portal Web    │     │    REST API     │     │   API Móvil     │
    │                 │     │                 │     │                 │
    │ Django 5.1      │     │ Django Ninja    │     │ Django Ninja    │
    │ + HTMX          │     │ (Alto rend.)    │     │ + JWT Auth      │
    │ + Alpine.js     │     │                 │     │                 │
    │ + Tailwind      │     │                 │     │                 │
    └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
             │                       │                       │
             └───────────────────────┼───────────────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │   Django Core       │
                          │                     │
                          │ • GeoDjango         │
                          │ • Django Admin      │
                          │ • Celery Tasks      │
                          │ • Django Channels   │
                          └──────────┬──────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  PostgreSQL 17  │       │    Redis 7.x    │       │   MinIO / S3    │
│  + PostGIS      │       │                 │       │                 │
│                 │       │ • Cache         │       │ • Fotos         │
│ • Datos         │       │ • Sesiones      │       │ • Documentos    │
│ • Geometrías    │       │ • Celery Broker │       │ • Reportes      │
└─────────────────┘       └─────────────────┘       └─────────────────┘
         │
         │ pgBouncer
         │ (Connection Pool)
         ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│                            PROCESAMIENTO ASYNC                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ Celery Worker   │  │ Celery Worker   │  │ Celery Beat     │             │
│  │ (high_priority) │  │ (reports)       │  │ (scheduler)     │             │
│  │                 │  │                 │  │                 │             │
│  │ • Sync móvil    │  │ • PDFs          │  │ • Backups       │             │
│  │ • Notificaciones│  │ • Excel         │  │ • Informes auto │             │
│  │ • Validación IA │  │ • Consolidados  │  │ • Limpieza      │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              APP MÓVIL (Flutter)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Flutter App                                  │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │   UI Layer   │  │  BLoC/Cubit  │  │  Repository  │              │   │
│  │  │              │  │  (State Mgmt)│  │   Pattern    │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │   SQLite     │  │    Hive      │  │  Dio + Retry │              │   │
│  │  │  (Offline)   │  │   (Cache)    │  │  (HTTP/Sync) │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  │                                                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │  Geolocator  │  │   Camera     │  │  TFLite      │              │   │
│  │  │    (GPS)     │  │  (Fotos)     │  │  (Valid. IA) │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Estructura del Proyecto Actualizada

```
transmaint/
├── apps/                           # Aplicaciones Django
│   ├── core/                       # Modelos base, mixins
│   ├── usuarios/                   # Autenticación, roles, permisos
│   ├── lineas/                     # Líneas y torres (GeoDjango)
│   ├── actividades/                # Programación y ejecución
│   ├── cuadrillas/                 # Gestión de cuadrillas
│   ├── campo/                      # Registros de campo, evidencias
│   ├── ambiental/                  # Informes ambientales
│   ├── financiero/                 # Presupuestos, facturación
│   ├── indicadores/                # KPIs y ANS
│   └── api/                        # Django Ninja API para móvil
│
├── config/                         # Configuración Django
│   ├── settings/
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── staging.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py
│
├── templates/                      # Templates Django + HTMX
│   ├── base.html
│   ├── components/                 # Componentes reutilizables
│   ├── partials/                   # Fragmentos HTMX
│   └── [app]/                      # Templates por app
│
├── static/                         # Archivos estáticos
│   ├── css/
│   ├── js/
│   └── img/
│
├── mobile/                         # App Flutter
│   ├── lib/
│   │   ├── core/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── actividades/
│   │   │   ├── captura/
│   │   │   └── sync/
│   │   └── main.dart
│   ├── android/
│   └── ios/
│
├── infrastructure/                 # DevOps
│   ├── docker/
│   │   ├── Dockerfile
│   │   ├── Dockerfile.celery
│   │   └── docker-compose.yml
│   ├── nginx/
│   └── scripts/
│
├── docs/                           # Documentación MkDocs
│   ├── mkdocs.yml
│   └── docs/
│
├── tests/                          # Tests pytest
│   ├── conftest.py
│   ├── factories/
│   └── [app]/
│
├── requirements/
│   ├── base.txt
│   ├── local.txt
│   └── production.txt
│
├── .pre-commit-config.yaml
├── pyproject.toml                  # Ruff, mypy config
├── pytest.ini
└── manage.py
```

---

## 5. Stack Tecnológico Final

### 5.1 Backend (Python/Django)

```txt
# requirements/base.txt

# Core
Django>=5.1,<5.2
psycopg[binary]>=3.1
python-decouple>=3.8

# APIs
djangorestframework>=3.15
django-ninja>=1.0
drf-spectacular>=0.27

# GeoDjango
GDAL>=3.6
django-leaflet>=0.29

# Async Tasks
celery>=5.3
django-celery-beat>=2.5
redis>=5.0

# Cache & Performance
django-cachalot>=2.6
django-redis>=5.4

# Auth & Security
djangorestframework-simplejwt>=5.3
django-axes>=6.3
django-cors-headers>=4.3
django-otp>=1.3

# Files & Media
django-storages>=1.14
boto3>=1.34  # Para S3/MinIO
Pillow>=10.2

# Reports
WeasyPrint>=60.0
openpyxl>=3.1
pandas>=2.1

# Utilities
django-extensions>=3.2
django-filter>=23.5
whitenoise>=6.6
```

### 5.2 Frontend (HTMX + Alpine.js)

```json
// package.json
{
  "dependencies": {
    "htmx.org": "^2.0",
    "alpinejs": "^3.14",
    "@alpinejs/persist": "^3.14",
    "@alpinejs/focus": "^3.14"
  },
  "devDependencies": {
    "tailwindcss": "^3.4",
    "daisyui": "^4.6",
    "@tailwindcss/forms": "^0.5",
    "@tailwindcss/typography": "^0.5",
    "vite": "^5.0"
  }
}
```

### 5.3 Visualización de Datos

```txt
# CDN o npm
echarts@5.5              # Dashboards y gráficos
ag-grid-community@31     # Tablas avanzadas
leaflet@1.9              # Mapas
```

### 5.4 App Móvil (Flutter)

```yaml
# pubspec.yaml
dependencies:
  flutter:
    sdk: flutter

  # State Management
  flutter_bloc: ^8.1

  # Networking
  dio: ^5.4
  retrofit: ^4.1

  # Local Storage
  sqflite: ^2.3
  hive_flutter: ^1.1

  # Location & Camera
  geolocator: ^11.0
  camera: ^0.10
  image_picker: ^1.0

  # AI Validation
  tflite_flutter: ^0.10

  # UI
  flutter_form_builder: ^9.2
  signature_pad: ^4.1

  # Utilities
  connectivity_plus: ^5.0
  workmanager: ^0.5  # Background sync
```

---

## 6. Comparativo de Esfuerzo de Desarrollo

| Módulo | Con Node/React | Con Django/HTMX | Ahorro |
|--------|---------------|-----------------|--------|
| Autenticación + Roles | 2 semanas | 3 días | 80% |
| Admin de datos maestros | 3 semanas | 1 semana (Django Admin) | 66% |
| API REST | 2 semanas | 1 semana (DRF) | 50% |
| Portal Web | 4 semanas | 2.5 semanas | 37% |
| Reportes PDF/Excel | 2 semanas | 1 semana | 50% |
| Background Jobs | 1 semana | 2 días (Celery) | 70% |
| **Total Backend+Web** | **14 semanas** | **7 semanas** | **50%** |

---

## 7. Comparativo de Costos

### Infraestructura Mensual

| Componente | GCP (Original) | DigitalOcean (Indunnova) |
|------------|---------------|--------------------------|
| Servidores App | $150 | $48 (2x Droplets) |
| Base de Datos | $100 | $30 (Managed DB) |
| Redis | $50 | $15 |
| Storage (500GB) | $50 | $25 (Spaces) |
| CDN/WAF | $50 | $0 (CloudFlare free) |
| Monitoreo | $30 | $0 (Self-hosted) |
| **Total** | **$430/mes** | **$118/mes** |
| **Anual** | **$5,160** | **$1,416** |

### Ahorro en Desarrollo

| Concepto | Original | Con Stack Indunnova |
|----------|----------|---------------------|
| Semanas desarrollo | 26 | 18-20 |
| Costo equipo | ~$99M COP | ~$70M COP |
| Infraestructura año 1 | $11.7M COP | $5M COP |

---

## 8. Cronograma Revisado

```
SEMANA   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20
         ├───┴───┴───┴───┼───┴───┴───┴───┼───┴───┴───┴───┼───┴───┴───┴───┼───┴───┴───┤
         │    FASE 1     │    FASE 2     │    FASE 3     │    FASE 4     │   FASE 5  │
         │   Setup +     │  App Móvil    │   Portal +    │  Ambiental +  │  Pruebas  │
         │    Auth       │   Campo       │  Programación │  Financiero   │  Deploy   │
         │               │               │               │               │           │
         │ • Django      │ • Flutter     │ • HTMX Views  │ • Reportes    │ • QA      │
         │ • GeoDjango   │ • Offline     │ • Dashboards  │ • Celery      │ • Piloto  │
         │ • API Ninja   │ • Sync        │ • Mapas       │ • PDFs        │ • Train   │
         │ • Admin       │ • GPS/Cam     │ • Real-time   │ • KPIs        │ • Go-live │
         └───────────────┴───────────────┴───────────────┴───────────────┴───────────┘
```

---

## 9. Recomendaciones Finales

### ✅ Adoptar del Estándar Indunnova

1. **Django 5.1** como framework backend
2. **HTMX + Alpine.js** para el portal web
3. **Celery** para tareas asíncronas
4. **DigitalOcean** como plataforma cloud
5. **Ruff + pre-commit** para calidad de código
6. **Sentry** para monitoreo de errores
7. **pytest** como framework de testing

### ✅ Mantener de la Propuesta Original

1. **Flutter** para la app móvil (no hay alternativa en Indunnova)
2. **PostGIS** para datos geoespaciales (añadir a PostgreSQL)
3. **TensorFlow Lite** para validación de fotos en dispositivo
4. **WebSockets** (Django Channels) para tiempo real

### ✅ Agregar

1. **Django Ninja** para API móvil de alto rendimiento
2. **GeoDjango** para manejo de geometrías
3. **MinIO** como alternativa económica a S3
4. **ECharts** para visualizaciones (mejor que Chart.js)
5. **AG Grid** para tablas de datos complejas

---

## 10. Conclusión

La adopción del estándar Indunnova ofrece:

| Beneficio | Impacto |
|-----------|---------|
| Reducción tiempo desarrollo | ~30% menos |
| Reducción costo infraestructura | ~70% menos |
| Menor complejidad técnica | Mantenimiento más simple |
| Mejor alineación con equipo | Stack conocido por Indunnova |
| Django Admin incluido | Semanas de desarrollo ahorradas |

**Recomendación:** Adoptar el stack de Indunnova para backend y web, manteniendo Flutter para la app móvil. Esto reduce riesgos, costos y tiempos manteniendo todas las funcionalidades requeridas.

---

*Documento de comparativo - Enero 2026*
