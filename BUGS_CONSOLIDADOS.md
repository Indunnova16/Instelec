# 🐛 ISSUE: Consolidado de Bugs - Correcciones Necesarias (2026-05-21)

**Prioridad:** 🔴 ALTA  
**Esfuerzo:** 14 horas  
**Módulos Afectados:** Construcción, Cuadrillas, Cache, Maps  
**Responsable:** Ana Sofía Munera

---

## 📋 Descripción

Consolidación de 5 bugs identificados en reuniones de seguimiento del aplicativo Instelec. Incluye bugs confirmados que causan pérdida de datos, issues de sincronización, y mejoras preventivas de UX/performance.

---

## 🐛 BUGS A CORREGIR

### **BUG #1: Fechas en formulario de Contrato aparecen vacías al editar**
**Impacto:** 🔴 CRÍTICO - Pérdida de datos | **Esfuerzo:** 4h

**Problema:** Cuando se abre un contrato existente para editar, los campos `fecha_inicio` y `fecha_fin` aparecen vacíos aunque tienen valores en BD. Al guardar sin cambios, pierde las fechas.

**Solución:**
```python
# apps/construccion/forms.py - ContratoForm
class ContratoForm(forms.ModelForm):
    fecha_inicio = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        input_formats=['%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S'],
        required=True
    )
    fecha_fin = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        input_formats=['%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S'],
        required=True
    )
    
    class Meta:
        model = Contrato
        fields = ['fecha_inicio', 'fecha_fin', ...]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Formatear fechas existentes en formato ISO
        if self.instance.fecha_inicio:
            self.fields['fecha_inicio'].initial = self.instance.fecha_inicio.strftime('%Y-%m-%d')
        if self.instance.fecha_fin:
            self.fields['fecha_fin'].initial = self.instance.fecha_fin.strftime('%Y-%m-%d')
```

**Testing:**
- [ ] Crear contrato con fechas
- [ ] Editar sin cambios → fechas deben persistir
- [ ] Cambiar fechas → deben actualizar
- [ ] Probar con diferentes formatos

---

### **BUG #2: Torres editadas en Contrato no se sincronizan en Ingeniería ni Preliminares**
**Impacto:** 🔴 CRÍTICO - Inconsistencia de datos | **Esfuerzo:** 5h

**Problema:** Editar torres en tab "Contrato" (altura, coordenadas) no se refleja en tabs "Ingeniería" y "Preliminares". Requiere refrescar página para ver cambios.

**Solución:**

Paso 1 - Agregar signals:
```python
# apps/lineas/signals.py (NUEVO)
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from apps.lineas.models import Torre

@receiver(post_save, sender=Torre)
def invalidate_torre_cache_on_save(sender, instance, created, **kwargs):
    cache.delete(f'torre_{instance.id}')
    cache.delete(f'linea_{instance.linea.id}_torres')
    cache.delete(f'linea_{instance.linea.id}_torres_json')
```

Paso 2 - Registrar en apps.py:
```python
# apps/lineas/apps.py
class LineasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.lineas'
    def ready(self):
        import apps.lineas.signals
```

Paso 3 - Endpoint para refrescar:
```python
# apps/construccion/views.py
def refresh_torres_tabs(request, proyecto_id):
    proyecto = Proyecto.objects.get(id=proyecto_id)
    torres = proyecto.linea.torre_set.all()
    torres_data = [
        {
            'id': t.id,
            'numero': t.numero,
            'altura': t.altura,
            'latitud': float(t.ubicacion.y) if t.ubicacion else None,
            'longitud': float(t.ubicacion.x) if t.ubicacion else None,
        }
        for t in torres
    ]
    return JsonResponse({'torres': torres_data})
```

Paso 4 - JavaScript para refrescar:
```javascript
// static/js/construccion.js
fetch('/api/construccion/' + proyectoId + '/torres/refresh/')
    .then(response => response.json())
    .then(data => {
        updateTableData('#ingenieria-torres-table', data.torres);
        updateTableData('#preliminares-torres-table', data.torres);
        showNotification('Torres actualizadas', 'success');
    })
    .catch(error => console.error('Error:', error));

function updateTableData(tableSelector, nuevasTorres) {
    const tabla = document.querySelector(tableSelector);
    const tbody = tabla.querySelector('tbody');
    tbody.innerHTML = '';
    nuevasTorres.forEach(torre => {
        const row = `<tr>
            <td>${torre.numero}</td>
            <td>${torre.altura}m</td>
            <td>${torre.latitud?.toFixed(4)}</td>
            <td>${torre.longitud?.toFixed(4)}</td>
        </tr>`;
        tbody.insertAdjacentHTML('beforeend', row);
    });
}
```

