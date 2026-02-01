"""
Views for KPIs and SLA dashboard.
"""
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from apps.core.mixins import RoleRequiredMixin, HTMXMixin
from .models import Indicador, MedicionIndicador, ActaSeguimiento


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

        from django.utils import timezone
        from django.db.models import Avg, Count

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

        # Data for charts
        context['indicadores_data'] = [
            {
                'nombre': m.indicador.nombre,
                'valor': float(m.valor_calculado),
                'meta': float(m.indicador.meta),
            }
            for m in mediciones
        ]

        # Chart-specific data for HTMX partial requests
        chart = self.request.GET.get('chart')
        if chart == 'actividades':
            from apps.actividades.models import Actividad
            # Get activity stats for the current month
            actividades = Actividad.objects.filter(
                fecha_programada__year=anio,
                fecha_programada__month=mes
            )
            context['actividades_stats'] = {
                'total': actividades.count(),
                'completadas': actividades.filter(estado='COMPLETADA').count(),
                'en_curso': actividades.filter(estado='EN_CURSO').count(),
                'pendientes': actividades.filter(estado='PENDIENTE').count(),
                'canceladas': actividades.filter(estado='CANCELADA').count(),
            }
            # Calculate percentage
            total = context['actividades_stats']['total']
            if total > 0:
                context['actividades_stats']['pct_completadas'] = round(
                    context['actividades_stats']['completadas'] / total * 100, 1
                )
            else:
                context['actividades_stats']['pct_completadas'] = 0

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
