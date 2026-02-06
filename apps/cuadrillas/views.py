"""
Views for crew management.
"""
from django.shortcuts import redirect
from django.contrib import messages
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import Cuadrilla, CuadrillaMiembro, Vehiculo, TrackingUbicacion


class CuadrillaListView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, ListView):
    """List all crews, organized by week."""
    model = Cuadrilla
    template_name = 'cuadrillas/lista.html'
    partial_template_name = 'cuadrillas/partials/lista_cuadrillas.html'
    context_object_name = 'cuadrillas'
    paginate_by = None
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    @staticmethod
    def _parse_semana(codigo):
        """Extract (week, year) from code format WW-YYYY-XXX."""
        try:
            parts = codigo.split('-')
            if len(parts) >= 2:
                semana = int(parts[0])
                ano = int(parts[1])
                if 1 <= semana <= 53 and 2000 <= ano <= 2100:
                    return semana, ano
        except (ValueError, IndexError):
            pass
        return None, None

    def get_queryset(self):
        qs = Cuadrilla.objects.filter(activa=True).select_related(
            'supervisor', 'vehiculo', 'linea_asignada'
        ).prefetch_related('miembros__usuario')

        # Filter by week if parameter provided
        semana_param = self.request.GET.get('semana', '').strip()
        if semana_param:
            # Format: WW-YYYY
            try:
                parts = semana_param.split('-')
                sem = parts[0].zfill(2)
                ano = parts[1]
                qs = qs.filter(codigo__startswith=f'{sem}-{ano}-')
            except (IndexError, ValueError):
                pass

        return qs

    def get_context_data(self, **kwargs):
        import json
        from collections import OrderedDict
        context = super().get_context_data(**kwargs)

        # Build list of available weeks from all active cuadrillas
        todas = Cuadrilla.objects.filter(activa=True).values_list('codigo', flat=True)
        semanas_set = set()
        for codigo in todas:
            sem, ano = self._parse_semana(codigo)
            if sem is not None:
                semanas_set.add((ano, sem))

        # Sort descending: most recent first
        semanas_disponibles = sorted(semanas_set, reverse=True)
        context['semanas_disponibles'] = [
            {'value': f'{s[1]}-{s[0]}', 'label': f'Semana {s[1]} - {s[0]}'}
            for s in semanas_disponibles
        ]

        # Current filter
        semana_param = self.request.GET.get('semana', '').strip()
        context['semana_actual'] = semana_param

        # Group cuadrillas by week for display
        cuadrillas_por_semana = OrderedDict()
        sin_semana = []
        for cuadrilla in context['cuadrillas']:
            sem, ano = self._parse_semana(cuadrilla.codigo)
            if sem is not None:
                key = f'Semana {sem} - {ano}'
                cuadrillas_por_semana.setdefault(key, []).append(cuadrilla)
            else:
                sin_semana.append(cuadrilla)

        if sin_semana:
            cuadrillas_por_semana['Otras'] = sin_semana

        context['cuadrillas_por_semana'] = cuadrillas_por_semana

        # Stats
        all_active = Cuadrilla.objects.filter(activa=True)
        context['total_cuadrillas'] = all_active.count()
        context['cuadrillas_activas'] = all_active.count()

        # Get latest location for each active crew for the mini-map
        ubicaciones = []
        for cuadrilla in context['cuadrillas']:
            ultima = TrackingUbicacion.objects.filter(
                cuadrilla=cuadrilla
            ).order_by('-created_at').first()

            if ultima:
                ubicaciones.append({
                    'cuadrilla_id': str(cuadrilla.id),
                    'cuadrilla_codigo': cuadrilla.codigo,
                    'lat': float(ultima.latitud),
                    'lng': float(ultima.longitud),
                })

        context['cuadrillas_ubicaciones_json'] = json.dumps(ubicaciones)
        return context


class CuadrillaDetailView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """Detail view for a crew."""
    model = Cuadrilla
    template_name = 'cuadrillas/detalle.html'
    context_object_name = 'cuadrilla'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get_context_data(self, **kwargs):
        from decimal import Decimal
        from apps.usuarios.models import Usuario

        context = super().get_context_data(**kwargs)
        miembros = self.object.miembros.filter(activo=True).select_related('usuario')
        context['miembros'] = miembros

        # Total daily cost
        context['costo_total_dia'] = sum(
            (m.costo_dia for m in miembros), Decimal('0')
        )

        # Available users for add member form
        miembros_ids = miembros.values_list('usuario_id', flat=True)
        context['usuarios_disponibles'] = Usuario.objects.filter(
            is_active=True
        ).exclude(id__in=miembros_ids).order_by('first_name', 'last_name')

        # Choices for form selects
        context['roles_cuadrilla'] = CuadrillaMiembro.RolCuadrilla.choices
        context['cargos_jerarquicos'] = CuadrillaMiembro.CargoJerarquico.choices

        # Last known location
        ultima_ubicacion = TrackingUbicacion.objects.filter(
            cuadrilla=self.object
        ).order_by('-created_at').first()
        context['ultima_ubicacion'] = ultima_ubicacion

        return context


