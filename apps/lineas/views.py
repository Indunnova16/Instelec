"""
Views for transmission lines.
"""
import logging

from django.shortcuts import redirect
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
import json
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import Linea, Torre, Vano

logger = logging.getLogger(__name__)


class LineaListView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, ListView):
    """List all transmission lines."""
    model = Linea
    template_name = 'lineas/lista.html'
    partial_template_name = 'lineas/partials/lista_lineas.html'
    context_object_name = 'lineas'
    paginate_by = 20
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'ing_ambiental', 'supervisor', 'liniero']

    def get_queryset(self):
        qs = super().get_queryset().filter(activa=True)

        # Filters
        cliente = self.request.GET.get('cliente')
        if cliente:
            qs = qs.filter(cliente=cliente)

        contrato_id = self.request.GET.get('contrato')
        if contrato_id:
            qs = qs.filter(contrato_id=contrato_id)

        buscar = self.request.GET.get('buscar')
        if buscar:
            qs = qs.filter(nombre__icontains=buscar) | qs.filter(codigo__icontains=buscar)

        return qs.select_related('contrato').prefetch_related('torres')


class LineaDetailView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """Detail view for a transmission line."""
    model = Linea
    template_name = 'lineas/detalle.html'
    partial_template_name = 'lineas/partials/detalle_linea.html'
    context_object_name = 'linea'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'ing_ambiental', 'supervisor', 'liniero']

    def get_context_data(self, **kwargs):
        import json
        context = super().get_context_data(**kwargs)
        context['torres'] = self.object.torres.all()
        context['total_torres'] = self.object.torres.count()
        if self.object.kmz_geojson:
            context['kmz_geojson_json'] = json.dumps(self.object.kmz_geojson)
        return context

    def post(self, request, *args, **kwargs):
        """Handle AJAX POST requests for updating vanos."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Check if user has permission to edit
        if not self.request.user.is_authenticated or self.request.user.rol not in ['admin', 'director', 'coordinador']:
            return JsonResponse({'error': 'No autorizado'}, status=403)

        # Handle vanos update
        if request.POST.get('action') == 'actualizar_vanos':
            cantidad_vanos = request.POST.get('cantidad_vanos', '').strip()
            if cantidad_vanos.isdigit():
                self.object.cantidad_vanos = int(cantidad_vanos)
                self.object.save(update_fields=['cantidad_vanos'])
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'error': 'Cantidad inválida'}, status=400)

        return JsonResponse({'error': 'Acción no reconocida'}, status=400)


class LineaEditView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """View for editing a transmission line."""
    model = Linea
    template_name = 'lineas/editar.html'
    context_object_name = 'linea'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        from apps.contratos.models import Contrato
        context = super().get_context_data(**kwargs)
        context['clientes'] = Linea.Cliente.choices
        context['contratistas'] = Linea.Contratista.choices
        context['tipos_estructura'] = Linea.TipoEstructura.choices
        context['contratos'] = Contrato.objects.filter(estado='ACTIVO').order_by('codigo')
        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission to update a transmission line."""
        linea = self.get_object()

        codigo = request.POST.get('codigo', '').strip()
        nombre = request.POST.get('nombre', '').strip()

        if not codigo or not nombre:
            messages.error(request, 'Código y nombre son obligatorios.')
            return self.get(request, *args, **kwargs)

        # Check unique codigo (excluding current object)
        if Linea.objects.filter(codigo=codigo).exclude(pk=linea.pk).exists():
            messages.error(request, f'Ya existe otra línea con el código {codigo}.')
            return self.get(request, *args, **kwargs)

        try:
            from apps.contratos.models import Contrato

            linea.codigo = codigo
            linea.nombre = nombre
            linea.codigo_transelca = request.POST.get('codigo_transelca', '').strip()
            linea.circuito = request.POST.get('circuito', '').strip()
            cliente = request.POST.get('cliente', '').strip()
            linea.cliente = cliente if cliente in dict(Linea.Cliente.choices) else linea.cliente
            contratista = request.POST.get('contratista', '').strip()
            linea.contratista = contratista if contratista in dict(Linea.Contratista.choices) else ''
            linea.centro_emplazamiento = request.POST.get('centro_emplazamiento', '').strip()
            linea.puesto_trabajo = request.POST.get('puesto_trabajo', '').strip()
            tension_kv = request.POST.get('tension_kv') or None
            linea.tension_kv = int(tension_kv) if tension_kv else None
            longitud_km = request.POST.get('longitud_km') or None
            linea.longitud_km = float(longitud_km) if longitud_km else None
            linea.departamento = request.POST.get('departamento', '').strip()
            linea.municipios = request.POST.get('municipios', '').strip()
            linea.activa = request.POST.get('activa') == 'on'
            linea.observaciones = request.POST.get('observaciones', '').strip()

            # Nuevos campos agregados 1 abril 2026
            contrato_id = request.POST.get('contrato') or None
            if contrato_id:
                try:
                    linea.contrato = Contrato.objects.get(id=contrato_id)
                except Contrato.DoesNotExist:
                    linea.contrato = None
            else:
                linea.contrato = None

            tipo_estructura = request.POST.get('tipo_estructura', '').strip()
            linea.tipo_estructura = tipo_estructura if tipo_estructura in dict(Linea.TipoEstructura.choices) else linea.tipo_estructura

            cantidad_torres = request.POST.get('cantidad_torres') or None
            linea.cantidad_torres = int(cantidad_torres) if cantidad_torres else None

            cantidad_postes = request.POST.get('cantidad_postes') or None
            linea.cantidad_postes = int(cantidad_postes) if cantidad_postes else None

            linea.save()
            messages.success(request, f'Línea {linea.codigo} actualizada exitosamente.')
            return redirect('lineas:detalle', pk=linea.pk)
        except Exception as e:
            messages.error(request, f'Error al actualizar la línea: {str(e)}')
            return self.get(request, *args, **kwargs)


