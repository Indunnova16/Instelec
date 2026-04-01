# Changelog - Instelec

Todos los cambios notables en este proyecto serán documentados en este archivo.

## [Implementación 1 Abril 2026] - 2026-04-01

### ✅ Completado

#### 1. Módulo de Líneas de Transmisión 🗺️
- **Agregado**: Nuevos campos al modelo `Línea`:
  - `contrato` (ForeignKey a Contrato/Proyecto)
  - `cantidad_torres` (entero)
  - `cantidad_postes` (entero)
  - `tipo_estructura` (TORRES/POSTES/MIXTO)
- **Agregado**: Property `total_estructuras` para calcular total según tipo
- **Actualizado**: Vista `LineaEditView` para soportar nuevos campos
- **Actualizado**: Template `lineas/editar.html` con sección de Estructura
- **Actualizado**: Template `lineas/detalle.html` para mostrar información de proyecto
- **Actualizado**: Filtro por contrato en `LineaListView`
- **Migración**: `lineas/0005_linea_cantidad_postes_linea_cantidad_torres_and_more.py`

#### 2. Módulo de Actividades - Correcciones 🔧
- **Corregido**: Vista `ActividadCreateView` permite crear actividades sin `aviso_sap` para emergencias
  - Genera código automático `EMG-YYYYMMDDHHMMSS` para emergencias
  - `aviso_sap` es opcional para otros tipos de actividad
- **Agregado**: Método `recalcular_avance()` al modelo `Actividad`
  - Calcula avance automáticamente basado en vanos ejecutados y aprobados
  - Marca actividad como completada al llegar a 100%
- **Agregado**: Comando `fix_actividades_ejemplo` para identificar y corregir datos de prueba
  - Detecta avisos SAP con "TO", "ejemplo", "test"
  - Detecta actividades sin tipo o sin línea
  - Modos: `--dry-run`, `--fix`, `--eliminar`

#### 3. Módulo de Lista Operativa (Histórico) 📋
- **Agregado**: Modelo `HistorialIntervencion`
  - Registra automáticamente todas las intervenciones en líneas
  - Incluye: fecha, tipo, cuadrilla, usuario, torres inicio/fin
  - Índices optimizados para consultas por línea, cuadrilla y fecha
- **Agregado**: Signal `crear_historial_intervencion` en `campo/signals.py`
  - Se ejecuta automáticamente al sincronizar un `RegistroCampo`
  - Evita duplicados
  - Captura datos de tramo/torre según configuración de actividad
- **Agregado**: Vista `ListaOperativaView`
  - Paginación de 50 items
  - Filtros: línea, fecha desde/hasta, cuadrilla, tipo de intervención
  - Roles permitidos: admin, director, coordinador, ing_residente, supervisor
- **Migración**: `actividades/0008_historialintervencion.py`

#### 4. Módulo de Permisos de Usuarios 🔐
- **Corregido**: `UsuarioManager.create_user()` asigna `is_staff=True` automáticamente
  - Aplica para roles: admin, director, coordinador
  - Fix para botones administrativos en templates
- **Agregado**: Comando `fix_admin_staff`
  - Corrige usuarios existentes sin `is_staff`
  - Modo `--dry-run` para simular sin aplicar cambios
  - Reporta ingenieros residentes sin permisos administrativos

#### 5. Módulo de Plantilla Excel Descargable 📥
- **Agregado**: Vista `DescargarPlantillaCuadrillasView`
  - Genera archivo Excel con formato predefinido
  - Incluye headers con estilo y validaciones
  - Hoja de instrucciones detalladas
  - Fila de ejemplo con datos reales
  - Nombre de archivo con fecha: `plantilla_cuadrillas_YYYYMMDD.xlsx`
- **Agregado**: URL `/cuadrillas/masiva/plantilla/`
- **Actualizado**: Template `cuadrillas/lista.html` con botón "📥 Plantilla"
- **Roles permitidos**: admin, director, coordinador, ing_residente

#### 6. Módulo de Avances en Campo (Vanos) ✅
- **Agregado**: Modelo `AvanceVano` en `campo/models.py`
  - Estados: PENDIENTE, EJECUTADO, SIN_PERMISO, NO_EJECUTADO, EN_ESPERA
  - Trazabilidad completa: usuario, fecha marcado, supervisor, fecha revisión
  - Soporte para ayuda entre cuadrillas (`cuadrilla_asignada_original`)
  - Property `es_apoyo` para identificar vanos de otras cuadrillas
  - Métodos: `marcar_ejecutado()`, `aprobar()`, `requiere_aprobacion_supervisor()`
  - Índices optimizados para consultas frecuentes
