# Plan de Trabajo - Mantenimiento de Líneas
**Documento Extraído de:** Transcripciones de Seguimiento Aplicativo Instelec (1-4)  
**Fecha:** 2026-05-13  
**Estado:** Plan detallado para implementación en 4 issues principales

---

## 📋 Resumen Ejecutivo

Este plan consolida todo lo pendiente sobre **MANTENIMIENTO DE LÍNEAS**. Se asume que los datos base (líneas, torres) YA EXISTEN en BD o se cargarán manualmente. El enfoque es en las FUNCIONALIDADES que el sistema debe tener para que los usuarios de campo registren y monitoreen el mantenimiento.

---

## 🎯 Objetivos Principales

1. Permitir que usuarios registren mantenimiento de líneas desde campo (móvil)
2. Crear un histórico completo (hoja de vida) de cada línea
3. Visualizar estado actual en mapa en tiempo real
4. Separar contexto mantenimiento vs construcción
5. Generar reportes y estadísticas de mantenimiento

---

## 🔧 Issues (4 Principales)

---

### **ISSUE #1: Registros de Campo y Hoja de Vida**
**Prioridad:** ALTA | **Estimado:** 22 horas  

Este es el CORAZÓN del módulo de mantenimiento. Permite que Alcides y su equipo registren qué sucede en campo y se mantenga un histórico completo.

---

#### **SECCIÓN A: Modelo de Datos para Registros de Mantenimiento**

**¿Qué es?** 
Cuando Alcides va a revisar una línea en el campo, necesita un formulario (idealmente móvil) donde pueda registrar:
- Qué línea está revisando
- Qué tipo de revisión hace (visual, eléctrica, estructural, etc.)
- Qué hallazgos/problemas encuentra
- Qué se recomienda
- Fotos/evidencia
- Cuándo debería revisarse de nuevo

**Modelo de Base de Datos:**
```
MaintenanceRecord
├── id (PK)
├── line (FK → Line)
├── tower (FK → Tower, opcional - si es revisión puntual)
├── inspection_date (DateTime)
├── inspection_type (CharField: choices=['visual', 'electrical', 'structural', 'full'])
├── inspector_name (CharField)
├── inspector_crew (FK → Cuadrilla)
├── findings (TextField - descripción de qué encontró)
├── severity (CharField: choices=['ok', 'minor', 'major', 'critical'])
├── recommendations (TextField - qué se debe hacer)
├── photos (JSONField o ManyToMany → Photo)
├── next_inspection_date (DateField - cuándo revisar de nuevo)
├── status (CharField: choices=['pending', 'in_progress', 'completed', 'escalated'])
├── created_at (DateTime)
├── updated_at (DateTime)
├── created_by (FK → User)
```

**Lógica:**
- Cada registro representa UNA revisión en una fecha específica
- Se agrega a un histórico (ver SECCIÓN B)
- El `status` permite seguimiento: si es crítico → escalado
- Las fotos se almacenan (CloudStorage o local con carpeta datada)
- `next_inspection_date` ayuda a planificar revisiones futuras

---

#### **SECCIÓN B: Timeline / Hoja de Vida de Líneas**

**¿Qué es?**
Una vista que muestra la "vida completa" de una línea. Al entrar a una línea, ves:

