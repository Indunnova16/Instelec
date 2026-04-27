"""
Views for the construccion (construction) app.
"""
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.db.models import Q

from apps.core.mixins import RoleRequiredMixin
from .models import (
    ProyectoConstruccion,
    TorreConstruccion,
    PataObra,
    FaseTorre,
    SocialPredial,
    AmbientalTorre,
    ControlLluvia,
    ReporteReplanteo,
    PersonalSST,
    EntregaElectromecanica,
    CorreccionEntrega,
)


class ProyectoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List all active construction projects."""
    model = ProyectoConstruccion
    template_name = 'construccion/proyecto_list.html'
    context_object_name = 'proyectos'
    paginate_by = 20
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        return ProyectoConstruccion.objects.filter(
            estado__in=['PLANIFICACION', 'EJECUCION', 'CIERRE']
        ).order_by('-created_at')


class ProyectoDashboardView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Show construction project dashboard with KPIs."""
    model = ProyectoConstruccion
    template_name = 'construccion/proyecto_dashboard.html'
    context_object_name = 'proyecto'
    allowed_roles = ['admin', 'director', 'coordinador']


class TorresListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List towers in a construction project."""
    model = TorreConstruccion
    template_name = 'construccion/torres_list.html'
    context_object_name = 'torres'
    paginate_by = 50
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        proyecto_id = self.kwargs.get('proyecto_id')
        return TorreConstruccion.objects.filter(
            proyecto_id=proyecto_id
        ).order_by('numero')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        context['proyecto'] = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        return context


class TorreCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    """Create a new tower in a construction project."""
    model = TorreConstruccion
    template_name = 'construccion/torre_form.html'
    fields = [
        'numero', 'tipo', 'tipo_cimentacion', 'peso_kg', 'tramo_tendido',
        'latitud', 'longitud', 'cuadrilla_civil', 'cuadrilla_montaje',
        'cuadrilla_tendido', 'observaciones'
    ]
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        context['proyecto'] = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        return context

    def form_valid(self, form):
        proyecto_id = self.kwargs.get('proyecto_id')
        form.instance.proyecto_id = proyecto_id
        response = super().form_valid(form)
        # Create related records
        torre = self.object
        for pata in ['A', 'B', 'C', 'D']:
            PataObra.objects.get_or_create(torre=torre, pata=pata)
        FaseTorre.objects.get_or_create(torre=torre, proyecto_id=proyecto_id)
        SocialPredial.objects.get_or_create(torre=torre)
        AmbientalTorre.objects.get_or_create(torre=torre)
        EntregaElectromecanica.objects.get_or_create(torre=torre)
        CorreccionEntrega.objects.get_or_create(torre=torre)
        return response

    def get_success_url(self):
        return reverse_lazy('construccion:torres_lista', kwargs={'proyecto_id': self.kwargs.get('proyecto_id')})


class TorreEditView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Edit a tower."""
    model = TorreConstruccion
    template_name = 'construccion/torre_form.html'
    fields = [
        'numero', 'tipo', 'tipo_cimentacion', 'peso_kg', 'tramo_tendido',
        'latitud', 'longitud', 'cuadrilla_civil', 'cuadrilla_montaje',
        'cuadrilla_tendido', 'observaciones'
    ]
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        context['proyecto'] = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        return context

    def get_success_url(self):
        return reverse_lazy('construccion:torres_lista', kwargs={'proyecto_id': self.kwargs.get('proyecto_id')})


class TorreDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    """Delete a tower."""
    model = TorreConstruccion
    allowed_roles = ['admin']

    def get_success_url(self):
        return reverse_lazy('construccion:torres_lista', kwargs={'proyecto_id': self.kwargs.get('proyecto_id')})


class SeguimientoDiarioView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Daily tracking matrix - towers × construction phases."""
    template_name = 'construccion/seguimiento_diario.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        torres = TorreConstruccion.objects.filter(proyecto=proyecto).order_by('numero')

        context['proyecto'] = proyecto
        context['torres'] = torres
        context['fases'] = FaseTorre.objects.filter(proyecto=proyecto).select_related('torre')
        context['patas_obra'] = PataObra.objects.filter(
            torre__proyecto=proyecto
        ).select_related('torre').order_by('torre__numero')

        return context


class SocialPredialView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Land/social clearance tracking matrix."""
    template_name = 'construccion/social_predial.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'gestor_social']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        context['proyecto'] = proyecto
        context['social_predial'] = SocialPredial.objects.filter(
            torre__proyecto=proyecto
        ).select_related('torre').order_by('torre__numero')

        return context


class AmbientalView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Environmental clearance tracking matrix."""
    template_name = 'construccion/ambiental.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ambientalista']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        context['proyecto'] = proyecto
        context['ambiental'] = AmbientalTorre.objects.filter(
            torre__proyecto=proyecto
        ).select_related('torre').order_by('torre__numero')

        return context


class ControlLluviaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Rain hours log for delay justification."""
    template_name = 'construccion/control_lluvia.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        context['proyecto'] = proyecto
        context['registros'] = ControlLluvia.objects.filter(
            torre__proyecto=proyecto
        ).order_by('-fecha')

        return context


class ReplanteoView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Topographic survey daily report."""
    template_name = 'construccion/replanteo.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'topografo']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        context['proyecto'] = proyecto
        context['reportes'] = ReporteReplanteo.objects.filter(
            proyecto=proyecto
        ).order_by('-fecha_ejecutado')

        return context


class SSTView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Health & Safety (SST) personnel."""
    template_name = 'construccion/sst.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        context['proyecto'] = proyecto
        context['personal_sst'] = PersonalSST.objects.filter(
            proyecto=proyecto
        ).order_by('nombre_completo')

        return context


class EntregaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Electromechanical delivery inspection records."""
    template_name = 'construccion/entrega.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'interventor']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        context['proyecto'] = proyecto
        context['entregas'] = EntregaElectromecanica.objects.filter(
            torre__proyecto=proyecto
        ).select_related('torre').order_by('torre__numero')

        return context


class PendientesView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Post-delivery corrections punch-list."""
    template_name = 'construccion/pendientes.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'interventor']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        context['proyecto'] = proyecto
        context['correcciones'] = CorreccionEntrega.objects.filter(
            torre__proyecto=proyecto
        ).select_related('torre').order_by('torre__numero')

        return context