- **Agregado**: Vista `AvancesCuadrillaView`
  - Muestra vanos asignados a la cuadrilla del usuario
  - Estadísticas: total, ejecutados, sin permiso, pendientes
  - Diferencia entre vanos propios y vanos de apoyo
  - Roles permitidos: supervisor, liniero, auxiliar
- **Agregado**: Vista `MarcarVanoView` (HTMX)
  - Actualización de estado de vanos en tiempo real
  - Modal de confirmación para evitar errores
  - Validación de permisos por cuadrilla
  - Recálculo automático de avance de actividad
- **Agregado**: Template `avances_cuadrilla.html`
  - Vista completa de avances con estadísticas
  - Información de actividad y línea
  - Separación visual de vanos propios vs apoyo
  - Responsive design para mobile y desktop
- **Agregado**: Template `partials/vano_item.html`
  - Código de colores por estado (verde=ejecutado, naranja=sin permiso, rojo=no ejecutado, amarillo=en espera, gris=pendiente)
  - Badges informativos (estado, apoyo, pendiente aprobación)
  - Botones de acción con iconos (Ejecutado, Sin Permiso, En Espera, No Ejecutado)
  - Información de trazabilidad (quién marcó, cuándo)
- **Agregado**: Template `partials/confirmar_vano.html`
  - Modal de confirmación para marcar como ejecutado
  - Campo de observaciones opcional
  - Previene errores accidentales
- **Agregado**: API endpoints para mobile en `campo/api.py`
  - `GET /api/campo/cuadrilla/avances` - Lista vanos de la cuadrilla
  - `POST /api/campo/vanos/{vano_id}/marcar` - Marca estado de vano
  - Schemas: `VanoOut`, `ActividadVanosOut`, `MarcarVanoIn`
  - Validaciones de permisos y estados
  - Rate limiting aplicado
- **Agregado**: Comando `generar_vanos`
  - Genera vanos automáticamente para actividades con tramo asignado
  - Opciones: `--actividad-id`, `--dry-run`, `--sobrescribir`
  - Valida que haya al menos 2 torres y cuadrilla asignada
  - Manejo de errores robusto
- **Agregado**: URLs en `campo/urls.py`
  - `/campo/avances/` - Vista de avances
  - `/campo/vanos/<uuid>/marcar/` - Marcar vano
- **Migración**: `campo/0008_alter_fotodano_id_avancevano.py`

#### 7. Módulo de Procedimientos 📄
- **Actualizado**: Vista `ProcedimientoListView` con búsqueda
  - Búsqueda por título, descripción, nombre de archivo, tipo
  - Ordenamiento por fecha de creación (más recientes primero)
- **Agregado**: Vista `ProcedimientoViewerView`
  - Visualización inline de archivos PDF con iframe
  - Descarga directa para otros formatos
  - Información del procedimiento: subido por, fecha, tamaño
- **Actualizado**: Template `procedimientos_lista.html`
  - Barra de búsqueda con botón "Limpiar"
  - Enlaces "Ver" y "Descargar" para cada procedimiento
  - Mejoras en UI/UX
- **Agregado**: Template `procedimiento_viewer.html`
  - Visualizador de PDF inline
  - Información detallada del archivo
  - Tips de navegación para PDFs
  - Fallback para archivos no visualizables
- **Agregado**: URL `/campo/procedimientos/<uuid>/` para viewer
- **Importación**: `Q` agregada a `campo/views.py` para búsquedas complejas

#### 8. Módulo de Vista de Daños 🔧
- **Actualizado**: Vista `ReportesDanoListView` con filtros
  - Filtro por línea
  - Filtro por severidad (BAJA, MEDIA, ALTA, CRITICA)
  - Filtro por tipo de daño
  - Ordenamiento por fecha (más recientes primero)
- **Actualizado**: Template `lista_danos.html`
  - Sección de filtros con dropdowns
  - Auto-submit al cambiar filtro
  - Botón "Limpiar filtros" cuando hay filtros activos
  - Nueva columna "Fotos" con icono y contador
  - Código de colores para severidad (rojo=crítica, naranja=alta, amarillo=media, verde=baja)
