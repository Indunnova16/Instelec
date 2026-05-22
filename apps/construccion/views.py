"""
Views for the construccion (construction) app.
"""
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Q

from apps.core.mixins import RoleRequiredMixin
from apps.contratos.models import Contrato
from .forms import ContratoForm
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
    ObraProteccion,
    PruebaTecnica,
    KitCerramiento,
    ProgramacionFase,
    CategoriaFinanciera,
    PeriodoFinanciero,
    MovimientoFinanciero,
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'dashboard'
        return context


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


class ProgramacionView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Programming and scheduling view."""
    template_name = 'construccion/programacion.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        return context


class RSDataView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """RS Data (Remote Sensing/Reporting) view."""
    template_name = 'construccion/rs_data.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        return context


class HochimimView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Hochimin (Equipment/Materials) tracking view."""
    template_name = 'construccion/hochimin.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        return context


class LecturaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Lectura (Readings/Measurements) view."""
    template_name = 'construccion/lectura.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'topografo']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        return context


class EntregaFlechasView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Delivery Arrows (Cable delivery/stringing) view."""
    template_name = 'construccion/entrega_flechas.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'interventor']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        return context


class ElectromecanicaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Electromechanical assembly view."""
    template_name = 'construccion/electromecanica.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'interventor']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        return context


class ContratoView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Contract details for a construction project — editable inline."""
    template_name = 'construccion/contrato.html'
    model = Contrato
    form_class = ContratoForm
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_object(self):
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        return proyecto.contrato

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['proyecto'] = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        context['active_tab'] = 'contrato'
        return context

    def get_success_url(self):
        return reverse_lazy('construccion:contrato', kwargs={'proyecto_id': self.kwargs['proyecto_id']})


class IngenieriaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Engineering and construction tracking."""
    template_name = 'construccion/ingenieria.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        context['active_tab'] = 'ingenieria'
        return context


class PreliminaresView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Preliminary work and surveys."""
    template_name = 'construccion/preliminares.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'topografo']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['proyecto'] = proyecto
        context['active_tab'] = 'preliminares'
        return context


# ==========================================================================
# Vistas CRUD para modelos nuevos (Sprint UI #59 #60 #65)
# ==========================================================================

ALL_ADMIN_ROLES = [
    'admin', 'director', 'coordinador', 'ing_residente',
    'admin_general', 'coordinador_general', 'admin_construccion',
]


class ObraProteccionListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Listado de obras de protección (#59) por proyecto."""
    template_name = 'construccion/protecciones_lista.html'
    context_object_name = 'protecciones'
    allowed_roles = ALL_ADMIN_ROLES

    def get_queryset(self):
        return ObraProteccion.objects.filter(
            torre__proyecto_id=self.kwargs['proyecto_id']
        ).select_related('torre', 'cuadrilla').order_by('torre__numero')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'protecciones'
        return ctx


class ObraProteccionCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = ObraProteccion
    template_name = 'construccion/protecciones_form.html'
    fields = ['torre', 'tipos_medida', 'metros_trinchos', 'metros_cunetas',
              'nota', 'tubo_metalico_unidades', 'malla_eslabonada_m2',
              'alambre_galvanizado_kg', 'geotextil_m2', 'cemento_bultos',
              'arena_cunetes', 'grava_cunetes', 'revegetalizacion_m2',
              'cuadrilla', 'fecha_ejecucion', 'completada_ok', 'observaciones']
    allowed_roles = ALL_ADMIN_ROLES

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['torre'].queryset = TorreConstruccion.objects.filter(
            proyecto_id=self.kwargs['proyecto_id'])
        return form

    def get_success_url(self):
        return reverse_lazy('construccion:protecciones_lista',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'protecciones'
        return ctx


class ObraProteccionUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = ObraProteccion
    template_name = 'construccion/protecciones_form.html'
    fields = ObraProteccionCreateView.fields
    pk_url_kwarg = 'pk'
    allowed_roles = ALL_ADMIN_ROLES

    def get_success_url(self):
        return reverse_lazy('construccion:protecciones_lista',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'protecciones'
        return ctx


class PruebaTecnicaListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Listado de pruebas técnicas (#60) por proyecto."""
    template_name = 'construccion/pruebas_lista.html'
    context_object_name = 'pruebas'
    allowed_roles = ALL_ADMIN_ROLES

    def get_queryset(self):
        return PruebaTecnica.objects.filter(
            proyecto_id=self.kwargs['proyecto_id']
        ).order_by('orden', 'nombre')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'pruebas'
        return ctx


class PruebaTecnicaCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = PruebaTecnica
    template_name = 'construccion/pruebas_form.html'
    fields = ['nombre', 'orden', 'fecha_programada', 'fecha_ejecucion',
              'laboratorio', 'resultado', 'adjunto', 'observaciones']
    allowed_roles = ALL_ADMIN_ROLES

    def form_valid(self, form):
        form.instance.proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('construccion:pruebas_lista',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'pruebas'
        return ctx


class PruebaTecnicaUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = PruebaTecnica
    template_name = 'construccion/pruebas_form.html'
    fields = PruebaTecnicaCreateView.fields
    pk_url_kwarg = 'pk'
    allowed_roles = ALL_ADMIN_ROLES

    def get_success_url(self):
        return reverse_lazy('construccion:pruebas_lista',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'pruebas'
        return ctx


class KitCerramientoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Listado de kits de cerramiento (#65) por proyecto, con alertas demora."""
    template_name = 'construccion/kits_lista.html'
    context_object_name = 'kits'
    allowed_roles = ALL_ADMIN_ROLES

    def get_queryset(self):
        return KitCerramiento.objects.filter(
            proyecto_id=self.kwargs['proyecto_id']
        ).select_related('torre_actual').order_by('codigo')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        qs = self.get_queryset()
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'kits'
        ctx['stats'] = {
            'total': qs.count(),
            'disponibles': qs.filter(estado='DISPONIBLE').count(),
            'en_uso': qs.filter(estado='EN_USO').count(),
            'demora': sum(1 for k in qs if k.alerta_demora),
        }
        return ctx


class KitCerramientoCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = KitCerramiento
    template_name = 'construccion/kits_form.html'
    fields = ['codigo', 'componentes', 'cantidad', 'estado', 'torre_actual',
              'fecha_ingreso_torre', 'fecha_salida_torre', 'observaciones']
    allowed_roles = ALL_ADMIN_ROLES

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['torre_actual'].queryset = TorreConstruccion.objects.filter(
            proyecto_id=self.kwargs['proyecto_id'])
        return form

    def form_valid(self, form):
        form.instance.proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('construccion:kits_lista',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'kits'
        return ctx


class KitCerramientoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = KitCerramiento
    template_name = 'construccion/kits_form.html'
    fields = KitCerramientoCreateView.fields
    pk_url_kwarg = 'pk'
    allowed_roles = ALL_ADMIN_ROLES

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['torre_actual'].queryset = TorreConstruccion.objects.filter(
            proyecto_id=self.kwargs['proyecto_id'])
        return form

    def get_success_url(self):
        return reverse_lazy('construccion:kits_lista',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'kits'
        return ctx


class CronogramaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Cronograma planeado por sección (#68) — grid editable."""
    template_name = 'construccion/cronograma.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        # Asegura una fila por cada sección estándar
        for seccion, _ in ProgramacionFase.Seccion.choices:
            ProgramacionFase.objects.get_or_create(
                proyecto=proyecto, seccion=seccion)
        ctx['proyecto'] = proyecto
        ctx['fases'] = ProgramacionFase.objects.filter(
            proyecto=proyecto).order_by('seccion')
        ctx['active_tab'] = 'cronograma'
        ctx['suma_pesos'] = sum(f.peso_pct for f in ctx['fases'])
        return ctx

    def post(self, request, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        from datetime import datetime
        for fase in ProgramacionFase.objects.filter(proyecto=proyecto):
            for field in ('fecha_inicio_planeada', 'fecha_fin_planeada',
                          'torres_planeadas', 'peso_pct', 'observaciones'):
                key = f'{fase.id}_{field}'
                if key in request.POST:
                    raw = request.POST[key].strip()
                    if field in ('fecha_inicio_planeada', 'fecha_fin_planeada'):
                        try:
                            value = datetime.strptime(raw, '%Y-%m-%d').date() if raw else None
                        except ValueError:
                            value = None
                    elif field in ('torres_planeadas', 'peso_pct'):
                        try:
                            value = int(raw) if raw else 0
                        except ValueError:
                            value = 0
                    else:
                        value = raw
                    setattr(fase, field, value)
            fase.save()
        from django.contrib import messages
        messages.success(request, 'Cronograma actualizado.')
        return redirect('construccion:cronograma', proyecto_id=proyecto.id)


class DashboardAvanceView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Dashboard de avance con curva S y barras por fase (#61)."""
    template_name = 'construccion/dashboard_avance.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres = list(proyecto.torres.all())
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'dashboard_avance'
        ctx['avance_civil_ponderado'] = proyecto.porcentaje_avance_civil_ponderado
        ctx['avance_civil_lineal'] = proyecto.porcentaje_avance_civil
        ctx['avance_montaje'] = proyecto.porcentaje_avance_montaje
        ctx['avance_tendido'] = proyecto.porcentaje_avance_tendido
        ctx['curva_s'] = proyecto.curva_s_data()
        ctx['total_torres'] = len(torres)
        ctx['torres_lista_montaje'] = sum(1 for t in torres if t.obra_civil_completa)
        ctx['torres_en_fases_paralelas'] = sum(
            1 for t in torres if len(t.fases_en_curso) > 1)
        return ctx


class DashboardFinancieroView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Dashboard KPIs financieros (#70)."""
    template_name = 'construccion/dashboard_financiero.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'dashboard_financiero'
        ctx['totales'] = proyecto.pyg_totales
        ctx['resumen'] = proyecto.pyg_resumen_ejecutivo()
        ctx['alertas'] = [r for r in ctx['resumen'] if r['alerta']]
        return ctx


class FinancieroGridView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Grid editable categoría × período × tipo (#69)."""
    template_name = 'construccion/financiero_grid.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'financiero'
        ctx['categorias'] = CategoriaFinanciera.objects.filter(
            activa=True).order_by('orden')
        ctx['periodos'] = PeriodoFinanciero.objects.filter(
            proyecto=proyecto).order_by('anio', 'mes')
        # Pre-cargar matriz dict[(cat_id, periodo_id, tipo)] = valor
        matriz = {}
        for mov in MovimientoFinanciero.objects.filter(periodo__proyecto=proyecto):
            matriz[(mov.categoria_id, mov.periodo_id, mov.tipo)] = mov.valor
        ctx['matriz'] = matriz
        return ctx


class PeriodoFinancieroCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    """Crea un nuevo período financiero (mes × año) del proyecto."""
    model = PeriodoFinanciero
    template_name = 'construccion/periodo_form.html'
    fields = ['anio', 'mes']
    allowed_roles = ALL_ADMIN_ROLES

    def form_valid(self, form):
        form.instance.proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('construccion:financiero_grid',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = get_object_or_404(ProyectoConstruccion,
                                            id=self.kwargs['proyecto_id'])
        ctx['active_tab'] = 'financiero'
        return ctx


class MovimientoFinancieroSaveView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """POST endpoint para guardar un movimiento (celda) vía HTMX/AJAX."""
    allowed_roles = ALL_ADMIN_ROLES

    def post(self, request, *args, **kwargs):
        from decimal import Decimal, InvalidOperation
        from django.http import JsonResponse
        try:
            categoria_id = request.POST['categoria_id']
            periodo_id = request.POST['periodo_id']
            tipo = request.POST['tipo']
            valor = Decimal(request.POST.get('valor', '0') or '0')
        except (KeyError, InvalidOperation):
            return JsonResponse({'ok': False, 'error': 'bad params'}, status=400)
        if tipo not in ('PRESUPUESTO', 'REAL'):
            return JsonResponse({'ok': False, 'error': 'bad tipo'}, status=400)
        MovimientoFinanciero.objects.update_or_create(
            categoria_id=categoria_id,
            periodo_id=periodo_id,
            tipo=tipo,
            defaults={'valor': valor, 'usuario': request.user},
        )
        return JsonResponse({'ok': True, 'valor': str(valor)})


class CilindrosPendientesView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Listado de patas con cilindros pendientes / próximos (#55)."""
    template_name = 'construccion/cilindros_pendientes.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        patas = PataObra.objects.filter(
            torre__proyecto=proyecto, vaciado_fecha__isnull=False
        ).select_related('torre')
        pendientes = []
        proximos = []
        for p in patas:
            if p.cilindros_pendientes:
                pendientes.append({'pata': p, 'dias': p.cilindros_pendientes})
            if p.cilindros_proximos:
                proximos.append({'pata': p, 'proximos': p.cilindros_proximos})
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'cilindros'
        ctx['pendientes'] = pendientes
        ctx['proximos'] = proximos
        return ctx
