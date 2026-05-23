# 🔗 Integración del Dashboard en Django - Instelec

## Opción Recomendada: Integración Full Django

### Paso 1: Crear Vista y Template

**`apps/core/views.py`**
```python
from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.db.models import Count, Q, F, Sum

# Importar modelos según tu estructura
# from apps.lineas.models import Linea, LineaInspeccion
# from apps.cuadrillas.models import Cuadrilla

class DashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard principal con avance por etapas"""
    template_name = 'dashboard/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calcular KPIs
        context['kpis'] = {
            'avance_general': self.calcular_avance_general(),
            'etapas_completadas': self.contar_etapas_completadas(),
            'en_riesgo': self.contar_etapas_riesgo(),
            'desviacion_dias': self.calcular_desviacion_dias(),
        }
        
        # Detalles de etapas
        context['etapas'] = self.get_etapas_con_avance()
        
        # Datos para gráficos
        context['progreso_semanal'] = self.get_progreso_semanal()
        context['comparativa_etapas'] = self.get_comparativa_etapas()
        
        return context
    
    def calcular_avance_general(self):
        """Promedio ponderado de avance de todas las etapas"""
        # Ajustar según tu modelo
        etapas = [
            {'pesos': 100, 'progreso': 95},  # Etapa 1
            {'pesos': 95, 'progreso': 78},   # Etapa 2
            {'pesos': 80, 'progreso': 45},   # Etapa 3
            {'pesos': 50, 'progreso': 22},   # Etapa 4
            {'pesos': 30, 'progreso': 0},    # Etapa 5
        ]
        total_peso = sum(e['pesos'] for e in etapas)
        total_avance = sum(e['pesos'] * e['progreso'] for e in etapas)
        return round(total_avance / total_peso, 1) if total_peso > 0 else 0
    
    def contar_etapas_completadas(self):
        """Contar etapas con avance >= 90%"""
        return 2  # Cambiar por consulta real
    
    def contar_etapas_riesgo(self):
        """Contar etapas con estado 'AT RISK' o 'OFF TRACK'"""
        return 1  # Cambiar por consulta real
    
    def calcular_desviacion_dias(self):
        """Diferencia entre fechas planeadas y reales"""
        return 3  # Cambiar por cálculo real
    
    def get_etapas_con_avance(self):
        """Obtener todas las etapas con su avance actual"""
        etapas = [
            {
                'id': 1,
                'nombre': 'Inspecciones de Campo',
                'planeado': 100,
                'ejecutado': 95,
                'avance': 95,
                'status': 'ON TRACK',
                'varianza_dias': 5,
            },
            {
                'id': 2,
                'nombre': 'Análisis y Clasificación',
                'planeado': 95,
                'ejecutado': 74,
                'avance': 78,
                'status': 'ON TRACK',
                'varianza_dias': -2,
            },
            {
                'id': 3,
                'nombre': 'Planes de Mantenimiento',
                'planeado': 80,
                'ejecutado': 36,
                'avance': 45,
                'status': 'AT RISK',
                'varianza_dias': -5,
            },
            {
                'id': 4,
                'nombre': 'Implementación de Mejoras',
                'planeado': 50,
                'ejecutado': 11,
                'avance': 22,
                'status': 'OFF TRACK',
                'varianza_dias': -10,
            },
            {
                'id': 5,
                'nombre': 'Cierre y Documentación',
                'planeado': 30,
                'ejecutado': 0,
                'avance': 0,
                'status': 'NOT STARTED',
                'varianza_dias': 0,
            },
        ]
        return etapas
    
    def get_progreso_semanal(self):
        """Progreso acumulado por semana"""
        return {
            'labels': ['Semana 1', 'Semana 2', 'Semana 3', 'Semana 4', 'Semana 5', 'Semana 6'],
            'planeado': [15, 30, 45, 60, 75, 90],
            'ejecutado': [18, 35, 48, 55, 64, 68],
        }
    
    def get_comparativa_etapas(self):
        """Comparativa planeado vs ejecutado por etapa"""
        return {
            'labels': ['Etapa 1', 'Etapa 2', 'Etapa 3', 'Etapa 4', 'Etapa 5'],
            'planeado': [100, 95, 80, 50, 30],
            'ejecutado': [95, 74, 36, 11, 0],
            'varianza': [-5, -21, -44, -39, -30],
        }


# API ENDPOINTS (para actualizaciones en vivo)
def dashboard_api_kpis(request):
    """API que devuelve KPIs en JSON"""
    view = DashboardView()
    return JsonResponse({
        'kpis': view.get_context_data()['kpis']
    })

def dashboard_api_etapas(request):
    """API que devuelve detalles de etapas"""
    view = DashboardView()
    return JsonResponse({
        'etapas': view.get_etapas_con_avance()
    })

def dashboard_api_graficos(request):
    """API que devuelve datos para gráficos"""
    view = DashboardView()
    context = view.get_context_data()
    return JsonResponse({
        'progreso_semanal': context['progreso_semanal'],
        'comparativa_etapas': context['comparativa_etapas'],
    })
```