- **Mejorado**: Contexto de la vista
  - Lista de líneas activas para filtro
  - Opciones de tipos y severidades para filtros
  - Valores actuales de filtros preservados
- **Optimización**: Prefetch de `fotos` en queryset para evitar N+1 queries

#### 9. Módulo de Mapa en Vivo (Corrección) 🗺️
- **Mejorado**: Template `cuadrillas/mapa.html`
  - Múltiples llamadas a `map.invalidateSize()` con timeouts escalonados (100ms, 300ms, 500ms)
  - Listener para `visibilitychange` para refrescar al volver a la pestaña
  - Verificación de existencia del contenedor antes de inicializar
  - ResizeObserver ya existente se mantiene
- **Fix**: Renderizado correcto del mapa en diferentes escenarios
  - Al cargar la página
  - Al cambiar de pestaña
  - Al redimensionar ventana
  - Al mostrar/ocultar sidebar

#### Bug Fixes 🐛
- **Corregido**: Sintaxis en `cuadrillas/views.py` línea 1248
  - Faltaba cierre de llave `}` en `JsonResponse`
  - Agregadas líneas en blanco para separación

### 📦 Migraciones Creadas
1. `lineas/0005_linea_cantidad_postes_linea_cantidad_torres_and_more.py`
2. `campo/0008_alter_fotodano_id_avancevano.py`
3. `actividades/0008_historialintervencion.py`

### 🛠️ Comandos de Gestión Creados
1. `python manage.py fix_admin_staff` - Corrige permisos de usuarios administrativos
2. `python manage.py fix_actividades_ejemplo` - Limpia datos de ejemplo en actividades
3. `python manage.py generar_vanos` - Genera vanos para actividades con tramos

### 📋 Tareas Pendientes

#### Alta Prioridad
- [ ] **Módulo 3**: Completar templates de Lista Operativa
  - [ ] Template `actividades/lista_operativa.html`
  - [ ] Template `actividades/partials/lista_operativa.html`
  - [ ] Vista de exportación a Excel (opcional)
  - [ ] Agregar URL en `actividades/urls.py`

#### Media Prioridad
- [ ] **Módulo 10**: Actualizar Calendario (OMITIDO según instrucciones del usuario)
  - [ ] Verificar `EventosAPIView`
  - [ ] Re-importar programación mensual con datos correctos
  - [ ] Validar mapeo de torres en importador

#### Baja Prioridad
- [ ] Crear tests unitarios para nuevos modelos
- [ ] Tests de integración para signals y API
- [ ] Tests E2E para flujo de vanos
- [ ] Actualizar documentación de API
- [ ] Actualizar README con nuevas funcionalidades
- [ ] Optimizar queries con índices adicionales si es necesario

### 📝 Notas de Implementación

#### Aplicar Migraciones
```bash
source .venv/bin/activate
python manage.py migrate
```

#### Ejecutar Comandos de Corrección
```bash
# 1. Corregir permisos de usuarios (revisar primero con --dry-run)
python manage.py fix_admin_staff --dry-run
python manage.py fix_admin_staff

# 2. Corregir datos de ejemplo en actividades
python manage.py fix_actividades_ejemplo --dry-run
python manage.py fix_actividades_ejemplo --fix

# 3. Generar vanos para actividades existentes
python manage.py generar_vanos --dry-run
python manage.py generar_vanos
```

#### Flujo de Trabajo Recomendado
1. Aplicar migraciones
2. Ejecutar `fix_admin_staff`
3. Ejecutar `fix_actividades_ejemplo --fix` (revisar con --dry-run primero)
4. Generar vanos con `generar_vanos` (si ya hay actividades con tramos)
5. Probar creación de actividades sin aviso_sap
6. Verificar que el mapa se renderiza correctamente
7. Descargar plantilla de cuadrillas y probar carga masiva

### 🎯 Próximos Pasos
1. Completar implementación de módulos pendientes (6, 3, 7, 8, 10)
2. Crear tests automatizados
3. Realizar pruebas de integración
4. Capacitación a usuarios
5. Despliegue en staging
6. Piloto de producción

---

## Convenciones de Commit
- `feat:` Nueva funcionalidad
- `fix:` Corrección de bug
- `docs:` Cambios en documentación
- `refactor:` Refactorización de código
- `test:` Agregar o modificar tests
- `chore:` Tareas de mantenimiento
