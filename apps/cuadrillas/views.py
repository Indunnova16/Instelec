"""
Views for crew management.
"""
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import Cuadrilla, TrackingUbicacion


class CuadrillaListView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, ListView):
    """List all crews."""
    model = Cuadrilla
    template_name = 'cuadrillas/lista.html'
    partial_template_name = 'cuadrillas/partials/lista_cuadrillas.html'
    context_object_name = 'cuadrillas'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get_queryset(self):
        return Cuadrilla.objects.filter(activa=True).select_related(
            'supervisor', 'vehiculo', 'linea_asignada'
        ).prefetch_related('miembros__usuario')

    def get_context_data(self, **kwargs):
        import json
        context = super().get_context_data(**kwargs)

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
        context = super().get_context_data(**kwargs)
        context['miembros'] = self.object.miembros.filter(activo=True).select_related('usuario')

        # Last known location
        ultima_ubicacion = TrackingUbicacion.objects.filter(
            cuadrilla=self.object
        ).order_by('-created_at').first()
        context['ultima_ubicacion'] = ultima_ubicacion

        return context


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
