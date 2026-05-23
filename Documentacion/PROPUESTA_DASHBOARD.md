# 📊 Propuesta: Dashboard de Seguimiento - Instelec

## Visión General

Dashboard interactivo para visualizar el avance del proyecto de **Mantenimiento de Líneas de Transmisión** con énfasis en:
- Avance por etapa (visual e intuitivo)
- Comparativa planeado vs ejecutado
- KPIs clave del proyecto
- Identificación de riesgos en tiempo real

---

## 🎨 Características del Diseño

### 1. **Paleta de Colores**
```
Primario:     #667eea (Azul-púrpura) - Moderna y profesional
Secundario:   #764ba2 (Púrpura)      - Gradientes suaves
Éxito:        #10b981 (Verde)        - On-track, completado
Advertencia:  #f59e0b (Amarillo)    - At-risk, retraso menor
Peligro:      #ef4444 (Rojo)         - Off-track, crítico
Fondo:        Gradiente lineal       - Premium visual
```

### 2. **Secciones Principales**

#### A. **Header + KPI Cards**
Muestra métricas de alto nivel:
- ✅ Avance General: 68%
- ✅ Etapas Completadas: 2/5
- ⚠️ En Riesgo: 1 etapa
- ✅ Desviación: +3 días

#### B. **Avance por Etapa (Cards Expandible)**
Cada etapa muestra:
```
┌─────────────────────────────────┐
│ Etapa N: Descripción      [STATUS]│
├─────────────────────────────────┤
│ [████████░░░░░░░░░░░░░░░░░░] 68% │
│                                  │
│ Planeado: 100  Ejecutado: 68     │
│ Varianza: +5 días (positivo)     │
└─────────────────────────────────┘
```

**Elementos:**
- Barra de progreso coloreada (rojo/amarillo/verde)
- Badge de estado (ON TRACK / AT RISK / OFF TRACK)
- Comparativa planeado vs ejecutado
- Indicador de varianza (+ o - días)

#### C. **Gráficos Interactivos (Chart.js)**

**Gráfico 1: Progreso Acumulado**
- Línea de "Planeado" (referencia)
- Línea de "Ejecutado" (real)
- Muestra si el proyecto está adelantado o atrasado
- Por semanas (6 semanas en el ejemplo)

**Gráfico 2: Comparativa por Etapa**
- Barras agrupadas (Planeado vs Ejecutado)
- Varianza en barras rojas (diferencia)
- Fácil identificar qué etapas están atrás

#### D. **Resumen Ejecutivo**
Tres columnas:
1. 🟢 **Fortalezas** - Lo que va bien
2. 🟡 **Riesgos** - Puntos de atención
3. 🎯 **Acciones Recomendadas** - Next steps

---

## 📐 Valores de Ejemplo (Adaptables)

### Etapas Definidas
| Etapa | Descripción | Planeado | Ejecutado | Status |
|-------|------------|----------|-----------|--------|
| 1 | Inspecciones de Campo | 100 líneas | 95 líneas | ✅ ON TRACK (95%) |
| 2 | Análisis y Clasificación | 95 líneas | 74 líneas | ✅ ON TRACK (78%) |
| 3 | Planes de Mantenimiento | 80 líneas | 36 líneas | ⚠️ AT RISK (45%) |
| 4 | Implementación de Mejoras | 50 líneas | 11 líneas | 🔴 OFF TRACK (22%) |
| 5 | Cierre y Documentación | 30 líneas | 0 líneas | ⏳ NOT STARTED (0%) |

### KPIs
- **Avance General**: 68% (suma ponderada de etapas)
- **Días de Retraso**: 3 días acumulados
- **Líneas Procesadas**: 216 / 325 (66%)

---

## 🛠️ Cómo Usar el Dashboard

### 1. **Abrir en Navegador**
```bash
# Opción A: Abrir directamente
open Documentacion/dashboard_propuesto.html

# Opción B: Desde servidor local (si se integra en Django)
python manage.py runserver
# Visitar: http://localhost:8000/dashboard/
```

### 2. **Actualizar Datos Dinámicamente**
Los datos actualmente son **estáticos** (hardcoded en HTML). Para hacerlos dinámicos:

#### Opción A: API REST + JavaScript
```javascript
// Cargar datos desde API
fetch('/api/dashboard/progress/')
  .then(r => r.json())
  .then(data => {
    document.querySelector('.etapa-percentage').textContent = data.percentage + '%';
    // ... más actualizaciones
  });
```

#### Opción B: Integración Django
```python
# views.py
def dashboard_view(request):
    etapas = Etapa.objects.all()
    context = {
        'etapas': etapas,
        'avance_general': calcular_avance_general(),
    }
    return render(request, 'dashboard.html', context)
```

#### Opción C: Archivo JSON de Configuración
```json
{
  "proyecto": "Mantenimiento Líneas",
  "avance_general": 68,
  "etapas": [
    {
      "id": 1,
      "nombre": "Inspecciones de Campo",
      "planeado": 100,
      "ejecutado": 95,
      "status": "ON TRACK"
    }
  ]
}
```

