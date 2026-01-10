"""
Views for activity management.
"""
from typing import Any

from django.db.models import QuerySet
from django.views.generic import ListView, DetailView, TemplateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import Actividad, ProgramacionMensual, TipoActividad


class ActividadListView(LoginRequiredMixin, HTMXMixin, ListView):
    """List activities with filters."""
    model = Actividad
    template_name = 'actividades/lista.html'
    partial_template_name = 'actividades/partials/lista_actividades.html'
    context_object_name = 'actividades'
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Actividad]:
        qs = super().get_queryset().select_related(
            'linea', 'torre', 'tipo_actividad', 'cuadrilla'
        ).prefetch_related('registros_campo')

        # Filters
        estado = self.request.GET.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        linea = self.request.GET.get('linea')
        if linea:
            from uuid import UUID
            try:
                UUID(linea)
                qs = qs.filter(linea_id=linea)
            except ValueError:
                pass  # Invalid UUID, ignore filter

        cuadrilla = self.request.GET.get('cuadrilla')
        if cuadrilla:
            from uuid import UUID
            try:
                UUID(cuadrilla)
                qs = qs.filter(cuadrilla_id=cuadrilla)
            except ValueError:
                pass  # Invalid UUID, ignore filter

        fecha_desde = self.request.GET.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha_programada__gte=fecha_desde)

        fecha_hasta = self.request.GET.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha_programada__lte=fecha_hasta)

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['estados'] = Actividad.Estado.choices
        context['tipos'] = TipoActividad.objects.filter(activo=True)
        return context


class ActividadDetailView(LoginRequiredMixin, HTMXMixin, DetailView):
    """Detail view for an activity."""
    model = Actividad
    template_name = 'actividades/detalle.html'
    context_object_name = 'actividad'

    def get_queryset(self) -> QuerySet[Actividad]:
        return super().get_queryset().select_related(
            'linea', 'torre', 'tipo_actividad', 'cuadrilla'
        ).prefetch_related(
            'registros_campo__usuario',
            'registros_campo__evidencias'
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        # Get field records for this activity (already prefetched)
        context['registros'] = self.object.registros_campo.all()
        return context


class ActividadDetailPartialView(ActividadDetailView):
    """Partial view for HTMX loading."""
    template_name = 'actividades/partials/detalle_actividad.html'


class CalendarioView(LoginRequiredMixin, TemplateView):
    """Calendar view for activity scheduling."""
    template_name = 'actividades/calendario.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Get current month activities
        hoy = timezone.now().date()
        try:
            mes = int(self.request.GET.get('mes', hoy.month))
        except (ValueError, TypeError):
            mes = hoy.month
        try:
            anio = int(self.request.GET.get('anio', hoy.year))
        except (ValueError, TypeError):
            anio = hoy.year

        actividades = Actividad.objects.filter(
            fecha_programada__year=anio,
            fecha_programada__month=mes
        ).select_related('linea', 'torre', 'tipo_actividad', 'cuadrilla')

        # Group by date
        from collections import defaultdict
        actividades_por_fecha = defaultdict(list)
        for act in actividades:
            actividades_por_fecha[act.fecha_programada.day].append(act)

        context['actividades_por_fecha'] = dict(actividades_por_fecha)
        context['mes'] = mes
        context['anio'] = anio

        # Generate calendar data
        import calendar
        cal = calendar.Calendar(firstweekday=0)
        context['semanas'] = cal.monthdayscalendar(anio, mes)
        context['nombre_mes'] = calendar.month_name[mes]

        return context


class ProgramacionListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List monthly programming."""
    model = ProgramacionMensual
    template_name = 'actividades/programacion.html'
    context_object_name = 'programaciones'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_queryset(self) -> QuerySet[ProgramacionMensual]:
        return super().get_queryset().select_related('linea', 'aprobado_por')


class ImportarProgramacionView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """View for importing programming from Excel."""
    template_name = 'actividades/importar.html'
    allowed_roles = ['admin', 'director', 'coordinador']