**Testing:**
- [ ] Editar torre en Contrato
- [ ] Sin refrescar, cambiar a Ingeniería → datos deben actualizarse
- [ ] Sin refrescar, cambiar a Preliminares → datos deben actualizarse

---

### **BUG #3: Mapas en Vivo devolvían 403 Forbidden**
**Impacto:** 🔴 CRÍTICO - Feature no funciona | **Esfuerzo:** 0h ✅

**Problema:** Endpoints `/cuadrillas/mapa/` y `/cuadrillas/mapa/partial/` devolvían 403 Forbidden.

**Estado:** ✅ YA CORREGIDO en commit `2c1f6f5`
- RoleRequiredMixin mejorado para diferenciar autenticación vs autorización
- Usuarios no autenticados redirigen a login (302)
- Usuarios sin rol reciben 403 claro

**Verificación:**
- [x] Usuarios anónimos redirigidos a login
- [x] Usuarios admin acceden a mapa (200 OK)
- [x] JSON endpoint retorna ubicaciones

---

### **BUG #4: Cache no se invalida al crear/editar/eliminar datos**
**Impacto:** 🟡 MEDIO - Datos stale en caché | **Esfuerzo:** 3h

**Problema:** Crear/editar/eliminar Líneas, Cuadrillas o Tipos de Actividad no invalida el caché. Datos viejos persisten por 5 minutos.

**Solución:**

```python
# apps/lineas/signals.py - AGREGAR
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from apps.lineas.models import Linea

@receiver(post_save, sender=Linea)
def invalidate_lineas_cache_on_save(sender, instance, **kwargs):
    cache.delete('lineas_activas')
    cache.delete('lineas_all')

@receiver(post_delete, sender=Linea)
def invalidate_lineas_cache_on_delete(sender, instance, **kwargs):
    cache.delete('lineas_activas')
    cache.delete('lineas_all')

# apps/cuadrillas/signals.py (NUEVO)
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from apps.cuadrillas.models import Cuadrilla

@receiver(post_save, sender=Cuadrilla)
def invalidate_cuadrillas_cache_on_save(sender, instance, **kwargs):
    cache.delete('cuadrillas_activas')

@receiver(post_delete, sender=Cuadrilla)
def invalidate_cuadrillas_cache_on_delete(sender, instance, **kwargs):
    cache.delete('cuadrillas_activas')

# apps/actividades/signals.py (NUEVO)
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from apps.actividades.models import TipoActividad

@receiver(post_save, sender=TipoActividad)
def invalidate_tipos_cache_on_save(sender, instance, **kwargs):
    cache.delete('tipos_actividad_activos')

@receiver(post_delete, sender=TipoActividad)
def invalidate_tipos_cache_on_delete(sender, instance, **kwargs):
    cache.delete('tipos_actividad_activos')
```

Registrar en cada `apps.py`:
```python
# apps/lineas/apps.py, apps/cuadrillas/apps.py, apps/actividades/apps.py
def ready(self):
    import apps.<module>.signals
```

**Testing:**
- [ ] Crear línea nueva → debe aparecer en caché inmediatamente
- [ ] Editar línea → cambios inmediatos
- [ ] Eliminar línea → se remueve del caché
- [ ] Verificar en Django shell: `cache.get('lineas_activas')`

---

### **BUG #5: Cuadrillas sin ubicación en mapa en tiempo real sin indicación visual**
**Impacto:** 🟡 MEDIO - UX confusa | **Esfuerzo:** 2h

**Problema:** En `/cuadrillas/mapa/`, cuadrillas sin GPS no aparecen y no hay indicación de dónde están. Usuario confundido.

**Solución:**

