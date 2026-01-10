# TransMaint API Documentation

## Descripcion General

La API de TransMaint proporciona acceso programatico a todas las funcionalidades del sistema de gestion de mantenimiento de lineas de transmision. Esta disenada principalmente para la aplicacion movil de campo, pero puede ser utilizada por cualquier cliente que implemente la autenticacion requerida.

**Version**: 1.0.0

## URL Base

| Ambiente | URL Base |
|----------|----------|
| Desarrollo | `http://localhost:8000/api` |
| Staging | `https://staging.transmaint.com/api` |
| Produccion | `https://api.transmaint.com/api` |

## Documentacion Interactiva

- **Swagger UI**: `{BASE_URL}/docs`

## Autenticacion

La API utiliza **JWT (JSON Web Tokens)** para autenticacion.

### Obtener Token

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "usuario@ejemplo.com",
  "password": "contraseña"
}
```

**Respuesta exitosa (200)**:
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "usuario@ejemplo.com",
  "nombre": "Juan Perez",
  "rol": "supervisor"
}
```

### Usar Token

Incluir el token de acceso en el header `Authorization`:

```http
GET /api/actividades/mis-actividades
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Refrescar Token

```http
POST /api/auth/refresh
Content-Type: application/json

{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Respuesta (200)**:
```json
{
  "access": "nuevo-token-de-acceso...",
  "refresh": "nuevo-token-de-refresh..."
}
```

### Duracion de Tokens

| Token | Duracion por Defecto |
|-------|---------------------|
| Access Token | 60 minutos |
| Refresh Token | 24 horas (1440 minutos) |

---

## Rate Limiting

La API implementa limitacion de tasa para proteger contra abusos.

| Tipo | Limite | Identificador |
|------|--------|---------------|
| Login | 5 req/min | IP |
| API General | 100 req/min | Usuario |
| Uploads | 20 req/min | Usuario |

### Headers de Rate Limit

Cada respuesta incluye headers informativos:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067200
```

### Respuesta de Limite Excedido

**HTTP 429 Too Many Requests**
```json
{
  "detail": "Demasiadas solicitudes. Por favor, intente de nuevo mas tarde.",
  "retry_after": 60
}
```

---

## Endpoints

### Sistema

#### Health Check

Verifica el estado del servicio.

```http
GET /api/health
```

**Respuesta (200)**:
```json
{
  "status": "healthy",
  "service": "transmaint-api"
}
```

> **Nota**: Este endpoint no requiere autenticacion.

---

### Autenticacion (`/api/auth/`)

#### POST /api/auth/login

Autenticar usuario y obtener tokens JWT.

**Request Body**:
```json
{
  "email": "string",
  "password": "string"
}
```

**Respuesta (200)**:
```json
{
  "access": "string",
  "refresh": "string",
  "user_id": "uuid",
  "email": "string",
  "nombre": "string",
  "rol": "string"
}
```

**Errores**:
- `401`: Credenciales invalidas o usuario inactivo
- `429`: Rate limit excedido

---

#### POST /api/auth/refresh

Refrescar token de acceso.

**Request Body**:
```json
{
  "refresh": "string"
}
```

**Respuesta (200)**:
```json
{
  "access": "string",
  "refresh": "string"
}
```

---

#### GET /api/auth/me

Obtener informacion del usuario autenticado.

**Respuesta (200)**:
```json
{
  "id": "uuid",
  "email": "string",
  "first_name": "string",
  "last_name": "string",
  "rol": "string",
  "telefono": "string"
}
```

---

### Actividades (`/api/actividades/`)

#### GET /api/actividades/tipos

Listar todos los tipos de actividad.

**Query Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `activo` | boolean | Filtrar por estado activo (default: true) |

**Respuesta (200)**:
```json
[
  {
    "id": "uuid",
    "codigo": "PODA-001",
    "nombre": "Poda de vegetacion en franja de servidumbre",
    "categoria": "PODA",
    "requiere_fotos_antes": true,
    "requiere_fotos_durante": false,
    "requiere_fotos_despues": true,
    "min_fotos": 3,
    "campos_formulario": [...],
    "tiempo_estimado_horas": "2.5"
  }
]
```

---

#### GET /api/actividades/mis-actividades

Listar actividades asignadas a la cuadrilla del usuario.

**Query Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `fecha` | date | Filtrar por fecha (YYYY-MM-DD) |
| `estado` | string | Filtrar por estado (PENDIENTE, EN_CURSO, COMPLETADA) |

**Respuesta (200)**:
```json
[
  {
    "id": "uuid",
    "linea_id": "uuid",
    "linea_codigo": "LT-001",
    "linea_nombre": "Linea Barranquilla - Cartagena",
    "torre_id": "uuid",
    "torre_numero": "T-001",
    "torre_latitud": "10.9878",
    "torre_longitud": "-74.7889",
    "tipo_actividad_id": "uuid",
    "tipo_actividad_nombre": "Poda de vegetacion",
    "tipo_actividad_categoria": "PODA",
    "fecha_programada": "2025-01-15",
    "estado": "PENDIENTE",
    "prioridad": "NORMAL",
    "campos_formulario": [...]
  }
]
```

---

#### GET /api/actividades/{actividad_id}

Obtener detalle de una actividad.

**Path Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `actividad_id` | uuid | ID de la actividad |

**Respuesta (200)**:
```json
{
  "id": "uuid",
  "linea_id": "uuid",
  "linea_codigo": "LT-001",
  "linea_nombre": "Linea Barranquilla - Cartagena",
  "torre_id": "uuid",
  "torre_numero": "T-001",
  "torre_latitud": "10.9878",
  "torre_longitud": "-74.7889",
  "tipo_actividad_id": "uuid",
  "tipo_actividad_nombre": "Poda de vegetacion",
  "tipo_actividad_categoria": "PODA",
  "fecha_programada": "2025-01-15",
  "estado": "PENDIENTE",
  "prioridad": "ALTA",
  "campos_formulario": [...],
  "cuadrilla_codigo": "CUA-001",
  "hora_inicio_estimada": "08:00:00",
  "observaciones_programacion": "Acceso por finca La Esperanza",
  "requiere_fotos_antes": true,
  "requiere_fotos_durante": false,
  "requiere_fotos_despues": true,
  "min_fotos": 3
}
```

---

#### POST /api/actividades/{actividad_id}/iniciar

Iniciar una actividad y crear registro de campo.

**Path Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `actividad_id` | uuid | ID de la actividad |

**Query Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `latitud` | decimal | Latitud GPS actual |
| `longitud` | decimal | Longitud GPS actual |

**Respuesta (200)**:
```json
{
  "registro_id": "uuid",
  "dentro_poligono": true,
  "mensaje": "Actividad iniciada correctamente"
}
```

> **Nota**: Si la ubicacion esta fuera del poligono de servidumbre, `dentro_poligono` sera `false` y el mensaje indicara una advertencia.

---

### Campo (`/api/campo/`)

#### GET /api/campo/registros

Listar registros de campo.

**Query Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `actividad_id` | uuid | Filtrar por actividad (opcional) |

**Respuesta (200)**:
```json
[
  {
    "id": "uuid",
    "actividad_id": "uuid",
    "fecha_inicio": "2025-01-15T08:30:00Z",
    "fecha_fin": "2025-01-15T11:45:00Z",
    "dentro_poligono": true,
    "sincronizado": true,
    "total_evidencias": 5
  }
]
```

---

#### GET /api/campo/registros/{registro_id}

Obtener detalle de un registro de campo.

**Respuesta (200)**:
```json
{
  "id": "uuid",
  "actividad_id": "uuid",
  "fecha_inicio": "2025-01-15T08:30:00Z",
  "fecha_fin": "2025-01-15T11:45:00Z",
  "dentro_poligono": true,
  "sincronizado": true,
  "total_evidencias": 5,
  "datos_formulario": {
    "altura_poda": 5.5,
    "tipo_vegetacion": "Arborea",
    "area_intervenida": 120
  },
  "observaciones": "Se encontro nido de aves, se reubico",
  "evidencias": [
    {
      "id": "uuid",
      "tipo": "ANTES",
      "url_original": "https://storage.googleapis.com/...",
      "url_thumbnail": "https://storage.googleapis.com/...",
      "latitud": "10.9878",
      "longitud": "-74.7889",
      "fecha_captura": "2025-01-15T08:35:00Z",
      "es_valida": true
    }
  ]
}
```

---

#### POST /api/campo/registros/sync

Sincronizar multiples registros de campo (para uso offline).

**Request Body**:
```json
{
  "registros": [
    {
      "actividad_id": "uuid",
      "datos_formulario": {...},
      "observaciones": "string",
      "latitud_fin": "decimal",
      "longitud_fin": "decimal"
    }
  ]
}
```

**Respuesta (200)**:
```json
[
  {
    "id": "uuid",
    "status": "ok",
    "message": "Sincronizado correctamente"
  },
  {
    "id": "uuid",
    "status": "error",
    "message": "Registro no encontrado"
  }
]
```

---

#### POST /api/campo/evidencias/upload

Subir evidencia fotografica.

**Content-Type**: `multipart/form-data`

**Form Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `registro_id` | uuid | ID del registro de campo |
| `tipo` | string | Tipo de evidencia (ANTES, DURANTE, DESPUES) |
| `latitud` | decimal | Latitud GPS de captura |
| `longitud` | decimal | Longitud GPS de captura |
| `fecha_captura` | datetime | Fecha y hora de captura |
| `archivo` | file | Imagen (JPEG, PNG, WebP) |

**Respuesta (200)**:
```json
{
  "id": "uuid",
  "url": "https://storage.googleapis.com/...",
  "status": "processing"
}
```

> **Nota**: El procesamiento de thumbnails y validacion IA se realiza de forma asincrona.

---

#### POST /api/campo/registros/{registro_id}/firma

Subir firma digital del responsable.

**Content-Type**: `multipart/form-data`

**Form Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `archivo` | file | Imagen PNG de la firma |

**Respuesta (200)**:
```json
{
  "url": "https://storage.googleapis.com/..."
}
```

---

### Lineas y Torres (`/api/lineas/`)

#### GET /api/lineas/lineas

Listar lineas de transmision.

**Query Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `cliente` | string | Filtrar por cliente |
| `activa` | boolean | Filtrar por estado (default: true) |

**Respuesta (200)**:
```json
[
  {
    "id": "uuid",
    "codigo": "LT-001",
    "nombre": "Linea Barranquilla - Cartagena",
    "cliente": "TRANSELCA",
    "tension_kv": 220,
    "longitud_km": "120.5",
    "activa": true
  }
]
```

---

#### GET /api/lineas/lineas/{linea_id}/torres

Listar torres de una linea.

**Respuesta (200)**:
```json
[
  {
    "id": "uuid",
    "numero": "T-001",
    "tipo": "SUSPENSION",
    "estado": "OPERATIVA",
    "latitud": "10.9878",
    "longitud": "-74.7889",
    "altitud": "150.0",
    "municipio": "Barranquilla",
    "linea_codigo": "LT-001",
    "linea_nombre": "Linea Barranquilla - Cartagena"
  }
]
```

---

#### GET /api/lineas/torres/{torre_id}

Obtener detalle de una torre.

**Respuesta (200)**:
```json
{
  "id": "uuid",
  "numero": "T-001",
  "tipo": "SUSPENSION",
  "estado": "OPERATIVA",
  "latitud": "10.9878",
  "longitud": "-74.7889",
  "altitud": "150.0",
  "municipio": "Barranquilla",
  "linea_codigo": "LT-001",
  "linea_nombre": "Linea Barranquilla - Cartagena",
  "propietario_predio": "Finca La Esperanza",
  "vereda": "Los Almendros",
  "altura_estructura": "45.5",
  "observaciones": "Acceso por camino destapado",
  "tiene_poligono": true
}
```

---

#### GET /api/lineas/torres/{torre_id}/poligono

Obtener poligono de servidumbre de una torre.

**Respuesta (200)**:
```json
{
  "id": "uuid",
  "nombre": "Servidumbre T-001",
  "area_hectareas": "0.25",
  "ancho_franja": "30.0",
  "geometria": {
    "type": "Polygon",
    "coordinates": [[[...]]]
  }
}
```

---

#### POST /api/lineas/validar-ubicacion

Validar si coordenadas GPS estan dentro del poligono de servidumbre.

**Request Body**:
```json
{
  "latitud": "10.9878",
  "longitud": "-74.7889",
  "torre_id": "uuid"
}
```

**Respuesta (200)**:
```json
{
  "dentro_poligono": true,
  "torre_numero": "T-001",
  "linea_codigo": "LT-001",
  "mensaje": "Ubicacion dentro del area de servidumbre autorizada."
}
```

---

### Cuadrillas (`/api/cuadrillas/`)

#### GET /api/cuadrillas/cuadrillas

Listar cuadrillas.

**Query Parameters**:
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `activa` | boolean | Filtrar por estado (default: true) |

**Respuesta (200)**:
```json
[
  {
    "id": "uuid",
    "codigo": "CUA-001",
    "nombre": "Cuadrilla Norte",
    "supervisor_nombre": "Pedro Lopez",
    "vehiculo_placa": "ABC123",
    "linea_codigo": "LT-001",
    "total_miembros": 5
  }
]
```

---

#### GET /api/cuadrillas/cuadrillas/{cuadrilla_id}

Obtener detalle de una cuadrilla con miembros.

**Respuesta (200)**:
```json
{
  "id": "uuid",
  "codigo": "CUA-001",
  "nombre": "Cuadrilla Norte",
  "supervisor_nombre": "Pedro Lopez",
  "vehiculo_placa": "ABC123",
  "linea_codigo": "LT-001",
  "total_miembros": 5,
  "miembros": [
    {
      "id": "uuid",
      "usuario_id": "uuid",
      "usuario_nombre": "Juan Perez",
      "rol_cuadrilla": "liniero",
      "activo": true
    }
  ]
}
```

---

#### POST /api/cuadrillas/ubicacion

Registrar ubicacion actual de la cuadrilla.

**Request Body**:
```json
{
  "latitud": "10.9878",
  "longitud": "-74.7889",
  "precision_metros": "5.0",
  "velocidad": "0.0",
  "bateria": 85
}
```

**Respuesta (200)**:
```json
{
  "status": "ok",
  "id": "uuid"
}
```

---

#### GET /api/cuadrillas/ubicaciones

Obtener ultima ubicacion de todas las cuadrillas activas.

**Respuesta (200)**:
```json
[
  {
    "cuadrilla_codigo": "CUA-001",
    "lat": 10.9878,
    "lng": -74.7889,
    "precision": 5.0,
    "timestamp": "2025-01-15T10:30:00Z"
  }
]
```

---

## Codigos de Error

| Codigo | Descripcion |
|--------|-------------|
| 400 | Bad Request - Datos invalidos en la solicitud |
| 401 | Unauthorized - Token invalido, expirado o no proporcionado |
| 403 | Forbidden - Sin permisos para el recurso |
| 404 | Not Found - Recurso no encontrado |
| 422 | Unprocessable Entity - Error de validacion |
| 429 | Too Many Requests - Rate limit excedido |
| 500 | Internal Server Error - Error del servidor |

### Formato de Errores

```json
{
  "detail": "Descripcion del error"
}
```

Para errores de validacion (422):
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Tipos de Datos

### Roles de Usuario

| Valor | Descripcion |
|-------|-------------|
| `admin` | Administrador del sistema |
| `director` | Director de proyecto |
| `coordinador` | Coordinador |
| `ing_residente` | Ingeniero residente |
| `ing_ambiental` | Ingeniero ambiental |
| `supervisor` | Supervisor de cuadrilla |
| `liniero` | Liniero |
| `auxiliar` | Auxiliar |

### Estados de Actividad

| Valor | Descripcion |
|-------|-------------|
| `PENDIENTE` | Actividad sin iniciar |
| `PROGRAMADA` | Actividad programada para ejecucion |
| `EN_CURSO` | Actividad en ejecucion |
| `COMPLETADA` | Actividad finalizada |
| `CANCELADA` | Actividad cancelada |

### Categorias de Actividad

| Valor | Descripcion |
|-------|-------------|
| `PODA` | Poda de vegetacion |
| `HERRAJES` | Cambio de herrajes |
| `INSPECCION` | Inspeccion visual |
| `LIMPIEZA` | Limpieza de componentes |
| `OTRO` | Otras actividades |

### Tipos de Torre

| Valor | Descripcion |
|-------|-------------|
| `SUSPENSION` | Torre de suspension |
| `ANCLAJE` | Torre de anclaje |
| `TERMINAL` | Torre terminal |

### Tipos de Evidencia

| Valor | Descripcion |
|-------|-------------|
| `ANTES` | Foto antes de la actividad |
| `DURANTE` | Foto durante la actividad |
| `DESPUES` | Foto despues de la actividad |

---

## Webhooks

> Proximamente

---

## SDKs y Clientes

- **App Movil Android/iOS**: Utiliza la API REST con autenticacion JWT
- **Panel Web**: Utiliza Django templates con autenticacion de sesion

---

## Changelog

### v1.0.0 (2025-01)
- Version inicial de la API
- Autenticacion JWT
- CRUD completo de actividades, registros, lineas y cuadrillas
- Upload de evidencias con procesamiento asincrono
- Validacion de ubicacion por geofencing
- Rate limiting por endpoint