class CuadrillaEditView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """View for editing a crew."""
    model = Cuadrilla
    template_name = 'cuadrillas/editar.html'
    context_object_name = 'cuadrilla'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.usuarios.models import Usuario
        from apps.lineas.models import Linea
        context['supervisores'] = Usuario.objects.filter(rol='supervisor', is_active=True)
        context['lineas'] = Linea.objects.filter(activa=True)
        context['vehiculos'] = Vehiculo.objects.filter(activo=True)
        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission to update a crew."""
        from apps.usuarios.models import Usuario
        from apps.lineas.models import Linea

        cuadrilla = self.get_object()

        codigo = request.POST.get('codigo', '').strip()
        nombre = request.POST.get('nombre', '').strip()

        if not codigo or not nombre:
            messages.error(request, 'Código y nombre son obligatorios.')
            return self.get(request, *args, **kwargs)

        if Cuadrilla.objects.filter(codigo=codigo).exclude(pk=cuadrilla.pk).exists():
            messages.error(request, f'Ya existe otra cuadrilla con el código {codigo}.')
            return self.get(request, *args, **kwargs)

        try:
            cuadrilla.codigo = codigo
            cuadrilla.nombre = nombre

            supervisor_id = request.POST.get('supervisor') or None
            cuadrilla.supervisor = Usuario.objects.get(pk=supervisor_id) if supervisor_id else None

            vehiculo_id = request.POST.get('vehiculo') or None
            cuadrilla.vehiculo = Vehiculo.objects.get(pk=vehiculo_id) if vehiculo_id else None

            linea_id = request.POST.get('linea_asignada') or None
            cuadrilla.linea_asignada = Linea.objects.get(pk=linea_id) if linea_id else None

            fecha_str = request.POST.get('fecha', '').strip()
            if fecha_str:
                from datetime import date as date_cls
                cuadrilla.fecha = date_cls.fromisoformat(fecha_str)
            else:
                cuadrilla.fecha = None

            cuadrilla.activa = request.POST.get('activa') == 'on'
            cuadrilla.observaciones = request.POST.get('observaciones', '').strip()
            cuadrilla.save()
            messages.success(request, f'Cuadrilla {cuadrilla.codigo} actualizada exitosamente.')
            return redirect('cuadrillas:detalle', pk=cuadrilla.pk)
        except (Usuario.DoesNotExist, Linea.DoesNotExist, Vehiculo.DoesNotExist) as e:
            messages.error(request, f'Referencia inválida: {str(e)}')
            return self.get(request, *args, **kwargs)
        except Exception as e:
            messages.error(request, f'Error al actualizar la cuadrilla: {str(e)}')
            return self.get(request, *args, **kwargs)


class MapaCuadrillasView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Real-time map of all crews."""
    template_name = 'cuadrillas/mapa.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']