---

### Paso 2: Crear URLs

**`apps/core/urls.py`** (o main urls.py)
```python
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    
    # APIs para actualizaciones en vivo
    path('api/dashboard/kpis/', views.dashboard_api_kpis, name='api-dashboard-kpis'),
    path('api/dashboard/etapas/', views.dashboard_api_etapas, name='api-dashboard-etapas'),
    path('api/dashboard/graficos/', views.dashboard_api_graficos, name='api-dashboard-graficos'),
]
```

---

### Paso 3: Crear Template

**`templates/dashboard/dashboard.html`**

Copiar el contenido del archivo `dashboard_propuesto.html` y reemplazar datos estáticos con variables Django:

```html
<!DOCTYPE html>
<html lang="es">
<head>
    {% load static %}
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Instelec - Avance de Proyecto</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="{% static 'css/dashboard.css' %}">
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <header>
            <h1>📊 Dashboard Instelec</h1>
            <p>Seguimiento de Avance - Mantenimiento de Líneas de Transmisión</p>
        </header>

        <!-- KPI CARDS (DINÁMICOS) -->
        <div class="kpi-grid">
            <div class="kpi-card success">
                <div class="kpi-label">Avance General</div>
                <div class="kpi-value">{{ kpis.avance_general|floatformat:0 }}%</div>
                <p style="color: #666; font-size: 0.9em;">Proyecto en marcha</p>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Etapas Completadas</div>
                <div class="kpi-value">{{ kpis.etapas_completadas }}/5</div>
                <p style="color: #666; font-size: 0.9em;">En calendario</p>
            </div>
            <div class="kpi-card warning">
                <div class="kpi-label">En Riesgo</div>
                <div class="kpi-value">{{ kpis.en_riesgo }}</div>
                <p style="color: #666; font-size: 0.9em;">Requiere atención</p>
            </div>
            <div class="kpi-card success">
                <div class="kpi-label">Desviación</div>
                <div class="kpi-value">{{ kpis.desviacion_dias|floatformat:0 }} días</div>
                <p style="color: #666; font-size: 0.9em;">Dentro de tolerancia</p>
            </div>
        </div>

        <!-- ETAPAS CON AVANCE -->
        <div class="card">
            <h2>📈 Avance por Etapa</h2>
            
            {% for etapa in etapas %}
            <div class="etapa">
                <div class="etapa-header">
                    <div class="etapa-title">Etapa {{ etapa.id }}: {{ etapa.nombre }}</div>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <span class="status-badge {% if etapa.status == 'ON TRACK' %}on-track{% elif etapa.status == 'AT RISK' %}at-risk{% else %}off-track{% endif %}">
                            {{ etapa.status }}
                        </span>
                        <span class="etapa-percentage">{{ etapa.avance|floatformat:0 }}%</span>
                    </div>
                </div>
                
                <div class="progress-container">
                    <div class="progress-bar {% if etapa.avance >= 90 %}complete{% elif etapa.avance >= 45 %}warning{% else %}danger{% endif %}" 
                         style="width: {{ etapa.avance }}%;">
                        {{ etapa.avance|floatformat:0 }}%
                    </div>
                </div>
                
                <div class="comparison">
                    <div class="comparison-item">
                        <div class="comparison-label">Planeado</div>
                        <div class="comparison-value">{{ etapa.planeado }} líneas</div>
                    </div>
                    <div class="comparison-item">
                        <div class="comparison-label">Ejecutado</div>
                        <div class="comparison-value">{{ etapa.ejecutado }} líneas</div>
                    </div>
                    <div class="comparison-item">
                        <div class="variance {% if etapa.varianza_dias > 0 %}positive{% elif etapa.varianza_dias < 0 %}negative{% else %}neutral{% endif %}">
                            {% if etapa.varianza_dias > 0 %}✓{% elif etapa.varianza_dias < 0 %}✗{% else %}—{% endif %} 
                            {{ etapa.varianza_dias }} días
                        </div>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>

        <!-- GRÁFICOS -->
        <div class="chart-wrapper">
            <div class="chart-card">
                <h2>Progreso Acumulado vs Planeado</h2>
                <div class="chart-container">
                    <canvas id="progressChart"></canvas>
                </div>
            </div>

            <div class="chart-card">
                <h2>Comparativa: Planeado vs Ejecutado</h2>
                <div class="chart-container">
                    <canvas id="comparisonChart"></canvas>
                </div>
            </div>
        </div>

        <!-- SUMMARY -->
        <div class="summary-section">
            <h2>📋 Resumen Ejecutivo</h2>
            <div class="summary-grid">
                <div class="summary-item">
                    <h3>🟢 Fortalezas</h3>
                    <p>
                        ✓ Etapa 1 completada ahead of schedule<br>
                        ✓ Equipo de campo muy productivo<br>
                        ✓ Calidad de datos excelente
                    </p>
                </div>
                <div class="summary-item">
                    <h3>🟡 Riesgos</h3>
                    <p>
                        ⚠ Etapa 3 con 5 días de retraso<br>
                        ⚠ Etapa 4 crítica (22% avance)<br>
                        ⚠ Recursos limitados para implementación
                    </p>
                </div>
                <div class="summary-item">
                    <h3>🎯 Acciones Recomendadas</h3>
                    <p>
                        → Reforzar equipo en Etapa 3<br>
                        → Iniciar Etapa 4 ya (solapamiento)<br>
                        → Revisar cronograma Etapa 5
                    </p>
                </div>
            </div>
        </div>

        <footer>
            <p>Dashboard Instelec © 2026 | Actualizado: {% now "d \d\e N \d\e Y" %} | Próxima actualización: 17 mayo 2026</p>
        </footer>
    </div>

    <script>
        // Datos desde Django
        const progressData = {{ progreso_semanal|safe }};
        const comparisonData = {{ comparativa_etapas|safe }};

        // Gráfico 1: Progreso
        const progressCtx = document.getElementById('progressChart').getContext('2d');
        new Chart(progressCtx, {
            type: 'line',
            data: {
                labels: progressData.labels,
                datasets: [
                    {
                        label: 'Planeado',
                        data: progressData.planeado,
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 6,
                    },
                    {
                        label: 'Ejecutado',
                        data: progressData.ejecutado,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 6,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, labels: { usePointStyle: true, padding: 15 } }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: { callback: function(value) { return value + '%'; } }
                    }
                }
            }
        });

        // Gráfico 2: Comparativa
        const comparisonCtx = document.getElementById('comparisonChart').getContext('2d');
        new Chart(comparisonCtx, {
            type: 'bar',
            data: {
                labels: comparisonData.labels,
                datasets: [
                    { label: 'Planeado', data: comparisonData.planeado, backgroundColor: '#667eea', borderRadius: 6 },
                    { label: 'Ejecutado', data: comparisonData.ejecutado, backgroundColor: '#10b981', borderRadius: 6 },
                    { label: 'Varianza', data: comparisonData.varianza, backgroundColor: '#ef4444', borderRadius: 6 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: true, labels: { usePointStyle: true, padding: 15 } } },
            }
        });
    </script>
</body>
</html>
```

