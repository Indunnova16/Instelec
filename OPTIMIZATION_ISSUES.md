# 🚀 Optimización: Caching de Datos Frecuentes

**Objetivo:** Reducir latencia 200-300ms por request mediante caching de datos que se cargan repetidamente en cada vista.

**Impacto esperado:**
- 50-70% reducción de queries a BD
- Mejora de 200-300ms en tiempo de respuesta
- Menor carga en base de datos

---

## Issues

### ISSUE #1: Cachear Líneas Activas
**Prioridad:** ALTA  
**Esfuerzo:** 2 horas  
**Ubicación:** 10 vistas cargando `Linea.objects.filter(activa=True)`

**Problema:**
```python
# Se ejecuta en CADA vista:
apps/actividades/views.py:101 - context['lineas'] = Linea.objects.filter(activa=True)
apps/actividades/views.py:290 - context['lineas'] = Linea.objects.filter(activa=True)
apps/campo/views.py:107 - context['lineas'] = Linea.objects.filter(activa=True)
... (10 veces más)
```

**Solución:**
```python
from apps.core.cache import get_lineas_activas

context['lineas'] = get_lineas_activas()
```

**Vistas a actualizar:**
- [ ] `apps/actividades/views.py` (4 ubicaciones)
- [ ] `apps/campo/views.py` (5 ubicaciones)
- [ ] `apps/financiero/views.py` (2 ubicaciones)

**Prueba:**
```bash
# Antes de caché: ~150ms
# Después de caché: ~5ms (primera vez), <1ms (subsecuentes)
```

---

### ISSUE #2: Cachear Cuadrillas Activas
**Prioridad:** ALTA  
**Esfuerzo:** 2 horas  
**Ubicación:** 8 vistas cargando `Cuadrilla.objects.filter(activa=True)`

**Problema:**
```python
apps/actividades/views.py:102 - context['cuadrillas'] = Cuadrilla.objects.filter(activa=True)
apps/campo/views.py:863 - context['cuadrillas'] = Cuadrilla.objects.filter(activa=True)
apps/financiero/views.py:650 - cuadrillas = Cuadrilla.objects.filter(...)
... (5 veces más)
```

**Solución:**
```python
from apps.core.cache import get_cuadrillas_activas

context['cuadrillas'] = get_cuadrillas_activas()
```

**Vistas a actualizar:**
- [ ] `apps/actividades/views.py` (3 ubicaciones)
- [ ] `apps/campo/views.py` (2 ubicaciones)
- [ ] `apps/financiero/views.py` (3 ubicaciones)

---

### ISSUE #3: Cachear Tipos de Actividad Activos
**Prioridad:** ALTA  
**Esfuerzo:** 2 horas  
**Ubicación:** 6 vistas cargando `TipoActividad.objects.filter(activo=True)`

**Problema:**
```python
apps/actividades/views.py:100 - context['tipos'] = TipoActividad.objects.filter(activo=True)
apps/actividades/views.py:291 - context['tipos'] = TipoActividad.objects.filter(activo=True)
apps/actividades/views.py:536 - context['tipos'] = TipoActividad.objects.filter(activo=True)
... (3 veces más)
```

**Solución:**
```python
from apps.core.cache import get_tipos_actividad_activos

context['tipos'] = get_tipos_actividad_activos()
```

**Vistas a actualizar:**
- [ ] `apps/actividades/views.py` (4 ubicaciones)
- [ ] `apps/actividades/importers.py` (2 ubicaciones)

---

### ISSUE #4: Cachear Contratos por Unidad de Negocio
**Prioridad:** MEDIA  
**Esfuerzo:** 2 horas  
**Ubicación:** 3 vistas cargando contratos sin caché

**Problema:**
```python
apps/financiero/views.py:1433 - Contrato.objects.filter(unidad_negocio=unidad_filter)
apps/contratos/views.py:36 - Contrato.objects.filter(unidad_negocio='MANTENIMIENTO')
apps/contratos/views.py:39 - Contrato.objects.filter(unidad_negocio='CONSTRUCCION')
```

**Solución:**
```python
from apps.core.cache import get_contratos_por_unidad

contratos = get_contratos_por_unidad('MANTENIMIENTO')
```

**Vistas a actualizar:**
- [ ] `apps/contratos/views.py` (1 vista)
- [ ] `apps/financiero/views.py` (1 vista)

---

### ISSUE #5: Invalidar Cache en Signals
**Prioridad:** MEDIA  
**Esfuerzo:** 3 horas  
**Dependencia:** Issues #1-4 deben estar completos

**Problema:**
Si el caché tiene TTL de 1 hora pero un usuario crea una nueva línea, los demás usuarios verán la lista desactualizada hasta que expire el caché.

**Solución:**
```python
# En apps/lineas/signals.py
from django.db.models.signals import post_save, post_delete
from apps.core.cache import invalidate_lineas_cache

@receiver(post_save, sender=Linea)
def invalidate_lineas_on_change(sender, instance, **kwargs):
    invalidate_lineas_cache()

@receiver(post_delete, sender=Linea)
def invalidate_lineas_on_delete(sender, instance, **kwargs):
    invalidate_lineas_cache()
```

**Modelos a actualizar:**
- [ ] `apps/lineas/models.py` - Agregar signals para Linea
- [ ] `apps/cuadrillas/models.py` - Agregar signals para Cuadrilla
- [ ] `apps/actividades/models.py` - Agregar signals para TipoActividad
- [ ] `apps/contratos/models.py` - Agregar signals para Contrato

---

### ISSUE #6: Agregar Cache Middleware
**Prioridad:** BAJA  
**Esfuerzo:** 1 hora  
**Dependencia:** Issues #1-4 deben estar completos

**Problema:**
Cada view sigue llamando a `get_cached_queryset()` manualmente. Podríamos usar un middleware para cachear respuestas HTML completas de vistas que no tienen parámetros dinámicos.

**Solución:**
```python
# En config/settings.py
MIDDLEWARE = [
    ...
    'django.middleware.cache.UpdateCacheMiddleware',
    ...
    'django.middleware.cache.FetchFromCacheMiddleware',
]

CACHE_MIDDLEWARE_SECONDS = 300  # 5 minutos
```

---

## Configuración de Cache

### Instalación (ya debe estar hecha)
```bash
# En requirements/base.txt
django>=4.0
# Redis viene incluido con Docker
```

### settings.py (verificar)
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'redis.Redis',
            'CONNECTION_POOL_CLASS_KWARGS': {'max_connections': 50}
        },
        'KEY_PREFIX': 'instelec',
        'TIMEOUT': 300,
    }
}
```

---

## Ejecución Recomendada

```
Semana 1:
  ✓ ISSUE #1: Cachear Líneas (2h)
  ✓ ISSUE #2: Cachear Cuadrillas (2h)
  ✓ ISSUE #3: Cachear TipoActividad (2h)
  
Semana 2:
  ✓ ISSUE #4: Cachear Contratos (2h)
  ✓ ISSUE #5: Signals de invalidación (3h)
  ✓ ISSUE #6: Cache Middleware (1h)

Total: ~12 horas = 1.5 días de desarrollo
```

---

## Verificación

```bash
# Medir antes/después
ab -n 100 -c 10 http://localhost:8000/actividades/

# Ver cache stats
python manage.py shell
from django.core.cache import cache
cache.get('instelec:lineas:activas')
```

---

## Notas

- ✅ Archivo `apps/core/cache.py` ya creado
- TTL de 1 hora es razonable para líneas/cuadrillas
- Los signals se activan automáticamente al crear/modificar
- Redis debe estar disponible en el ambiente
