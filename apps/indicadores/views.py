"""
Views for KPIs and SLA dashboard.
"""
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import RoleRequiredMixin
from .models import Indicador, MedicionIndicador, ActaSeguimiento


class DashboardView(LoginRequiredMixin, TemplateView):
    """KPI Dashboard."""
    template_name = 'indicadores/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from django.utils import timezone
        from django.db.models import Avg

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
