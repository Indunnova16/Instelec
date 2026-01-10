"""
Views for transmission lines.
"""
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import Linea, Torre


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

        buscar = self.request.GET.get('buscar')
        if buscar:
            qs = qs.filter(nombre__icontains=buscar) | qs.filter(codigo__icontains=buscar)

        return qs.prefetch_related('torres')


class LineaDetailView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """Detail view for a transmission line."""
    model = Linea
    template_name = 'lineas/detalle.html'
    partial_template_name = 'lineas/partials/detalle_linea.html'
    context_object_name = 'linea'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'ing_ambiental', 'supervisor', 'liniero']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['torres'] = self.object.torres.all()[:50]
        context['total_torres'] = self.object.torres.count()
        return context


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
        context = super().get_context_data(**kwargs)
        # Get all active lines with their towers
        lineas = Linea.objects.filter(activa=True).prefetch_related('torres')
        context['lineas'] = lineas

        # Prepare GeoJSON data for the map
        torres_data = []
        for linea in lineas:
            for torre in linea.torres.all():
                if torre.latitud and torre.longitud:
                    torres_data.append({
                        'id': str(torre.id),
                        'numero': torre.numero,
                        'linea': linea.codigo,
                        'tipo': torre.tipo,
                        'estado': torre.estado,
                        'lat': float(torre.latitud),
                        'lng': float(torre.longitud),
                    })
        context['torres_json'] = torres_data
        return context
