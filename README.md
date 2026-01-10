# TransMaint

**Sistema de Gestion Integral para Mantenimiento de Lineas de Transmision**

TransMaint es una plataforma completa para la gestion de operaciones de mantenimiento en lineas de transmision electrica. Permite la planificacion, ejecucion y seguimiento de actividades de mantenimiento con soporte para trabajo en campo, geolocalizacion, captura de evidencias y generacion de reportes.

## Tecnologias

- **Backend**: Django 5.1 con Python 3.12
- **Base de Datos**: PostgreSQL 16 con PostGIS (soporte geoespacial)
- **Cache/Broker**: Redis 7
- **Tareas Asincronas**: Celery
- **API**: Django Ninja (OpenAPI/Swagger)
- **Autenticacion**: JWT (JSON Web Tokens)
- **Almacenamiento**: Google Cloud Storage
- **Reportes**: WeasyPrint (PDF), OpenPyXL (Excel)

## Inicio Rapido

### Prerrequisitos

- Python 3.12+
- PostgreSQL 16+ con PostGIS
- Redis 7+
- GDAL (para GeoDjango)

### Instalacion

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/indunnova/transmaint.git
   cd transmaint
   ```

2. **Crear entorno virtual**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # o
   venv\Scripts\activate  # Windows
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements/local.txt
   ```

4. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Editar .env con tus configuraciones
   ```

5. **Ejecutar migraciones**
   ```bash
   python manage.py migrate
   ```

6. **Crear superusuario**
   ```bash
   python manage.py createsuperuser
   ```

7. **Cargar datos iniciales (opcional)**
   ```bash
   python manage.py seed_data
   ```

8. **Iniciar servidor de desarrollo**
   ```bash
   python manage.py runserver
   ```

### Comandos Make

El proyecto incluye un `Makefile` con comandos utiles:

```bash
make install      # Instalar dependencias
make migrate      # Ejecutar migraciones
make run          # Iniciar servidor de desarrollo
make test         # Ejecutar todos los tests
make coverage     # Tests con reporte de cobertura
make lint         # Verificar codigo con ruff
make format       # Formatear codigo con ruff
make clean        # Limpiar archivos temporales
```

## Variables de Entorno

| Variable | Descripcion | Ejemplo |
|----------|-------------|---------|
| `DEBUG` | Modo debug | `True` |
| `SECRET_KEY` | Clave secreta Django | `your-secret-key` |
| `DJANGO_SETTINGS_MODULE` | Modulo de configuracion | `config.settings.local` |
| `DATABASE_URL` | URL de conexion PostgreSQL/PostGIS | `postgis://user:pass@localhost:5432/transmaint` |
| `REDIS_URL` | URL de conexion Redis | `redis://localhost:6379/0` |
| `GS_BUCKET_NAME` | Bucket de Google Cloud Storage | `transmaint-media` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta a credenciales GCS | `/path/to/credentials.json` |
| `SENTRY_DSN` | DSN de Sentry (opcional) | `https://xxx@sentry.io/xxx` |
| `EMAIL_HOST` | Servidor SMTP | `smtp.gmail.com` |
| `EMAIL_PORT` | Puerto SMTP | `587` |
| `EMAIL_HOST_USER` | Usuario SMTP | `user@gmail.com` |
| `EMAIL_HOST_PASSWORD` | Password SMTP | `app-password` |
| `ALLOWED_HOSTS` | Hosts permitidos | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Origenes CORS permitidos | `http://localhost:3000` |
| `JWT_ACCESS_TOKEN_LIFETIME` | Duracion token acceso (minutos) | `60` |
| `JWT_REFRESH_TOKEN_LIFETIME` | Duracion refresh token (minutos) | `1440` |

## Estructura del Proyecto