```python
# apps/cuadrillas/views.py - MapLiveView
from django.views.generic import TemplateView

class MapLiveView(TemplateView):
    template_name = 'cuadrillas/mapa.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        todas_cuadrillas = Cuadrilla.objects.filter(activa=True)
        
        cuadrillas_con_ubicacion = []
        cuadrillas_sin_ubicacion = []
        
        for cuadrilla in todas_cuadrillas:
            if hasattr(cuadrilla, 'ubicacion_gps') and cuadrilla.ubicacion_gps:
                cuadrillas_con_ubicacion.append({
                    'id': cuadrilla.id,
                    'nombre': cuadrilla.nombre,
                    'lat': float(cuadrilla.ubicacion_gps.y),
                    'lng': float(cuadrilla.ubicacion_gps.x),
                    'supervisor': str(cuadrilla.supervisor),
                })
            else:
                cuadrillas_sin_ubicacion.append({
                    'id': cuadrilla.id,
                    'nombre': cuadrilla.nombre,
                    'supervisor': str(cuadrilla.supervisor),
                })
        
        context['cuadrillas_con_ubicacion'] = cuadrillas_con_ubicacion
        context['cuadrillas_sin_ubicacion'] = cuadrillas_sin_ubicacion
        context['total_con_ubicacion'] = len(cuadrillas_con_ubicacion)
        context['total_sin_ubicacion'] = len(cuadrillas_sin_ubicacion)
        return context
```

```html
<!-- templates/cuadrillas/mapa.html -->
<div class="alert alert-success">
    ✅ {{ total_con_ubicacion }} cuadrilla(s) en línea
</div>

{% if total_sin_ubicacion > 0 %}
<div class="alert alert-warning">
    ⚠️ {{ total_sin_ubicacion }} cuadrilla(s) sin datos de GPS
    <button class="btn btn-sm btn-outline-warning" data-toggle="collapse" data-target="#cuadrillas-sin-ubicacion">
        Ver detalles
    </button>
</div>

<div id="cuadrillas-sin-ubicacion" class="collapse mt-3">
    <div class="card">
        <div class="card-header">Cuadrillas sin Datos de GPS</div>
        <div class="card-body">
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th>Cuadrilla</th>
                        <th>Supervisor</th>
                        <th>Acción</th>
                    </tr>
                </thead>
                <tbody>
                    {% for cuadrilla in cuadrillas_sin_ubicacion %}
                    <tr>
                        <td>{{ cuadrilla.nombre }}</td>
                        <td>{{ cuadrilla.supervisor }}</td>
                        <td>
                            <a href="{% url 'cuadrilla-detail' cuadrilla.id %}" class="btn btn-xs btn-info">Ver</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endif %}

<div id="map" style="height: 600px; margin-top: 20px;"></div>
```

**Testing:**
- [ ] Cuadrilla con GPS aparece en mapa
- [ ] Cuadrilla sin GPS muestra en tabla de "sin ubicación"
- [ ] Contador es correcto (con + sin = total)

---

## ✅ CHECKLIST COMPLETO

- [ ] BUG #1: Actualizar ContratoForm con formateo de fechas
- [ ] BUG #1: Probar persistencia de fechas al editar
- [ ] BUG #2: Crear signals en apps/lineas/signals.py
- [ ] BUG #2: Registrar signals en apps/lineas/apps.py
- [ ] BUG #2: Crear endpoint refresh_torres_tabs
- [ ] BUG #2: Agregar JavaScript para refrescar tabs
- [ ] BUG #2: Probar sincronización de torres en tiempo real
- [ ] BUG #3: Verificar que mapas funcionan (ya corregido)
- [ ] BUG #4: Crear signals para Linea, Cuadrilla, TipoActividad
- [ ] BUG #4: Registrar signals en apps.py de cada módulo
- [ ] BUG #4: Probar que cache se invalida correctamente
- [ ] BUG #5: Mejorar MapLiveView para separar con/sin ubicación
- [ ] BUG #5: Agregar tabla de cuadrillas sin GPS en template
- [ ] BUG #5: Probar con cuadrillas sin ubicación

---

## 🚀 ORDEN DE IMPLEMENTACIÓN

1. **BUG #1** (4h) - Fechas Contrato
2. **BUG #2** (5h) - Torres sincronización
3. **BUG #5** (2h) - Cuadrillas sin ubicación
4. **BUG #4** (3h) - Cache signals

**Total:** 14 horas

---

## 📌 NOTAS

- BUG #3 ya está corregido ✅
- BUG #1 y #2 causan pérdida/inconsistencia de datos (CRÍTICOS)
- BUG #4 y #5 son mejoras de UX/performance
- Todos requieren testing exhaustivo
- Verificar que signals estén bien conectados en `apps.py`