class TorresLineaView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, ListView):
    """List towers for a specific line."""
    model = Torre
    template_name = 'lineas/torres.html'
    partial_template_name = 'lineas/partials/lista_torres.html'
    context_object_name = 'torres'
    paginate_by = 50
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'ing_ambiental', 'supervisor', 'liniero']

    def get_queryset(self):
        return Torre.objects.filter(linea_id=self.kwargs['pk']).order_by('numero')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['linea'] = Linea.objects.get(pk=self.kwargs['pk'])
        return context


class TorreDetailView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """Detail view for a tower."""
    model = Torre
    template_name = 'lineas/torre_detalle.html'
    partial_template_name = 'lineas/partials/detalle_torre.html'
    context_object_name = 'torre'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'ing_ambiental', 'supervisor', 'liniero']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['poligonos'] = self.object.poligonos.all()
        # Get recent activities for this tower
        context['actividades_recientes'] = self.object.actividades.order_by('-fecha_programada')[:5]
        return context


class MapaLineasView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Map view showing all lines and towers."""
    template_name = 'lineas/mapa.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'ing_ambiental', 'supervisor']

    def get_context_data(self, **kwargs):
        import json
        context = super().get_context_data(**kwargs)

        # Check if a specific line is requested
        linea_id = self.request.GET.get('linea')

        if linea_id:
            try:
                from uuid import UUID
                UUID(linea_id)
                linea = Linea.objects.prefetch_related('torres').get(pk=linea_id)
                context['linea'] = linea
                torres = list(linea.torres.all())
                context['torres'] = torres
            except (ValueError, Linea.DoesNotExist):
                linea = None
                torres = []
        else:
            # Get all active lines with their towers
            lineas = Linea.objects.filter(activa=True).prefetch_related('torres')
            context['lineas'] = lineas
            linea = lineas.first() if lineas.exists() else None
            context['linea'] = linea
            torres = list(linea.torres.all()) if linea else []
            context['torres'] = torres

        # Prepare JSON data for the map
        torres_data = []
        lats = []
        lons = []
        for torre in torres:
            if torre.latitud and torre.longitud:
                torres_data.append({
                    'id': str(torre.id),
                    'numero': torre.numero,
                    'linea': linea.codigo if linea else '',
                    'tipo': torre.tipo,
                    'estado': torre.estado,
                    'lat': float(torre.latitud),
                    'lon': float(torre.longitud),
                    'altitud': float(torre.altitud) if torre.altitud else None,
                })
                lats.append(float(torre.latitud))
                lons.append(float(torre.longitud))

        # Convert to JSON string for JavaScript
        context['torres_json'] = json.dumps(torres_data)

        # Calculate center of map
        if lats and lons:
            context['center_lat'] = sum(lats) / len(lats)
            context['center_lon'] = sum(lons) / len(lons)
        else:
            # Default to Colombia center
            context['center_lat'] = 4.5709
            context['center_lon'] = -74.2973

        return context


class ImportarKMZView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """View for importing towers from KMZ/KML files."""
    template_name = 'lineas/importar_kmz.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lineas'] = Linea.objects.filter(activa=True)
        return context

    def post(self, request, *args, **kwargs):
        from django.contrib import messages
        from .importers import KMZImporter

        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Debe seleccionar un archivo KMZ o KML.')
            return redirect('lineas:importar_kmz')

        if not archivo.name.lower().endswith(('.kmz', '.kml')):
            messages.error(request, 'El archivo debe ser un KMZ o KML.')
            return redirect('lineas:importar_kmz')

        linea_id = request.POST.get('linea')
        if not linea_id:
            messages.error(request, 'Debe seleccionar una linea.')
            return redirect('lineas:importar_kmz')

        try:
            linea = Linea.objects.get(id=linea_id)
        except Linea.DoesNotExist:
            messages.error(request, 'Linea no encontrada.')
            return redirect('lineas:importar_kmz')

        actualizar = request.POST.get('actualizar_existentes') == 'on'

        importer = KMZImporter()
        resultado = importer.importar(
            archivo, linea,
            opciones={'actualizar_existentes': actualizar}
        )

        if resultado['exito']:
            mensaje = (
                f"Importacion exitosa: {resultado['torres_creadas']} torres creadas, "
                f"{resultado['torres_actualizadas']} actualizadas."
            )
            if resultado['advertencias']:
                mensaje += f" {len(resultado['advertencias'])} advertencias."
            messages.success(request, mensaje)

            if resultado['advertencias']:
                for adv in resultado['advertencias'][:5]:
                    messages.warning(request, adv)
        else:
            messages.error(request, resultado.get('error', 'Error desconocido'))

        return redirect('lineas:detalle', pk=linea.pk)


class LineaCreateView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """View for creating a new transmission line."""
    template_name = 'lineas/crear.html'
    partial_template_name = 'lineas/partials/form_linea.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['clientes'] = Linea.Cliente.choices
        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission to create a new transmission line."""
        from django.shortcuts import redirect
        from django.contrib import messages

        codigo = request.POST.get('codigo', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        cliente = request.POST.get('cliente', '').strip()
        tension_kv = request.POST.get('voltaje') or None
        longitud_km = request.POST.get('longitud_km') or None
        observaciones = request.POST.get('descripcion', '').strip()

        # Validation
        if not codigo or not nombre:
            messages.error(request, 'Código y nombre son obligatorios.')
            return self.get(request, *args, **kwargs)

        if Linea.objects.filter(codigo=codigo).exists():
            messages.error(request, f'Ya existe una línea con el código {codigo}.')
            return self.get(request, *args, **kwargs)

        # Create the line
        try:
            linea = Linea.objects.create(
                codigo=codigo,
                nombre=nombre,
                cliente=cliente if cliente in dict(Linea.Cliente.choices) else Linea.Cliente.TRANSELCA,
                tension_kv=int(tension_kv) if tension_kv else None,
                longitud_km=float(longitud_km) if longitud_km else None,
                observaciones=observaciones,
            )
            messages.success(request, f'Línea {linea.codigo} creada exitosamente.')
            return redirect('lineas:detalle', pk=linea.pk)
        except Exception as e:
            messages.error(request, f'Error al crear la línea: {str(e)}')
            return self.get(request, *args, **kwargs)


class LineaUploadKMZView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Upload a KMZ/KML file for a specific transmission line and convert to GeoJSON."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def post(self, request, pk):
        from .importers import kmz_to_geojson

        try:
            linea = Linea.objects.get(pk=pk)
        except Linea.DoesNotExist:
            messages.error(request, 'Línea no encontrada.')
            return redirect('lineas:lista')

        archivo = request.FILES.get('archivo_kmz')
        if not archivo:
            messages.error(request, 'Debe seleccionar un archivo KMZ o KML.')
            return redirect('lineas:detalle', pk=pk)

        if not archivo.name.lower().endswith(('.kmz', '.kml')):
            messages.error(request, 'El archivo debe ser un KMZ o KML.')
            return redirect('lineas:detalle', pk=pk)

        if archivo.size > 50 * 1024 * 1024:
            messages.error(request, 'El archivo no debe superar los 50 MB.')
            return redirect('lineas:detalle', pk=pk)

        try:
            geojson_data = kmz_to_geojson(archivo)
            archivo.seek(0)  # Reset file pointer for FileField save

            if not geojson_data or not geojson_data.get('features'):
                messages.error(request, 'El archivo no contiene datos geográficos válidos.')
                return redirect('lineas:detalle', pk=pk)

            # Delete old file if replacing
            if linea.archivo_kmz:
                linea.archivo_kmz.delete(save=False)

            linea.archivo_kmz = archivo
            linea.kmz_geojson = geojson_data
            linea.save(update_fields=['archivo_kmz', 'kmz_geojson'])

            num_features = len(geojson_data['features'])
            messages.success(
                request,
                f'Archivo KMZ cargado exitosamente. Se encontraron {num_features} elementos geográficos.'
            )
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.exception('Error processing KMZ upload')
            messages.error(request, f'Error al procesar el archivo: {str(e)}')

        return redirect('lineas:detalle', pk=pk)


class LineaDeleteKMZView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Delete the KMZ file and GeoJSON data from a transmission line."""
    allowed_roles = ['admin', 'director', 'coordinador']

    def post(self, request, pk):
        try:
            linea = Linea.objects.get(pk=pk)
        except Linea.DoesNotExist:
            messages.error(request, 'Línea no encontrada.')
            return redirect('lineas:lista')

        if linea.archivo_kmz:
            linea.archivo_kmz.delete(save=False)

        linea.kmz_geojson = None
        linea.save(update_fields=['archivo_kmz', 'kmz_geojson'])

        messages.success(request, 'Archivo KMZ eliminado exitosamente.')
        return redirect('lineas:detalle', pk=pk)


class AvanceCampoView(LoginRequiredMixin, View):
    """Redirect campo users to the avance of their assigned line, or show line list."""

    def get(self, request, *args, **kwargs):
        from apps.cuadrillas.models import CuadrillaMiembro

        # Find the user's active cuadrilla assignment
        asignacion = CuadrillaMiembro.objects.filter(
            usuario=request.user,
            activo=True,
            cuadrilla__activa=True,
        ).select_related('cuadrilla__linea_asignada').first()

        if asignacion and asignacion.cuadrilla.linea_asignada:
            return redirect('lineas:avance_campo_linea', pk=asignacion.cuadrilla.linea_asignada.pk)

        # No cuadrilla or no line assigned — show all active lines
        lineas = Linea.objects.filter(activa=True).prefetch_related('torres')
        lineas_data = []
        for linea in lineas:
            total_torres = linea.torres.count()
            lineas_data.append({
                'linea': linea,
                'total_torres': total_torres,
            })

        from django.shortcuts import render
        return render(request, 'lineas/avance_campo.html', {
            'lineas_data': lineas_data,
            'sin_cuadrilla': True,
        })


class AvanceCampoLineaView(LoginRequiredMixin, HTMXMixin, DetailView):
    """Simplified tower-by-tower progress for campo users."""
    model = Linea
    template_name = 'lineas/avance_campo.html'
    context_object_name = 'linea'

    def get_context_data(self, **kwargs):
        from collections import defaultdict
        from apps.actividades.models import Actividad

        context = super().get_context_data(**kwargs)
        linea = self.object

        torres = linea.torres.all().order_by('numero')

        actividades = Actividad.objects.filter(
            linea=linea
        ).select_related('torre', 'tipo_actividad').order_by('torre__numero')

        actividades_por_torre = defaultdict(list)
        for act in actividades:
            actividades_por_torre[str(act.torre_id)].append(act)

        filas_torres = []
        total_actividades = 0
        total_completadas = 0
        for torre in torres:
            acts = actividades_por_torre.get(str(torre.id), [])
            completadas = sum(1 for a in acts if a.estado == 'COMPLETADA')
            en_curso = sum(1 for a in acts if a.estado == 'EN_CURSO')
            pendientes = sum(1 for a in acts if a.estado in ('PENDIENTE', 'PROGRAMADA'))
            total = len(acts)

            total_actividades += total
            total_completadas += completadas

            porcentaje = round(completadas / total * 100) if total > 0 else 0

            if total == 0:
                estado_color = 'gray'
            elif completadas == total:
                estado_color = 'green'
            elif en_curso > 0:
                estado_color = 'blue'
            elif pendientes > 0:
                estado_color = 'yellow'
            else:
                estado_color = 'gray'

            filas_torres.append({
                'torre': torre,
                'total': total,
                'completadas': completadas,
                'en_curso': en_curso,
                'pendientes': pendientes,
                'porcentaje': porcentaje,
                'estado_color': estado_color,
                'actividades': acts,
            })

        context['filas_torres'] = filas_torres
        context['total_torres'] = torres.count()
        context['total_actividades'] = total_actividades
        context['total_completadas'] = total_completadas
        context['porcentaje_global'] = (
            round(total_completadas / total_actividades * 100)
            if total_actividades > 0 else 0
        )

        return context


class MarcarActividadCompletadaView(LoginRequiredMixin, View):
    """Allow campo users to mark an activity as completed."""

    def post(self, request, pk):
        from apps.actividades.models import Actividad
        from apps.cuadrillas.models import CuadrillaMiembro

        try:
            actividad = Actividad.objects.select_related('linea').get(pk=pk)
        except Actividad.DoesNotExist:
            messages.error(request, 'Actividad no encontrada.')
            return redirect('lineas:mi_avance')

        # Verify user belongs to a cuadrilla assigned to this line
        tiene_acceso = CuadrillaMiembro.objects.filter(
            usuario=request.user,
            activo=True,
            cuadrilla__activa=True,
            cuadrilla__linea_asignada=actividad.linea,
        ).exists()

        # Also allow admin/coordinador roles
        if not tiene_acceso and request.user.rol not in ('admin', 'director', 'coordinador', 'ing_residente'):
            messages.error(request, 'No tiene permiso para marcar esta actividad.')
            return redirect('lineas:mi_avance')

        if actividad.estado in ('PENDIENTE', 'PROGRAMADA', 'EN_CURSO'):
            actividad.completar()
            messages.success(request, f'Actividad marcada como ejecutada.')
        else:
            messages.info(request, 'La actividad ya fue completada o no se puede modificar.')

        return redirect('lineas:avance_campo_linea', pk=actividad.linea.pk)


class AvanceLineaView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """Tower-by-tower progress tracking for a line."""
    model = Linea
    template_name = 'lineas/avance.html'
    context_object_name = 'linea'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get_context_data(self, **kwargs):
        from collections import defaultdict
        from apps.actividades.models import Actividad

        context = super().get_context_data(**kwargs)
        linea = self.object

        torres = linea.torres.all().order_by('numero')

        # Get all activities for this line grouped by torre
        actividades = Actividad.objects.filter(
            linea=linea
        ).select_related('torre', 'tipo_actividad').order_by('torre__numero')

        actividades_por_torre = defaultdict(list)
        for act in actividades:
            actividades_por_torre[str(act.torre_id)].append(act)

        # Build progress data per tower
        filas_torres = []
        total_actividades = 0
        total_completadas = 0
        for torre in torres:
            acts = actividades_por_torre.get(str(torre.id), [])
            completadas = sum(1 for a in acts if a.estado == 'COMPLETADA')
            en_curso = sum(1 for a in acts if a.estado == 'EN_CURSO')
            pendientes = sum(1 for a in acts if a.estado in ('PENDIENTE', 'PROGRAMADA'))
            total = len(acts)

            total_actividades += total
            total_completadas += completadas

            if total > 0:
                porcentaje = round(completadas / total * 100)
            else:
                porcentaje = 0

            # Determine status color
            if total == 0:
                estado_color = 'gray'
            elif completadas == total:
                estado_color = 'green'
            elif en_curso > 0:
                estado_color = 'blue'
            elif pendientes > 0:
                estado_color = 'yellow'
            else:
                estado_color = 'gray'

            filas_torres.append({
                'torre': torre,
                'total': total,
                'completadas': completadas,
                'en_curso': en_curso,
                'pendientes': pendientes,
                'porcentaje': porcentaje,
                'estado_color': estado_color,
                'actividades': acts,
            })

        context['filas_torres'] = filas_torres
        context['total_torres'] = torres.count()
        context['total_actividades'] = total_actividades
        context['total_completadas'] = total_completadas
        context['porcentaje_global'] = (
            round(total_completadas / total_actividades * 100)
            if total_actividades > 0 else 0
        )

        return context


class TorreCreateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Create a new tower for a transmission line."""
    allowed_roles = ['admin', 'director', 'coordinador']

    def get(self, request, linea_pk):
        """Show the form to create a new tower."""
        try:
            linea = Linea.objects.get(pk=linea_pk)
        except Linea.DoesNotExist:
            messages.error(request, 'Línea no encontrada.')
            return redirect('lineas:lista')

        from .forms import TorreForm
        form = TorreForm()
        return self.render_form(request, linea, form)

    def post(self, request, linea_pk):
        """Handle form submission to create a tower."""
        try:
            linea = Linea.objects.get(pk=linea_pk)
        except Linea.DoesNotExist:
            messages.error(request, 'Línea no encontrada.')
            return redirect('lineas:lista')

        from .forms import TorreForm
        from django.db import IntegrityError
        form = TorreForm(request.POST)

        if form.is_valid():
            tower = form.save(commit=False)
            tower.linea = linea
            # Set default coordinates (can be updated later)
            tower.latitud = 4.5709
            tower.longitud = -74.2973
            try:
                tower.save()
                messages.success(request, f'Torre {tower.numero} creada exitosamente.')
                return redirect('lineas:detalle', pk=linea_pk)
            except IntegrityError:
                messages.error(request, f'Ya existe una torre con número "{tower.numero}" en esta línea. Use un número diferente.')
                return self.render_form(request, linea, form)
        else:
            messages.error(request, 'Error al crear la torre. Revise los datos.')
            return self.render_form(request, linea, form)

    def render_form(self, request, linea, form):
        """Render the tower form."""
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from django.urls import reverse
        html = render_to_string('lineas/partials/torre_form.html', {
            'form': form,
            'linea': linea,
            'accion': 'Crear Torre',
            'form_action': reverse('lineas:torre_crear', kwargs={'linea_pk': linea.id})
        }, request=request)
        return HttpResponse(html)


class TorreEditView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Edit an existing tower."""
    allowed_roles = ['admin', 'director', 'coordinador']

    def get(self, request, pk):
        """Show the form to edit a tower."""
        try:
            torre = Torre.objects.get(pk=pk)
        except Torre.DoesNotExist:
            messages.error(request, 'Torre no encontrada.')
            return redirect('lineas:lista')

        from .forms import TorreForm
        form = TorreForm(instance=torre)
        return self.render_form(request, torre, form)

    def post(self, request, pk):
        """Handle form submission to edit a tower."""
        try:
            torre = Torre.objects.get(pk=pk)
        except Torre.DoesNotExist:
            messages.error(request, 'Torre no encontrada.')
            return redirect('lineas:lista')

        from .forms import TorreForm
        form = TorreForm(request.POST, instance=torre)

        if form.is_valid():
            form.save()
            messages.success(request, f'Torre {torre.numero} actualizada exitosamente.')
            return redirect('lineas:detalle', pk=torre.linea.pk)
        else:
            messages.error(request, 'Error al actualizar la torre. Revise los datos.')
            return self.render_form(request, torre, form)

    def render_form(self, request, torre, form):
        """Render the tower form."""
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from django.urls import reverse
        html = render_to_string('lineas/partials/torre_form.html', {
            'form': form,
            'linea': torre.linea,
            'torre': torre,
            'accion': 'Editar Torre',
            'form_action': reverse('lineas:torre_editar', kwargs={'pk': torre.id})
        }, request=request)
        return HttpResponse(html)


class TorreMasivaCreateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Create multiple towers at once."""
    allowed_roles = ['admin', 'director', 'coordinador']

    def get(self, request, linea_pk):
        """Show the form to create multiple towers."""
        try:
            linea = Linea.objects.get(pk=linea_pk)
        except Linea.DoesNotExist:
            messages.error(request, 'Línea no encontrada.')
            return redirect('lineas:lista')

        from .forms import TorreMasivaForm
        form = TorreMasivaForm()
        return self.render_form(request, linea, form)

    def post(self, request, linea_pk):
        """Handle form submission to create multiple towers."""
        try:
            linea = Linea.objects.get(pk=linea_pk)
        except Linea.DoesNotExist:
            messages.error(request, 'Línea no encontrada.')
            return redirect('lineas:lista')

        from .forms import TorreMasivaForm
        from django.db import IntegrityError
        form = TorreMasivaForm(request.POST)

        if form.is_valid():
            cantidad = form.cleaned_data['cantidad']
            numero_inicial = form.cleaned_data['numero_inicial']
            tipo = form.cleaned_data['tipo']
            municipio = form.cleaned_data['municipio']

            # Extract prefix and starting number
            import re
            match = re.match(r'^([A-Za-z]*)-?(\d+)$', numero_inicial)
            if not match:
                messages.error(request, 'Formato de número inválido. Use formato como "T-001".')
                return self.render_form(request, linea, form)

            prefix = match.group(1) or 'T'
            start_num = int(match.group(2))

            torres_creadas = 0
            torres_duplicadas = 0

            for i in range(cantidad):
                numero = f"{prefix}-{str(start_num + i).zfill(len(match.group(2)))}"
                try:
                    torre = Torre.objects.create(
                        linea=linea,
                        numero=numero,
                        tipo=tipo,
                        municipio=municipio,
                        latitud=4.5709,
                        longitud=-74.2973
                    )
                    torres_creadas += 1
                except IntegrityError:
                    torres_duplicadas += 1

            if torres_creadas > 0:
                if torres_duplicadas > 0:
                    messages.success(request, f'Se crearon {torres_creadas} torres. {torres_duplicadas} torres ya existían.')
                else:
                    messages.success(request, f'Se crearon {torres_creadas} torres exitosamente.')
            else:
                messages.error(request, f'No se crearon torres. {torres_duplicadas} torres ya existían.')

            return redirect('lineas:detalle', pk=linea_pk)
        else:
            messages.error(request, 'Error al crear las torres. Revise los datos.')
            return self.render_form(request, linea, form)

    def render_form(self, request, linea, form):
        """Render the massive tower form."""
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from django.urls import reverse
        html = render_to_string('lineas/partials/torre_masiva_form.html', {
            'form': form,
            'linea': linea,
            'form_action': reverse('lineas:torre_masiva_crear', kwargs={'linea_pk': linea.id})
        }, request=request)
        return HttpResponse(html)


class TorreUpdateObservacionesView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Update observaciones of a tower via API."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    @method_decorator(require_http_methods(["PATCH"]))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def patch(self, request, pk):
        """Handle PATCH request to update observaciones."""
        try:
            torre = Torre.objects.get(pk=pk)
            data = json.loads(request.body)
            observaciones = data.get('observaciones', '')

            torre.observaciones = observaciones
            torre.save(update_fields=['observaciones'])

            return JsonResponse({
                'status': 'success',
                'message': 'Observaciones actualizadas',
                'observaciones': torre.observaciones
            })
        except Torre.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Torre no encontrada'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


class TorreDeleteView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Delete a tower."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def delete(self, request, pk):
        try:
            torre = Torre.objects.get(pk=pk)
            torre.delete()
            return JsonResponse({'success': True, 'message': 'Torre eliminada'})
        except Torre.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Torre no encontrada'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


class VanoCreateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Create a new vano."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def post(self, request, linea_id):
        try:
            linea = Linea.objects.get(pk=linea_id)
            data = json.loads(request.body)

            vano = Vano.objects.create(
                linea=linea,
                numero=data.get('numero'),
                observaciones=data.get('observaciones', '')
            )
            return JsonResponse({'success': True, 'message': 'Vano creado', 'id': str(vano.id)})
        except Linea.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Línea no encontrada'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


class VanoEditView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Edit a vano."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def patch(self, request, pk):
        try:
            vano = Vano.objects.get(pk=pk)
            data = json.loads(request.body)
            vano.observaciones = data.get('observaciones', '')
            vano.save(update_fields=['observaciones'])
            return JsonResponse({'success': True, 'message': 'Vano actualizado'})
        except Vano.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Vano no encontrado'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


class VanoDeleteView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Delete a vano."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def delete(self, request, pk):
        try:
            vano = Vano.objects.get(pk=pk)
            vano.delete()
            return JsonResponse({'success': True, 'message': 'Vano eliminado'})
        except Vano.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Vano no encontrado'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