**Estructura Visual:**
```
LÍNEA 5114 - 110kV - Trans
├─ Información Base
│  ├─ Código: 5114
│  ├─ Voltaje: 110kV
│  ├─ Cliente: Trans
│  ├─ Ubicación: Bogotá → Cali
│  ├─ Cantidad de postes: 450
│  └─ Última revisión: 15 mayo 2026
│
├─ TIMELINE (cronológica, más reciente primero)
│  │
│  ├─ 15 may 2026 - Revisión Visual por Alcides
│  │  ├─ Severidad: MENOR
│  │  ├─ Hallazgos: "Aisladores sucios en torres 45-50"
│  │  ├─ Recomendación: "Limpiar aisladores próxima semana"
│  │  ├─ Próxima revisión: 29 mayo 2026
│  │  ├─ Fotos: [4 imágenes]
│  │  └─ Estado: COMPLETADO
│  │
│  ├─ 10 may 2026 - Revisión Eléctrica por García
│  │  ├─ Severidad: OK
│  │  ├─ Hallazgos: "Tensión normal en todos los puntos"
│  │  └─ ...
│  │
│  ├─ 25 abr 2026 - Avisos Generadas
│  │  ├─ Tipo: "Mantenimiento programado"
│  │  └─ ...
│  │
│  └─ [más eventos anteriores...]
│
├─ ESTADÍSTICAS (a la derecha o abajo)
│  ├─ Total revisiones (mes): 3
│  ├─ Revisiones vencidas (> 30 días): 0
│  ├─ Problemas reportados: 2 (1 menor, 1 ok)
│  ├─ Fotos documentadas: 12
│  └─ Próxima revisión programada: 29 mayo 2026
│
└─ BOTÓN: "Registrar Nueva Revisión"
```

**Modelo para Timeline:**
```
LineHistoryEvent (se crea automáticamente para cada acción)
├── id (PK)
├── line (FK → Line)
├── event_type (CharField: choices=['maintenance_record', 'notice_created', 'status_change', 'manual_note'])
├── event_date (DateTime)
├── related_maintenance (FK → MaintenanceRecord, nullable)
├── related_notice (FK → Notice, nullable)
├── description (TextField)
├── created_by (FK → User)
└── metadata (JSONField - datos adicionales según tipo)
```

**¿Cómo se genera?**
1. Cuando Alcides CREA un MaintenanceRecord → automáticamente se crea un LineHistoryEvent
2. Cuando se CAMBIA el status de un registro → nuevo evento
3. Cuando se genera una AVISO → nuevo evento
4. Los usuarios pueden agregar NOTAS manuales → nuevo evento

---

#### **SECCIÓN C: Formulario de Registro (Móvil-First)**

**Pantalla 1: Seleccionar Línea**
```
┌─────────────────────────────────┐
│ Nueva Revisión de Línea          │
├─────────────────────────────────┤
│ Línea: [Buscar/Dropdown]         │
│   └─ 5114 (110kV, Trans)         │
│   └─ 5115 (110kV, Intercol)      │
│   └─ 2200 (220kV, Trans)         │
│                                  │
│ Última revisión: 15 may 2026     │
│ Días desde última: 0             │
│ Próxima programada: 29 may 2026  │
│                                  │
│ [CONTINUAR]                      │
└─────────────────────────────────┘
```

**Pantalla 2: Detalles de Revisión**
```
┌─────────────────────────────────┐
│ Línea 5114 - Revisión             │
├─────────────────────────────────┤
│ Fecha: [Hoy]                    │
│ Tipo: [Seleccionar]              │
│   └─ Visual                       │
│   └─ Eléctrica                    │
│   └─ Estructural                  │
│   └─ Completa                     │
│                                  │
│ Inspector: [Autocomplete]         │
│   └─ Alcides Giovannetti          │
│                                  │
│ Cuadrilla: [Seleccionar]          │
│   └─ Cuadrilla 3 (Bogotá)         │
│                                  │
│ [CONTINUAR]                      │
└─────────────────────────────────┘
```

**Pantalla 3: Hallazgos y Observaciones**
```
┌─────────────────────────────────┐
│ Hallazgos - Línea 5114           │
├─────────────────────────────────┤
│ ¿Encontró problemas?             │
│ ○ Sí  ○ No                       │
│                                  │
│ Severidad (si encontró):         │
│ ○ Menor  ○ Mayor  ○ Crítico      │
│                                  │
│ Descripción:                     │
│ ┌──────────────────────────────┐ │
│ │ Ej: "Aisladores sucios en    │ │
│ │ torres 45-50. Considerar     │ │
│ │ limpieza..."                 │ │
│ └──────────────────────────────┘ │
│                                  │
│ Recomendaciones:                 │
│ ┌──────────────────────────────┐ │
│ │ Ej: "Limpiar aisladores      │ │
│ │ próxima semana"              │ │
│ └──────────────────────────────┘ │
│                                  │
│ [CONTINUAR]                      │
└─────────────────────────────────┘
```

