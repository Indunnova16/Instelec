"""
Views for KPIs and SLA dashboard.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import HTMXMixin, RoleRequiredMixin

from .models import ActaSeguimiento, Indicador, MedicionIndicador


class DashboardView(LoginRequiredMixin, HTMXMixin, TemplateView):
    """KPI Dashboard."""
    template_name = 'indicadores/dashboard.html'
    partial_template_name = 'indicadores/partials/dashboard_content.html'

    def get_template_names(self):
        # Check if this is an HTMX request for a specific chart
        chart = self.request.GET.get('chart')
        if self.request.headers.get('HX-Request') and chart:
            return [f'indicadores/partials/chart_{chart}.html']
        return super().get_template_names()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        import json

        from django.db.models import Avg
        from django.utils import timezone

        from apps.actividades.models import Actividad
        from apps.cuadrillas.models import Cuadrilla
        from apps.lineas.models import Linea

        hoy = timezone.now()
        try:
            mes = int(self.request.GET.get('mes', hoy.month))
        except (ValueError, TypeError):
            mes = hoy.month
        try:
            anio = int(self.request.GET.get('anio', hoy.year))
        except (ValueError, TypeError):
            anio = hoy.year

        # Get all active indicators
        indicadores = Indicador.objects.filter(activo=True)
        context['indicadores'] = indicadores

        # Get measurements for current period
        mediciones = MedicionIndicador.objects.filter(
            anio=anio,
            mes=mes
        ).select_related('indicador', 'linea')

        context['mediciones'] = mediciones

        # Calculate summary
        context['promedio_cumplimiento'] = mediciones.aggregate(
            promedio=Avg('valor_calculado')
        )['promedio'] or 0

        context['en_alerta'] = mediciones.filter(en_alerta=True).count()
        context['cumplen_meta'] = mediciones.filter(cumple_meta=True).count()

        context['mes'] = mes
        context['anio'] = anio

        # Get activities for KPIs
        actividades = Actividad.objects.filter(
            fecha_programada__year=anio,
            fecha_programada__month=mes
        )
        total_actividades = actividades.count()
        completadas = actividades.filter(estado='COMPLETADA').count()

        # KPIs
        cumplimiento = (completadas / total_actividades * 100) if total_actividades > 0 else 0
        context['kpis'] = {
            'cumplimiento': cumplimiento,
            'actividades_completadas': completadas,
            'actividades_programadas': total_actividades,
            'dias_sin_accidentes': 45,  # Placeholder - should come from safety model
            'record_dias_sin_accidentes': 120,
            'informes_tiempo': 92.5,  # Placeholder
        }

        # Period filters
        context['periodos'] = [
            {'value': 'mes', 'label': 'Este mes'},
            {'value': 'semana', 'label': 'Esta semana'},
            {'value': 'trimestre', 'label': 'Este trimestre'},
        ]
        context['periodo_actual'] = self.request.GET.get('periodo', 'mes')

        # Lines for filter
        context['lineas'] = Linea.objects.filter(activa=True)

        # Cumplimiento por cuadrilla
        cuadrillas = Cuadrilla.objects.filter(activa=True)
        cuadrillas_labels = []
        cuadrillas_data = []
        for cuadrilla in cuadrillas[:10]:
            cuadrillas_labels.append(cuadrilla.codigo)
            acts = actividades.filter(cuadrilla=cuadrilla)
            total = acts.count()
            comp = acts.filter(estado='COMPLETADA').count()
            pct = (comp / total * 100) if total > 0 else 0
            cuadrillas_data.append(round(pct, 1))

        context['cuadrillas_labels'] = json.dumps(cuadrillas_labels)
        context['cuadrillas_data'] = json.dumps(cuadrillas_data)

        # Tendencia mensual (últimos 6 meses)
        meses_labels = []
        planeado_data = []
        ejecutado_data = []
        meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        for i in range(5, -1, -1):
            m = mes - i
            a = anio
            if m <= 0:
                m += 12
                a -= 1
            meses_labels.append(f"{meses_nombres[m-1]}")
            acts_mes = Actividad.objects.filter(fecha_programada__year=a, fecha_programada__month=m)
            planeado_data.append(acts_mes.count())
            ejecutado_data.append(acts_mes.filter(estado='COMPLETADA').count())

        context['meses_labels'] = json.dumps(meses_labels)
        context['planeado_data'] = json.dumps(planeado_data)
        context['ejecutado_data'] = json.dumps(ejecutado_data)

        # Por tipo de actividad
        from apps.actividades.models import TipoActividad
        tipos = TipoActividad.objects.filter(activo=True)
        tipo_data = []
        for tipo in tipos[:8]:
            count = actividades.filter(tipo_actividad=tipo).count()
            if count > 0:
                tipo_data.append({'value': count, 'name': tipo.nombre})
        context['tipo_data'] = json.dumps(tipo_data)

        # Por prioridad
        context['prioridad_data'] = {
            'urgente': actividades.filter(prioridad='URGENTE').count(),
            'alta': actividades.filter(prioridad='ALTA').count(),
            'normal': actividades.filter(prioridad='NORMAL').count(),
            'baja': actividades.filter(prioridad='BAJA').count(),
        }

        # Actividades recientes
        context['actividades_recientes'] = Actividad.objects.select_related(
            'torre'
        ).order_by('-updated_at')[:5]

        # Data for charts
        context['indicadores_data'] = [
            {
                'nombre': m.indicador.nombre,
                'valor': float(m.valor_calculado),
                'meta': float(m.indicador.meta),
            }
            for m in mediciones
        ]

        return context


class IndicadorDetailView(LoginRequiredMixin, DetailView):
    """Indicator detail with history."""
    model = Indicador
    template_name = 'indicadores/detalle.html'
    context_object_name = 'indicador'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get historical measurements
        context['historial'] = MedicionIndicador.objects.filter(
            indicador=self.object
        ).order_by('-anio', '-mes')[:12]

        return context


class ActaListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List follow-up meeting minutes."""
    model = ActaSeguimiento
    template_name = 'indicadores/actas.html'
    context_object_name = 'actas'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_queryset(self):
        return super().get_queryset().select_related('linea')


class ActaDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Meeting minutes detail."""
    model = ActaSeguimiento
    template_name = 'indicadores/acta_detalle.html'
    context_object_name = 'acta'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']