class MapaCuadrillasPartialView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Partial view for HTMX polling of crew locations."""
    template_name = 'cuadrillas/partials/mapa_cuadrillas.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get latest location for each active crew
        cuadrillas = Cuadrilla.objects.filter(activa=True)
        ubicaciones = []

        for cuadrilla in cuadrillas:
            ultima = TrackingUbicacion.objects.filter(
                cuadrilla=cuadrilla
            ).order_by('-created_at').first()

            if ultima:
                ubicaciones.append({
                    'cuadrilla_id': str(cuadrilla.id),
                    'cuadrilla_codigo': cuadrilla.codigo,
                    'cuadrilla_nombre': cuadrilla.nombre,
                    'lat': float(ultima.latitud),
                    'lng': float(ultima.longitud),
                    'precision': float(ultima.precision_metros) if ultima.precision_metros else None,
                    'timestamp': ultima.created_at.isoformat(),
                })

        context['ubicaciones'] = ubicaciones
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('Accept') == 'application/json':
            return JsonResponse({'ubicaciones': context['ubicaciones']})
        return super().render_to_response(context, **response_kwargs)


class CuadrillaCreateView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """View for creating a new crew."""
    template_name = 'cuadrillas/crear.html'
    partial_template_name = 'cuadrillas/partials/form_cuadrilla.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.usuarios.models import Usuario
        from apps.lineas.models import Linea
        context['supervisores'] = Usuario.objects.filter(rol='supervisor', is_active=True)
        context['lineas'] = Linea.objects.filter(activa=True)
        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission to create a new crew."""
        from django.shortcuts import redirect
        from django.contrib import messages
        from apps.usuarios.models import Usuario
        from apps.lineas.models import Linea

        codigo = request.POST.get('codigo', '').strip()
        nombre = request.POST.get('nombre', '').strip()
        supervisor_id = request.POST.get('supervisor') or None
        linea_id = request.POST.get('linea_asignada') or None

        # Validation
        if not codigo or not nombre:
            messages.error(request, 'Código y nombre son obligatorios.')
            return self.get(request, *args, **kwargs)

        if Cuadrilla.objects.filter(codigo=codigo).exists():
            messages.error(request, f'Ya existe una cuadrilla con el código {codigo}.')
            return self.get(request, *args, **kwargs)

        # Get related objects
        supervisor = None
        if supervisor_id:
            try:
                supervisor = Usuario.objects.get(pk=supervisor_id)
            except Usuario.DoesNotExist:
                pass

        linea_asignada = None
        if linea_id:
            try:
                linea_asignada = Linea.objects.get(pk=linea_id)
            except Linea.DoesNotExist:
                pass

        # Create the crew
        try:
            cuadrilla = Cuadrilla.objects.create(
                codigo=codigo,
                nombre=nombre,
                supervisor=supervisor,
                linea_asignada=linea_asignada,
            )
            messages.success(request, f'Cuadrilla {cuadrilla.codigo} creada exitosamente.')
            return redirect('cuadrillas:detalle', pk=cuadrilla.pk)
        except Exception as e:
            messages.error(request, f'Error al crear la cuadrilla: {str(e)}')
            return self.get(request, *args, **kwargs)


class CuadrillaMiembroAddView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Add a member to a cuadrilla."""
    model = Cuadrilla
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def post(self, request, *args, **kwargs):
        from apps.usuarios.models import Usuario
        from datetime import date

        cuadrilla = self.get_object()
        usuario_id = request.POST.get('usuario')
        rol = request.POST.get('rol_cuadrilla', 'LINIERO_I')
        cargo = request.POST.get('cargo', 'MIEMBRO')
        costo_dia = request.POST.get('costo_dia', '0') or '0'

        if not usuario_id:
            messages.error(request, 'Debe seleccionar un usuario.')
            return redirect('cuadrillas:detalle', pk=cuadrilla.pk)

        try:
            usuario = Usuario.objects.get(pk=usuario_id)
        except Usuario.DoesNotExist:
            messages.error(request, 'Usuario no encontrado.')
            return redirect('cuadrillas:detalle', pk=cuadrilla.pk)

        if CuadrillaMiembro.objects.filter(
            cuadrilla=cuadrilla, usuario=usuario, activo=True
        ).exists():
            messages.error(request, f'{usuario.get_full_name()} ya es miembro activo.')
            return redirect('cuadrillas:detalle', pk=cuadrilla.pk)

        try:
            CuadrillaMiembro.objects.create(
                cuadrilla=cuadrilla,
                usuario=usuario,
                rol_cuadrilla=rol if rol in dict(CuadrillaMiembro.RolCuadrilla.choices) else 'LINIERO_I',
                cargo=cargo if cargo in dict(CuadrillaMiembro.CargoJerarquico.choices) else 'MIEMBRO',
                costo_dia=float(costo_dia),
                fecha_inicio=date.today(),
            )
            messages.success(request, f'{usuario.get_full_name()} agregado a la cuadrilla.')
        except Exception as e:
            messages.error(request, f'Error al agregar miembro: {str(e)}')

        return redirect('cuadrillas:detalle', pk=cuadrilla.pk)


class CuadrillaMiembroRemoveView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Remove a member from a cuadrilla (soft delete)."""
    model = Cuadrilla
    allowed_roles = ['admin', 'director', 'coordinador']

    def post(self, request, *args, **kwargs):
        from datetime import date

        cuadrilla = self.get_object()
        miembro_pk = self.kwargs['miembro_pk']

        try:
            miembro = CuadrillaMiembro.objects.get(pk=miembro_pk, cuadrilla=cuadrilla)
            nombre = miembro.usuario.get_full_name()
            miembro.activo = False
            miembro.fecha_fin = date.today()
            miembro.save(update_fields=['activo', 'fecha_fin', 'updated_at'])
            messages.success(request, f'{nombre} removido de la cuadrilla.')
        except CuadrillaMiembro.DoesNotExist:
            messages.error(request, 'Miembro no encontrado.')

        return redirect('cuadrillas:detalle', pk=cuadrilla.pk)