**Pantalla 4: Fotos y Próxima Revisión**
```
┌─────────────────────────────────┐
│ Fotos y Seguimiento              │
├─────────────────────────────────┤
│ Fotos:                           │
│ [📷 Tomar foto] [📷 Tomar foto]  │
│ [📷 Foto 1] [x] [📷 Foto 2] [x]  │
│                                  │
│ Próxima revisión programada:     │
│ Fecha: [Picker] → 29 may 2026    │
│                                  │
│ Notas adicionales:               │
│ ┌──────────────────────────────┐ │
│ │ (opcional)                   │ │
│ └──────────────────────────────┘ │
│                                  │
│ [CANCELAR]  [GUARDAR Y FINALIZAR]│
└─────────────────────────────────┘
```

**API Endpoint:**
```
POST /api/maintenance/records/
{
  "line_id": 5114,
  "tower_id": null,
  "inspection_date": "2026-05-15",
  "inspection_type": "visual",
  "inspector_name": "Alcides Giovannetti",
  "crew_id": 3,
  "findings": "Aisladores sucios en torres 45-50",
  "severity": "minor",
  "recommendations": "Limpiar aisladores próxima semana",
  "photo_ids": [123, 124, 125],
  "next_inspection_date": "2026-05-29"
}

RESPONSE 201:
{
  "id": 456,
  "line": {...},
  "status": "completed",
  "created_at": "2026-05-15T14:30:00Z",
  "history_entry_created": true
}
```

---

#### **SECCIÓN D: Vistas del Sistema**

**Vista 1: Detalle de Línea (GET /lines/{line_id}/)**
```
┌──────────────────────────────────────────────┐
│ Línea 5114 - 110kV - Trans                   │
├──────────────────────────────────────────────┤
│                                              │
│ INFORMACIÓN BASE (Card)                      │
│ • Código: 5114                               │
│ • Voltaje: 110 kV                            │
│ • Cliente: Trans                             │
│ • Ubicación: Bogotá → Cali                   │
│ • Postes: 450                                │
│ • Estado: ACTIVO                             │
│ • Última revisión: 15 may (0 días atrás)     │
│ • Próxima: 29 may (14 días)                  │
│                                              │
├──────────────────────────────────────────────┤
│ TIMELINE (Main Content)                      │
│ [← Filtrar por tipo de revisión]             │
│                                              │
│ ─ 15 may 2026 - Revisión Visual              │
│   Por: Alcides Giovannetti | Cuadrilla 3    │
│   Severidad: ⚠️ MENOR                        │
│   "Aisladores sucios en torres 45-50..."     │
│   Próxima: 29 may 2026                       │
│   [Ver detalles] [📸 4 fotos]                │
│                                              │
│ ─ 10 may 2026 - Revisión Eléctrica           │
│   Por: García López | Cuadrilla 2            │
│   Severidad: ✅ OK                           │
│   "Tensión normal en todos puntos..."        │
│   [Ver detalles]                             │
│                                              │
│ ─ 25 abr 2026 - Aviso Generada               │
│   Tipo: Mantenimiento Programado             │
│   [Ver aviso]                                │
│                                              │
│ [Cargar más eventos...]                      │
│                                              │
├──────────────────────────────────────────────┤
│ [📝 Registrar Nueva Revisión]                │
└──────────────────────────────────────────────┘
```