```
transmaint/
├── apps/                          # Aplicaciones Django
│   ├── actividades/               # Gestion de actividades programadas
│   ├── ambiental/                 # Modulo ambiental y reportes
│   ├── api/                       # Configuracion API (Django Ninja)
│   ├── campo/                     # Registros de campo y evidencias
│   ├── core/                      # Modelos base y utilidades
│   ├── cuadrillas/                # Gestion de cuadrillas y vehiculos
│   ├── financiero/                # Modulo financiero y costos
│   ├── indicadores/               # KPIs y metricas
│   ├── lineas/                    # Lineas de transmision y torres
│   └── usuarios/                  # Autenticacion y usuarios
├── config/                        # Configuracion Django
│   ├── settings/                  # Configuraciones por ambiente
│   ├── celery.py                  # Configuracion Celery
│   ├── urls.py                    # URLs principales
│   └── wsgi.py                    # WSGI entry point
├── docs/                          # Documentacion
│   └── API.md                     # Documentacion de la API
├── infrastructure/                # Configuracion de infraestructura
├── mobile/                        # Recursos para app movil
├── requirements/                  # Dependencias por ambiente
│   ├── base.txt                   # Dependencias base
│   ├── local.txt                  # Dependencias desarrollo
│   └── production.txt             # Dependencias produccion
├── templates/                     # Templates HTML
├── tests/                         # Tests
│   ├── e2e/                       # Tests end-to-end
│   ├── factories/                 # Factories para tests
│   ├── integration/               # Tests de integracion
│   └── unit/                      # Tests unitarios
├── .env.example                   # Ejemplo de variables de entorno
├── conftest.py                    # Configuracion pytest
├── manage.py                      # CLI Django
├── Makefile                       # Comandos make
└── pyproject.toml                 # Configuracion del proyecto
```

## Modulos Principales

### Lineas y Torres
Gestion de la infraestructura de lineas de transmision, incluyendo:
- Registro de lineas con datos tecnicos (tension, longitud, cliente)
- Torres con coordenadas GPS y poligonos de servidumbre
- Validacion de ubicacion en campo mediante geofencing

### Actividades
Programacion y seguimiento de actividades de mantenimiento:
- Tipos de actividad configurables con formularios dinamicos
- Programacion mensual por linea
- Estados de seguimiento (pendiente, en curso, completada)
- Asignacion a cuadrillas

### Campo
Captura de informacion en campo con la app movil:
- Registros de campo con geolocalizacion
- Evidencias fotograficas con validacion
- Firma digital del responsable
- Sincronizacion offline/online

### Cuadrillas
Gestion de equipos de trabajo:
- Cuadrillas con supervisor y miembros
- Vehiculos asignados
- Tracking de ubicacion en tiempo real

### Indicadores
Metricas y KPIs del proyecto:
- Avance de actividades
- Cumplimiento de programacion
- Costos y rendimiento

## Documentacion API

La API REST esta documentada con OpenAPI/Swagger. Una vez el servidor este corriendo:

- **Swagger UI**: http://localhost:8000/api/docs
- **Documentacion detallada**: [docs/API.md](docs/API.md)

## Servicios Adicionales

### Celery Worker

Para procesamiento de tareas asincronas (evidencias, reportes):

```bash
celery -A config worker -l info
```

### Celery Beat

Para tareas programadas:

```bash
celery -A config beat -l info
```

## Testing

```bash
# Todos los tests
make test

# Solo tests unitarios
make test-unit

# Solo tests de integracion
make test-int

# Tests E2E
make test-e2e

# Con cobertura
make coverage
```

## Contribuir

1. Crear una rama desde `develop`
   ```bash
   git checkout -b feature/mi-feature
   ```

2. Hacer commits siguiendo conventional commits
   ```bash
   git commit -m "feat: agregar nueva funcionalidad"
   ```

3. Ejecutar linter y tests antes de hacer push
   ```bash
   make check
   make test
   ```

4. Crear Pull Request hacia `develop`

### Convenciones de Codigo

- Usar `ruff` para linting y formateo
- Seguir PEP 8
- Documentar funciones y clases con docstrings
- Escribir tests para nueva funcionalidad

## Licencia

Copyright (c) 2025 Indunnova S.A.S. Todos los derechos reservados.

Este software es propietario y confidencial. No esta permitida su distribucion, modificacion o uso sin autorizacion expresa por escrito de Indunnova S.A.S.
