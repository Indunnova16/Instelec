"""
Views for environmental management.
"""
from django.views.generic import ListView, DetailView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import InformeAmbiental, PermisoServidumbre


class InformeListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List environmental reports."""
    model = InformeAmbiental
    template_name = 'ambiental/lista.html'
    context_object_name = 'informes'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_ambiental']

    def get_queryset(self):
        return super().get_queryset().select_related('linea', 'elaborado_por')


class InformeDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Detail view for an environmental report."""
    model = InformeAmbiental
    template_name = 'ambiental/detalle.html'
    context_object_name = 'informe'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_ambiental']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get activities included in this report
        from apps.actividades.models import Actividad
        context['actividades'] = Actividad.objects.filter(
            linea=self.object.linea,
            fecha_programada__year=self.object.periodo_anio,
            fecha_programada__month=self.object.periodo_mes,
            estado='COMPLETADA'
        ).select_related('torre', 'tipo_actividad')
        return context


class GenerarInformeView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Generate PDF/Excel report."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_ambiental']

    def post(self, request, pk):
        from .tasks import generar_informe_ambiental

        informe = InformeAmbiental.objects.get(pk=pk)

        # Trigger async generation
        generar_informe_ambiental.delay(str(informe.id))

        return JsonResponse({
            'status': 'processing',
            'message': 'El informe se está generando. Recibirá una notificación cuando esté listo.'
        })


class PermisoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List easement permissions."""
    model = PermisoServidumbre
    template_name = 'ambiental/permisos.html'
    context_object_name = 'permisos'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_ambiental']

    def get_queryset(self):
        return super().get_queryset().select_related('torre__linea')


class ConsolidadoView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Consolidated view of field data for report generation."""
    template_name = 'ambiental/consolidado.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_ambiental']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from apps.campo.models import RegistroCampo
        from django.db.models import Count

        mes_param = self.request.GET.get('mes')
        anio_param = self.request.GET.get('anio')
        linea = self.request.GET.get('linea')

        registros = RegistroCampo.objects.filter(sincronizado=True)

        if mes_param and anio_param:
            try:
                mes = int(mes_param)
                anio = int(anio_param)
                registros = registros.filter(
                    fecha_inicio__year=anio,
                    fecha_inicio__month=mes
                )
            except (ValueError, TypeError):
                pass  # Invalid month/year, ignore filter

        if linea:
            from uuid import UUID
            try:
                UUID(linea)
                registros = registros.filter(actividad__linea_id=linea)
            except ValueError:
                pass  # Invalid UUID, ignore filter

        context['registros'] = registros.select_related(
            'actividad__linea',
            'actividad__torre',
            'actividad__tipo_actividad',
            'usuario'
        ).prefetch_related('evidencias')

        # Summary stats
        context['stats'] = registros.aggregate(
            total=Count('id'),
        )

        return context
