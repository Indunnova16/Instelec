"""
Views for activity management.
"""
from typing import Any
from datetime import date, timedelta

from django.db.models import QuerySet
from django.views.generic import ListView, DetailView, TemplateView, FormView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
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

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        from apps.lineas.models import Linea
        context['lineas'] = Linea.objects.filter(activa=True)
        context['anios'] = range(date.today().year - 1, date.today().year + 2)
        context['meses'] = [
            (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
            (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
            (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')
        ]
        return context

    def post(self, request, *args, **kwargs):
        """Handle Excel file upload and import."""
        from .importers import ProgramaTranselcaImporter
        from apps.lineas.models import Linea

        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Debe seleccionar un archivo Excel')
            return redirect('actividades:importar')

        # Validar extensión
        if not archivo.name.endswith(('.xlsx', '.xls')):
            messages.error(request, 'El archivo debe ser un Excel (.xlsx o .xls)')
            return redirect('actividades:importar')

        # Obtener parámetros
        linea_id = request.POST.get('linea')
        anio = request.POST.get('anio')
        mes = request.POST.get('mes')
        actualizar_existentes = request.POST.get('actualizar_existentes') == 'on'

        if not all([linea_id, anio, mes]):
            messages.error(request, 'Debe especificar línea, año y mes')
            return redirect('actividades:importar')

        try:
            linea = Linea.objects.get(id=linea_id)
            anio = int(anio)
            mes = int(mes)
        except (Linea.DoesNotExist, ValueError) as e:
            messages.error(request, f'Error en parámetros: {e}')
            return redirect('actividades:importar')

        # Crear o obtener programación mensual
        programacion, created = ProgramacionMensual.objects.get_or_create(
            anio=anio,
            mes=mes,
            linea=linea,
            defaults={
                'archivo_origen': archivo,
            }
        )

        if not created:
            programacion.archivo_origen = archivo
            programacion.save(update_fields=['archivo_origen', 'updated_at'])

        # Importar
        importer = ProgramaTranselcaImporter()
        resultado = importer.importar(
            archivo,
            programacion,
            opciones={'actualizar_existentes': actualizar_existentes}
        )

        if resultado['exito']:
            mensaje = (
                f"Importación exitosa: {resultado['actividades_creadas']} actividades creadas, "
                f"{resultado['actividades_actualizadas']} actualizadas, "
                f"{resultado['filas_omitidas']} filas omitidas."
            )
            if resultado['advertencias']:
                mensaje += f" {len(resultado['advertencias'])} advertencias."
            messages.success(request, mensaje)

            # Guardar datos importados en la programación
            programacion.datos_importados = {
                'resultado': resultado,
                'fecha_importacion': timezone.now().isoformat(),
                'usuario': request.user.get_full_name(),
            }
            programacion.save(update_fields=['datos_importados', 'updated_at'])
        else:
            messages.error(request, f"Error en importación: {resultado.get('error', 'Error desconocido')}")

        return redirect('actividades:programacion')


class ActividadCreateView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """View for creating a new activity."""
    template_name = 'actividades/crear.html'
    partial_template_name = 'actividades/partials/form_actividad.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['tipos'] = TipoActividad.objects.filter(activo=True)
        from apps.lineas.models import Linea
        from apps.cuadrillas.models import Cuadrilla
        context['lineas'] = Linea.objects.filter(activa=True)
        context['cuadrillas'] = Cuadrilla.objects.filter(activa=True)
        return context


class ActividadEditView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """View for editing an activity."""
    model = Actividad
    template_name = 'actividades/editar.html'
    context_object_name = 'actividad'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['tipos'] = TipoActividad.objects.filter(activo=True)
        context['estados'] = Actividad.Estado.choices
        context['prioridades'] = Actividad.Prioridad.choices
        from apps.lineas.models import Linea
        from apps.cuadrillas.models import Cuadrilla
        context['lineas'] = Linea.objects.filter(activa=True)
        context['cuadrillas'] = Cuadrilla.objects.filter(activa=True)
        return context


class CambiarEstadoView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """View for changing activity status via HTMX."""
    model = Actividad
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def post(self, request, *args, **kwargs):
        actividad = self.get_object()
        nuevo_estado = request.POST.get('estado')
        if nuevo_estado in dict(Actividad.Estado.choices):
            actividad.estado = nuevo_estado
            actividad.save(update_fields=['estado', 'updated_at'])
            return JsonResponse({'success': True, 'estado': nuevo_estado})
        return JsonResponse({'success': False, 'error': 'Estado inválido'}, status=400)


class ExportarProgramacionView(LoginRequiredMixin, RoleRequiredMixin, View):
    """View for exporting weekly programming to Excel."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get(self, request, *args, **kwargs):
        """Generate and download weekly programming Excel."""
        from .exporters import ProgramacionSemanalExporter

        # Obtener parámetros de fecha
        fecha_inicio_str = request.GET.get('fecha_inicio')
        fecha_fin_str = request.GET.get('fecha_fin')
        linea_id = request.GET.get('linea')
        cuadrilla_id = request.GET.get('cuadrilla')

        # Calcular fechas (default: semana actual)
        hoy = date.today()
        if fecha_inicio_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_inicio_str)
            except ValueError:
                fecha_inicio = hoy - timedelta(days=hoy.weekday())  # Lunes de esta semana
        else:
            fecha_inicio = hoy - timedelta(days=hoy.weekday())

        if fecha_fin_str:
            try:
                fecha_fin = date.fromisoformat(fecha_fin_str)
            except ValueError:
                fecha_fin = fecha_inicio + timedelta(days=6)
        else:
            fecha_fin = fecha_inicio + timedelta(days=6)

        # Generar Excel
        exporter = ProgramacionSemanalExporter()
        excel_content = exporter.generar_excel(
            semana_inicio=fecha_inicio,
            semana_fin=fecha_fin,
            linea_id=linea_id,
            cuadrilla_id=cuadrilla_id
        )

        # Preparar respuesta
        filename = f"programacion_semanal_{fecha_inicio.strftime('%Y%m%d')}_{fecha_fin.strftime('%Y%m%d')}.xlsx"
        response = HttpResponse(
            excel_content.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response


class ExportarAvanceView(LoginRequiredMixin, RoleRequiredMixin, View):
    """View for exporting advance report to Excel."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get(self, request, *args, **kwargs):
        """Generate and download advance report Excel."""
        from .exporters import ReporteAvanceExporter

        linea_id = request.GET.get('linea')
        fecha_corte_str = request.GET.get('fecha_corte')

        if not linea_id:
            return JsonResponse({'error': 'Debe especificar una línea'}, status=400)

        fecha_corte = None
        if fecha_corte_str:
            try:
                fecha_corte = date.fromisoformat(fecha_corte_str)
            except ValueError:
                pass

        try:
            exporter = ReporteAvanceExporter()
            excel_content = exporter.generar_excel(linea_id, fecha_corte)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=404)

        # Preparar respuesta
        filename = f"reporte_avance_{date.today().strftime('%Y%m%d')}.xlsx"
        response = HttpResponse(
            excel_content.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response


class EventosAPIView(LoginRequiredMixin, View):
    """API endpoint for FullCalendar events."""

    def get(self, request, *args, **kwargs):
        """Return events in FullCalendar format."""
        from datetime import datetime

        # Parse date range from FullCalendar
        start_str = request.GET.get('start', '')
        end_str = request.GET.get('end', '')
        linea_id = request.GET.get('linea')

        # Build queryset
        qs = Actividad.objects.select_related(
            'linea', 'torre', 'tipo_actividad', 'cuadrilla'
        )

        # Filter by date range
        if start_str:
            try:
                start_date = datetime.fromisoformat(start_str.replace('Z', '+00:00')).date()
                qs = qs.filter(fecha_programada__gte=start_date)
            except ValueError:
                pass

        if end_str:
            try:
                end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00')).date()
                qs = qs.filter(fecha_programada__lte=end_date)
            except ValueError:
                pass

        # Filter by linea
        if linea_id:
            from uuid import UUID
            try:
                UUID(linea_id)
                qs = qs.filter(linea_id=linea_id)
            except ValueError:
                pass

        # Build events list for FullCalendar
        events = []
        for actividad in qs:
            # Determine color based on status and priority
            if actividad.prioridad == 'URGENTE':
                color = '#EF4444'  # red-500
            elif actividad.estado == 'COMPLETADA':
                color = '#22C55E'  # green-500
            elif actividad.estado == 'EN_CURSO':
                color = '#EAB308'  # yellow-500
            elif actividad.estado == 'CANCELADA':
                color = '#6B7280'  # gray-500
            else:
                color = '#9CA3AF'  # gray-400

            events.append({
                'id': str(actividad.id),
                'title': f"T{actividad.torre.numero} - {actividad.linea.codigo}",
                'start': actividad.fecha_programada.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'extendedProps': {
                    'tipo': actividad.tipo_actividad.nombre,
                    'cuadrilla': actividad.cuadrilla.nombre if actividad.cuadrilla else None,
                    'estado': actividad.get_estado_display(),
                    'prioridad': actividad.get_prioridad_display(),
                }
            })

        return JsonResponse(events, safe=False)


class ActividadDetalleModalView(LoginRequiredMixin, DetailView):
    """Partial view for activity detail in modal."""
    model = Actividad
    template_name = 'actividades/partials/detalle_modal.html'
    context_object_name = 'actividad'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'linea', 'torre', 'tipo_actividad', 'cuadrilla'
        )