---

## 🎯 Propuestas de Mejora Futuras

### Versión 2.0
- [ ] **Real-time Updates**: WebSocket para actualizaciones en vivo
- [ ] **Exportar Reportes**: PDF / Excel con gráficos
- [ ] **Predicción de Finalización**: Basada en tendencia actual
- [ ] **Heatmap de Riesgos**: Visualizar qué líneas/etapas están en riesgo
- [ ] **Timeline Interactivo**: Mostrar hitos completados
- [ ] **Comparativa Histórica**: Ver cómo ha evolucionado el avance

### Versión 3.0
- [ ] **Dashboard Móvil**: Responsive completo para tablets/móviles
- [ ] **Alertas Automáticas**: Notificaciones cuando algo se atrasa 5+ días
- [ ] **Análisis Predictivo**: Proyectar fecha de finalización con ML
- [ ] **Drill-down**: Hacer click en etapa para ver detalles granulares
- [ ] **Comparativa con Proyectos Históricos**: Benchmarking
- [ ] **Integración de Costos**: Avance vs presupuesto

---

## 📱 Responsive Design

El dashboard está diseñado para:
- ✅ Desktop (1024px+) - 2 columnas de gráficos
- ✅ Tablet (768px-1024px) - 1 columna de gráficos, grid ajustado
- ✅ Móvil (< 768px) - Stack vertical, optimizado para touch

---

## 🎨 Estilos Clave

### Paleta completa usada:
```css
--primary: #667eea;
--secondary: #764ba2;
--success: #10b981;
--warning: #f59e0b;
--danger: #ef4444;
--neutral: #f9f9f9;
--text-dark: #333;
--text-light: #666;
```

### Bordes redondeados y sombras suaves
- Border-radius: 10-12px (elegante)
- Box-shadow: 0 10px 30px rgba(0,0,0,0.2) (profundidad)
- Transiciones suaves (0.3s) en hover

### Animaciones
- Fade-in al cargar (0.6s)
- Hover effect en cards (translate -5px)
- Progresión de barras (width 0.5s ease)

---

## 🚀 Próximos Pasos

### Fase 1: Integración en Django (Semana 1)
```
1. Crear vista en apps/core/views.py
2. Crear template en templates/dashboard.html
3. Agregar URL en urls.py
4. Conectar modelos existentes (Líneas, Etapas, etc.)
```

### Fase 2: API REST (Semana 2)
```
1. Crear serializers para Etapa y Avance
2. Endpoints:
   - GET /api/dashboard/kpis/
   - GET /api/dashboard/etapas/
   - GET /api/dashboard/progreso/
3. Real-time updates con WebSocket (opcional)
```

### Fase 3: Reportería (Semana 3)
```
1. Exportar a PDF con ReportLab
2. Exportar a Excel con Pandas
3. Email automático de reportes
```

---

## 📊 Estructura de Datos Esperada

```python
# models.py
class Etapa(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField()
    orden = models.IntegerField()
    fecha_inicio_planeada = models.DateField()
    fecha_fin_planeada = models.DateField()
    
    # Métricas
    total_lineas_planeadas = models.IntegerField()
    total_lineas_ejecutadas = models.IntegerField()
    
    def porcentaje_avance(self):
        if self.total_lineas_planeadas == 0:
            return 0
        return (self.total_lineas_ejecutadas / self.total_lineas_planeadas) * 100
    
    def estado(self):
        avance = self.porcentaje_avance()
        dias_atrasado = self.calcular_atraso()
        
        if avance >= 90:
            return 'ON TRACK'
        elif avance >= 70 or dias_atrasado <= 3:
            return 'AT RISK'
        else:
            return 'OFF TRACK'
```

---

## 💡 Tips de Personalización

### Cambiar colores:
```html
<!-- En <style> -->
--primary: #667eea;  → tu_color_favorito
```

### Cambiar datos:
```html
<!-- Buscar en HTML y reemplazar valores -->
<div class="kpi-value">68%</div>  → Tu porcentaje
```

### Agregar más etapas:
```html
<!-- Copiar y pegar bloque .etapa, cambiar valores -->
<div class="etapa">
    <div class="etapa-header">
        <div class="etapa-title">Etapa N: Descripción</div>
        <!-- ... -->
    </div>
</div>
```

---

## 📝 Notas

- Dashboard es **100% responsive** (funciona en móvil)
- Usa **Chart.js** (gratuito, sin dependencias externas)
- Código **limpio y comentado** para fácil mantenimiento
- Colores optimizados para **accesibilidad** (WCAG AA)
- Datos de ejemplo son **realistas** pero **adaptables**

---

**Creado:** 2026-05-15  
**Versión:** 1.0 - Propuesta Inicial  
**Próxima Revisión:** 2026-05-20