**Vista 2: Lista de Revisiones (GET /maintenance/records/)**
```
┌──────────────────────────────────────────────┐
│ Revisiones de Mantenimiento                  │
├──────────────────────────────────────────────┤
│ Filtros: [Línea] [Tipo] [Severidad] [Fecha] │
│                                              │
│ Revisión ID  │ Línea    │ Tipo      │ Sever.│
│──────────────┼──────────┼───────────┼───────┤
│ 456          │ 5114     │ Visual    │ ⚠️    │
│ 455          │ 5115     │ Eléctrica │ ✅    │
│ 454          │ 5114     │ Completa  │ 🔴    │
│ 453          │ 2200     │ Visual    │ ⚠️    │
│ ...          │ ...      │ ...       │ ...   │
│                                              │
│ [Exportar a Excel] [Ver estadísticas]       │
└──────────────────────────────────────────────┘
```

---

#### **SECCIÓN E: Automatizaciones y Lógica de Negocio**

**1. Alertas Automáticas**
- Si una línea no tiene revisión en > 30 días → ALERT "Revisión vencida"
- Si severidad = CRÍTICO → automáticamente escalar y notificar supervisor
- Si próxima_revisión es HOY → notificación a cuadrilla asignada

**2. Generación de Reportes Automáticos**
- Al finalizar un MaintenanceRecord con severidad > MENOR → generar reporte PDF
- Opción de enviar por correo a supervisor/cliente

**3. Integración con Avisos**
- Si se encuentra un problema crítico → opción rápida para generar AVISO relacionada
- La aviso se vincula automáticamente al MaintenanceRecord

**4. Historial de Estados**
- MaintenanceRecord.status puede cambiar: pending → in_progress → completed
- Cada cambio genera un LineHistoryEvent

---

#### **SECCIÓN F: Casos de Uso Reales (según transcripciones)**

**Caso 1: Revisión Visual de Línea 5114**
1. Alcides abre la app en su celular
2. Selecciona "Nueva Revisión"
3. Busca "Línea 5114"
4. Selecciona "Revisión Visual"
5. Registra: "Aisladores sucios en torres 45-50"
6. Severidad: MENOR
7. Recomendación: "Limpiar aisladores próxima semana"
8. Toma 4 fotos con cámara del celular
9. Próxima revisión: 29 mayo
10. Guarda → Automáticamente:
    - Se crea MaintenanceRecord
    - Se crea LineHistoryEvent
    - Se actualiza Line.last_inspection_date
    - Se envía notificación a supervisor
    - Aparece en timeline de la línea

**Caso 2: Problema Crítico Encontrado**
1. Alcides está revisando y encuentra un problema CRÍTICO
2. Registra hallazgo con severidad = CRÍTICO
3. Al guardar, el sistema automáticamente:
    - Marca como ESCALADO
    - Envía alerta inmediata a supervisor
    - Sugiere crear AVISO de urgencia
    - Propone revisión en 48h (no 30 días)

**Caso 3: Ver Histórico de una Línea**
1. Supervisor abre línea 5114
2. Ve timeline completa: revisiones de los últimos 6 meses
3. Ve patrones: "Esta línea ha tenido 3 problemas de aisladores en 3 meses"
4. Decide: "Vamos a programar limpieza preventiva"
5. Crea nota manual en timeline: "Limpieza preventiva programada para 20 mayo"

---

#### **SECCIÓN G: Diferencia con Construcción (Context)**

En CONSTRUCCIÓN (futuro):
```
MaintenanceRecord                   ConstructionProgressRecord
├── Revisa ESTADO actual            ├── Registra AVANCE de obra
├── Hallazgos = problemas encontrados
├── Recomendación = qué reparar     ├── Hallazgo = torres construidas hoy
├── Próxima revisión = cuándo volver├── Etapa = civil, eléctrica, etc.
└── Severidad = ok/minor/major      └── % Avance = 0-100%
```