---

### Paso 4: CSS Estático

**`static/css/dashboard.css`**

Copiar el contenido del `<style>` del archivo `dashboard_propuesto.html` a un archivo CSS separado.

---

## Actualización en Tiempo Real

### Con AJAX/Fetch (Refresco cada 30 segundos)

```javascript
// En el template
<script>
    // Auto-refresh cada 30 segundos
    setInterval(() => {
        fetch('{% url "api-dashboard-kpis" %}')
            .then(r => r.json())
            .then(data => {
                document.querySelector('.kpi-value').textContent = 
                    data.kpis.avance_general.toFixed(0) + '%';
            });
    }, 30000);
</script>
```

### Con WebSocket (Real-time - Más avanzado)

Instalar Django Channels:
```bash
pip install channels
```

**`consumers.py`**
```python
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add('dashboard', self.channel_name)
        await self.accept()

    async def receive(self, text_data):
        data = json.loads(text_data)
        # Emitir actualización
        await self.channel_layer.group_send('dashboard', {
            'type': 'dashboard_update',
            'data': data
        })

    async def dashboard_update(self, event):
        await self.send(text_data=json.dumps(event['data']))
```

---

## Resumen de Archivos a Crear

```
Instelec/
├── apps/
│   └── core/
│       ├── views.py (Agregar DashboardView)
│       ├── urls.py (Agregar rutas)
│
├── templates/
│   └── dashboard/
│       └── dashboard.html (Nuevo)
│
├── static/
│   └── css/
│       └── dashboard.css (Nuevo)
│
└── Documentacion/
    ├── dashboard_propuesto.html (✅ Creado)
    ├── PROPUESTA_DASHBOARD.md (✅ Creado)
    └── INTEGRACION_DJANGO.md (Este archivo)
```

---

## Testing

```python
# tests.py
from django.test import TestCase, Client
from django.urls import reverse

class DashboardTestCase(TestCase):
    def test_dashboard_view(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('kpis', response.context)
        self.assertIn('etapas', response.context)
    
    def test_dashboard_api_kpis(self):
        response = self.client.get(reverse('api-dashboard-kpis'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('kpis', data)
```

---

**Estimación de Esfuerzo:**
- Opción 1 (HTML estático): 15 minutos ✅
- Opción 2 (Integración Django): 2-3 horas
- Opción 3 (Con WebSocket Real-time): 4-6 horas

¡Elige la que mejor se ajuste a tu timeline! 🚀