Por eso el formulario es diferente y se usa tab selector (Issue #2).

---

#### **SECCIÓN H: Implementación Técnica Resumida**

**Modelos Django:**
- `MaintenanceRecord` (formulario, datos de revisión)
- `LineHistoryEvent` (timeline automático)
- Actualizar `Line` con fields: `last_inspection_date`, `last_inspection_type`, `inspection_status`

**Vistas/APIs:**
- `POST /api/maintenance/records/` - crear revisión
- `GET /api/maintenance/records/` - listar con filtros
- `GET /api/lines/{id}/history/` - timeline de línea
- `GET /api/lines/{id}/` - detalle con timeline embebido

**Frontend:**
- Componente de formulario multi-paso (React/Vue)
- Componente de timeline reutilizable
- Componente de card de información base
- Integración de cámara (photo upload)

**Permisos:**
- Solo usuario con rol `inspector_mantenimiento` puede crear MaintenanceRecord
- Solo supervisor puede cambiar status o escalar

**Entregables:**
- ✅ Modelos de BD (migrations)
- ✅ APIs completas con documentación
- ✅ Formulario móvil funcional
- ✅ Vistas de detalle y listado
- ✅ Timeline automático con 3 tipos de eventos

---

---

### **ISSUE #2: Visualización - Mapa en Vivo y Tabs de Contexto**
**Prioridad:** ALTA | **Estimado:** 18 horas  

#### **SECCIÓN A: Pestaña Mantenimiento vs Construcción**
- En página principal, agregar TAB/SWITCH en parte superior
- Tab 1: "Mantenimiento de Líneas" (datos existentes)
- Tab 2: "Construcción de Líneas" (nuevo módulo futuro)
- Al cambiar tab: filtro global se actualiza, todos los módulos cambian (actividades, cuadrillas, registros de campo)
- Usar URL param: `?unit=maintenance` o `?unit=construction`
- Persistir en sesión/localStorage

#### **SECCIÓN B: Mapa en Vivo - Líneas y Torres (Formato KMZ específico)**

**DATOS DISPONIBLES:**
Archivo: `Torres Transelca.kmz (1).zip`
- **40 líneas de transmisión** con coordenadas GPS
- **4,586 torres** (placemarks) distribuidas en las líneas
- **Voltajes:** 34.5 kV, 110 kV, 220 kV
- **Estructura del KMZ:**
  ```
  Torres Transelca (Folder)
  ├── Document: LN588 TEBSA - TRIPLE A 1 34.5 KV
  │   └── Waypoints
  │       ├── Placemark: P001 (torre) → coords: [-74.76333, 10.93896, 100]
  │       ├── Placemark: P002 (torre) → coords: [-74.76350, 10.93976, 100]
  │       └── ... (múltiples torres)
  ├── Document: LN5114 CERROMATOSO - GECELCA 3 1 34.5 KV
  │   └── Waypoints
  │       ├── Placemark: P001 ...
  │       └── ...
  └── ... (38 documentos más)
  ```

**PROCESAMIENTO DEL KMZ:**

**Paso 1: Importador de KMZ**
- Crear management command: `python manage.py import_lines_from_kmz "ruta/Torres Transelca.kmz"`
- Descomprimir ZIP → extraer doc.kml
- Parser KML con librería `lxml` o `defusedxml` (evita XXE attacks)
- Iterar sobre cada `<Document>` (= cada línea de transmisión)
  
**Paso 2: Extraer Información de Línea**
```python
Para cada Document:
  - Nombre: "LN588 TEBSA - TRIPLE A 1 34.5 KV"
  - Extraer código: "LN588"
  - Extraer voltaje: "34.5 kV"
  - Crear o actualizar modelo Line en BD
  - Guardar metadata en JSON field
```

**Paso 3: Extraer Torres**
```python
Para cada Placemark dentro del Document:
  - Nombre: "P001", "P002", etc.
  - Description: "LN-588" (referencia a la línea)
  - Coordinates: "-74.76333333333331,10.9389694444444,100"
    → Parsear: lon, lat, elevation
  - Crear modelo Tower con:
    - tower_number = "P001"
    - line_id = referencia a Line creada arriba
    - location = Point(lon=-74.76333, lat=10.93896) [GeoDjango]
    - elevation = 100
    - created_from_kmz = True
```

**Paso 4: Crear Índice Espacial**
- Después de importar 4,586 torres, crear índice espacial en DB para queries rápidas
- PostGIS GIST index: `CREATE INDEX idx_tower_location ON tower USING GIST(location);`

**Vistas del Mapa:**

```
┌────────────────────────────────────────────────┐
│ Mapa en Vivo - Mantenimiento de Líneas         │
├────────────────────────────────────────────────┤
│ [🎮 Zoom] [📍 Pan] [👁️ Layers: Líneas/Torres] │
│                                                │
│ ┌──────────────────────────────────────────┐  │
│ │                                          │  │
│ │    🗺️ Mapa OpenStreetMap                │  │ Leyenda:
│ │    (Leaflet.js)                         │  │ 🟢 OK (verde)
│ │                                          │  │ 🟠 En mantenimiento (naranja)
│ │    Líneas dibujadas como polígonos:     │  │ 🔴 Crítico (rojo)
│ │    ▓▓▓▓ LN588 (34.5kV) - verde          │  │
│ │    ▓▓▓▓ LN5114 (34.5kV) - naranja       │  │ Voltaje:
│ │    ▓▓▓▓ LN801 (220kV) - verde           │  │ 34.5kV • 110kV • 220kV
│ │                                          │  │
│ │    Torres como puntos:                   │  │
│ │    • P001 (LN588) - clickeable           │  │
│ │    • P002 (LN588) - clickeable           │  │
│ │    • ... 4,586 torres totales            │  │
│ │                                          │  │
│ │    Click en línea → Abre detalle         │  │
│ │    Click en torre → Abre info de torre  │  │
│ │                                          │  │
│ └──────────────────────────────────────────┘  │
│                                                │
│ Filtros (abajo):                             │
│ [Todas] [34.5kV] [110kV] [220kV]            │
│ [Estado: Todas] [OK] [Mantenimiento]        │
│                                                │
└────────────────────────────────────────────────┘
```

**Endpoints Backend:**

```
1. POST /api/maintenance/import-kmz/
   Body: multipart/form-data (archivo KMZ)
   Response: {
     "status": "success",
     "lines_created": 40,
     "towers_created": 4586,
     "import_duration_seconds": 25
   }

2. GET /api/lines/{line_id}/geojson/
   Response:
   {
     "type": "FeatureCollection",
     "features": [
       {
         "type": "Feature",
         "geometry": {
           "type": "LineString",
           "coordinates": [
             [-74.763, 10.938],
             [-74.763, 10.939],
             [-74.763, 10.940],
             ... (todos los puntos en orden)
           ]
         },
         "properties": {
           "line_id": 5114,
           "line_name": "LN5114",
           "line_code": "LN5114",
           "voltage": "34.5 kV",
           "client": "Gecelca",
           "status": "active",
           "last_inspection": "2026-05-15",
           "next_inspection": "2026-05-29"
         }
       }
     ]
   }

3. GET /api/towers/?line_id={line_id}
   Response:
   {
     "count": 150,
     "results": [
       {
         "id": 123,
         "tower_number": "P001",
         "line_id": 5114,
         "coordinates": {
           "lat": 10.938969,
           "lon": -74.763333
         },
         "elevation": 100,
         "status": "ok"
       },
       ...
     ]
   }

4. GET /api/lines/{line_id}/towers/
   (Similar al anterior, limitado a una línea)
```

**Frontend - Mapa Interactivo:**

```javascript
// Pseudocódigo
const map = L.map('map').setView([4.5, -74.2], 7);

// Cargar todas las líneas
fetch('/api/lines/?format=geojson')
  .then(res => res.json())
  .then(geojson => {
    // Dibujar líneas con color según status
    geojson.features.forEach(line => {
      const color = getColorByStatus(line.properties.status);
      L.geoJSON(line, {
        style: {
          color: color,
          weight: 2,
          opacity: 0.8
        },
        onEachFeature: (feature, layer) => {
          layer.bindPopup(`
            <strong>${feature.properties.line_name}</strong><br/>
            ${feature.properties.voltage}<br/>
            Estado: ${feature.properties.status}
          `);
          layer.on('click', () => {
            window.location = `/lines/${feature.properties.line_id}/`;
          });
        }
      }).addTo(map);
    });
  });

// Cargar torres como markers
fetch('/api/towers/')
  .then(res => res.json())
  .then(data => {
    data.results.forEach(tower => {
      L.circleMarker(
        [tower.coordinates.lat, tower.coordinates.lon],
        {
          radius: 3,
          fillColor: getColorByStatus(tower.status),
          color: '#000',
          weight: 1,
          opacity: 0.7,
          fillOpacity: 0.8
        }
      ).bindPopup(`
        Torre: ${tower.tower_number}<br/>
        Línea: LN${tower.line_id}
      `).addTo(map);
    });
  });
```

**Optimizaciones Necesarias:**
1. **Clustering de torres:** Con 4,586 puntos, usar `Leaflet.MarkerCluster` para no colapsar navegador
2. **Lazy loading:** Cargar torres solo en viewport visible (no todas a la vez)
3. **Caché:** Cachear respuesta GeoJSON con Expires header o Redis
4. **Compresión:** Usar gzip en respuestas
5. **Índice espacial:** Consultas geo rápidas con PostGIS

**Entregable:** 
- ✅ Management command de importación KMZ
- ✅ Parseo correcto de 40 líneas + 4,586 torres
- ✅ Mapa interactivo con Leaflet + OpenStreetMap
- ✅ Clustering y optimizaciones de performance
- ✅ Endpoints GeoJSON para líneas y torres
- ✅ Popup/detalle clickeable en líneas y torres
- ✅ Filtros por voltaje y estado

---

### **ISSUE #3: Filtros Globales - Sistema de Contexto Mantenimiento/Construcción**
**Prioridad:** ALTA | **Estimado:** 8 horas  

- Implementar filtro global en navbar que afecte TODOS los módulos
- Switch: "Mostrar: Mantenimiento de Líneas / Construcción de Líneas"
- URLs cambian automáticamente
- La selección persiste en sesión
- Todos los QuerySets se filtran por `business_unit` automáticamente

**Entregable:** Componente selector global, filtrado en todos los QuerySets

---

### **ISSUE #4: Reportes y Documentación**
**Prioridad:** MEDIA | **Estimado:** 12 horas  

#### **SECCIÓN A: Reportes y Estadísticas**
- Dashboard con:
  - Total de líneas en sistema
  - Líneas "vencidas" (última revisión > X días)
  - Avisos pendientes por resolver
  - Evolución de incidentes (gráfico temporal)
  - Cuadrillas activas en mantenimiento

#### **SECCIÓN B: Documentación y Capacitación**
- Wiki clara sobre:
  - Cómo registrar revisión desde móvil
  - Cómo interpretar timeline
  - Cómo leer severidades y alertas
  - Troubleshooting común
- Incluir capturas de pantalla, ejemplos

**Entregable:** Dashboard con gráficas, documento de capacitación

---

## 📈 Orden de Implementación

| Fase | Issues | Duración | Descripción |
|------|--------|----------|-------------|
| **1** | Issue #1 | ~1 semana | Registros de campo, hoja de vida, timeline |
| **2** | Issue #2 (Sección A) | ~3-4 días | Tabs mantenimiento/construcción |
| **3** | Issue #2 (Sección B) | ~4-5 días | Mapa en vivo |
| **4** | Issue #3 | ~3-4 días | Filtros globales |
| **5** | Issue #4 | ~1 semana | Reportes, documentación |

**Total Estimado:** 4-5 semanas de desarrollo

---

## 📝 Notas Críticas

- **Issue #1 es el núcleo:** Sin registros de campo, no hay nada que visualizar
- **Datos base se asumen existentes:** Líneas, torres, cuadrillas ya en BD
- **Móvil-first:** El formulario debe funcionar perfecto en celular (campo)
- **Automatizaciones:** La hoja de vida se genera sola, no manual
- **Separación clara:** Mantenimiento ≠ Construcción (contextos diferentes)

---

**Estado:** ✅ 4 issues claros, muy focalizados  
**Próximo:** Crear en GitHub Issues
