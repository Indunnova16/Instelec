"""
Views for the construccion (construction) app.
"""
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Q

from apps.core.mixins import RoleRequiredMixin, SubModuloRequiredMixin
from apps.contratos.models import Contrato
from .forms import (
    ContratoForm, PataObraForm, FaseTorreMontajeForm, FaseTorreTendidoForm,
    SocialPredialForm, AmbientalTorreForm,
)
from django.http import HttpResponseRedirect
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
    """List towers in a construction project. Si user es operario (#62),
    filtra solo a las torres con cuadrillas asignadas al usuario."""
    model = TorreConstruccion
    template_name = 'construccion/torres_list.html'
    context_object_name = 'torres'
    paginate_by = 50
    # Operario también puede entrar, pero ve queryset filtrado.
    allowed_roles = ['admin', 'director', 'coordinador',
                     'admin_general', 'coordinador_general', 'admin_construccion',
                     'operario_construccion', 'operario_general']

    def get_queryset(self):
        proyecto_id = self.kwargs.get('proyecto_id')
        qs = TorreConstruccion.objects.filter(proyecto_id=proyecto_id)
        qs = filtrar_torres_por_cuadrilla(qs, self.request.user)
        return qs.order_by('numero')

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
    """Lista de torres con semáforo Sociopredial (#51)."""
    template_name = 'construccion/social_predial.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'gestor_social',
                     'admin_general', 'coordinador_general', 'admin_construccion']

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres = TorreConstruccion.objects.filter(proyecto=proyecto).order_by('numero')

        filas = []
        verdes = 0
        for torre in torres:
            social, _ = SocialPredial.objects.get_or_create(torre=torre)
            if social.semaforo == 'VERDE':
                verdes += 1
            filas.append({
                'torre': torre,
                'social': social,
            })
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'social_predial'
        ctx['filas'] = filas
        ctx['stats'] = {
            'total': len(filas),
            'verdes': verdes,
            'rojos': len(filas) - verdes,
        }
        return ctx


class SocialPredialTorreView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Edición de Sociopredial por torre (#51)."""
    model = SocialPredial
    form_class = SocialPredialForm
    template_name = 'construccion/social_predial_torre.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'gestor_social',
                     'admin_general', 'coordinador_general', 'admin_construccion']

    def get_object(self, queryset=None):
        torre = get_object_or_404(
            TorreConstruccion,
            id=self.kwargs['torre_id'],
            proyecto_id=self.kwargs['proyecto_id'],
        )
        social, _ = SocialPredial.objects.get_or_create(torre=torre)
        return social

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        social = self.object
        ctx['proyecto'] = social.torre.proyecto
        ctx['torre'] = social.torre
        ctx['social'] = social
        ctx['active_tab'] = 'social_predial'
        return ctx

    def get_success_url(self):
        return reverse_lazy('construccion:social_predial_torre',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id'],
                                    'torre_id': self.kwargs['torre_id']}) + '?saved=1'


class AmbientalView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Lista de torres con semáforo Ambiental (#52)."""
    template_name = 'construccion/ambiental.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ambientalista',
                     'admin_general', 'coordinador_general', 'admin_construccion']

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres = TorreConstruccion.objects.filter(proyecto=proyecto).order_by('numero')

        filas = []
        verdes = 0
        for torre in torres:
            amb, _ = AmbientalTorre.objects.get_or_create(torre=torre)
            if amb.semaforo == 'VERDE':
                verdes += 1
            filas.append({
                'torre': torre,
                'ambiental': amb,
            })
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'ambiental'
        ctx['filas'] = filas
        ctx['stats'] = {
            'total': len(filas),
            'verdes': verdes,
            'rojos': len(filas) - verdes,
        }
        return ctx


class AmbientalTorreView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Edición Ambiental por torre (#52)."""
    model = AmbientalTorre
    form_class = AmbientalTorreForm
    template_name = 'construccion/ambiental_torre.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ambientalista',
                     'admin_general', 'coordinador_general', 'admin_construccion']

    def get_object(self, queryset=None):
        torre = get_object_or_404(
            TorreConstruccion,
            id=self.kwargs['torre_id'],
            proyecto_id=self.kwargs['proyecto_id'],
        )
        amb, _ = AmbientalTorre.objects.get_or_create(torre=torre)
        return amb

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        amb = self.object
        ctx['proyecto'] = amb.torre.proyecto
        ctx['torre'] = amb.torre
        ctx['ambiental'] = amb
        ctx['active_tab'] = 'ambiental'
        return ctx

    def get_success_url(self):
        return reverse_lazy('construccion:ambiental_torre',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id'],
                                    'torre_id': self.kwargs['torre_id']}) + '?saved=1'


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


# Roles operario que ven solo SUS torres (por cuadrilla asignada) — #62
OPERARIO_ROLES = [
    'operario_construccion', 'operario_general',
    'supervisor', 'liniero', 'auxiliar',
]


def filtrar_torres_por_cuadrilla(qs, user):
    """Si el user es operario (RBAC v2 o legacy), filtra `qs` (TorreConstruccion
    queryset) para que solo aparezcan las torres con alguna pata o fase
    asignada a alguna de sus cuadrillas activas. Admin / superuser → sin filtro.
    Helper de #62.
    """
    if user.is_superuser:
        return qs
    if not getattr(user, 'es_operario_campo', False):
        return qs
    cuadrillas = user.cuadrillas_activas
    if not cuadrillas:
        return qs.none()
    # cuadrilla_civil + cuadrilla_montaje son CharField (legacy); en MVP filtramos
    # solo por nombre exacto si las cuadrillas activas matchean.
    from apps.cuadrillas.models import Cuadrilla
    nombres = list(Cuadrilla.objects.filter(id__in=cuadrillas).values_list('nombre', flat=True))
    return qs.filter(
        Q(pata_obra__cuadrilla_civil__in=nombres) |
        Q(fase__cuadrilla_montaje__in=nombres) |
        Q(fase__cuadrilla_tendido__in=nombres) |
        Q(fase__cuadrilla_prearmado__in=nombres)
    ).distinct()


class ObraProteccionListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Listado de obras de protección (#59) por proyecto."""
    template_name = 'construccion/protecciones_lista.html'
    context_object_name = 'protecciones'
    allowed_roles = ALL_ADMIN_ROLES

    def get_queryset(self):
        qs = ObraProteccion.objects.filter(
            torre__proyecto_id=self.kwargs['proyecto_id']
        ).select_related('torre', 'cuadrilla')
        user = self.request.user
        # #62: operario solo ve obras de torres con sus cuadrillas
        if getattr(user, 'es_operario_campo', False) and not user.is_superuser:
            torres_user = filtrar_torres_por_cuadrilla(
                TorreConstruccion.objects.filter(proyecto_id=self.kwargs['proyecto_id']),
                user,
            )
            qs = qs.filter(torre__in=torres_user)
        return qs.order_by('torre__numero')

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
        ctx['curva_s_fin'] = proyecto.curva_s_financiera()
        return ctx


class FinancieroGridView(LoginRequiredMixin, RoleRequiredMixin, SubModuloRequiredMixin, TemplateView):
    """Grid editable categoría × período × tipo (#69). Solo FINANCIERO (#62 iter 2)."""
    template_name = 'construccion/financiero_grid.html'
    allowed_roles = ALL_ADMIN_ROLES
    required_submodulo = 'FINANCIERO'

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
        from .signals import PresupuestoBloqueadoError
        try:
            categoria_id = request.POST['categoria_id']
            periodo_id = request.POST['periodo_id']
            tipo = request.POST['tipo']
            valor = Decimal(request.POST.get('valor', '0') or '0')
        except (KeyError, InvalidOperation):
            return JsonResponse({'ok': False, 'error': 'bad params'}, status=400)
        if tipo not in ('PRESUPUESTO', 'REAL'):
            return JsonResponse({'ok': False, 'error': 'bad tipo'}, status=400)

        override = (
            request.POST.get('override') == '1'
            and getattr(request.user, 'is_superuser', False)
        )
        try:
            obj, _ = MovimientoFinanciero.objects.get_or_create(
                categoria_id=categoria_id,
                periodo_id=periodo_id,
                tipo=tipo,
                defaults={'valor': valor, 'usuario': request.user},
            )
            # Update path (if existing) — pre_save signal puede rechazar
            if obj.valor != valor:
                obj.valor = valor
                obj.usuario = request.user
                if override:
                    obj._override_presupuesto = True
                obj.save()
        except PresupuestoBloqueadoError as e:
            return JsonResponse({'ok': False, 'error': str(e),
                                 'blocked': True}, status=409)
        return JsonResponse({'ok': True, 'valor': str(valor)})


class CategoriaDrilldownView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Drill-down de una categoría financiera del proyecto (#70 iter 2):
    movimientos PRESUPUESTO/REAL por período + transacciones contables."""
    template_name = 'construccion/categoria_drilldown.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        cat = get_object_or_404(CategoriaFinanciera,
                                id=self.kwargs['categoria_id'])
        movs = MovimientoFinanciero.objects.filter(
            periodo__proyecto=proyecto, categoria=cat
        ).select_related('periodo', 'usuario').order_by('periodo__anio', 'periodo__mes', 'tipo')
        ctx['proyecto'] = proyecto
        ctx['categoria'] = cat
        ctx['movimientos'] = movs
        ctx['active_tab'] = 'financiero'
        # Suma transacciones contables si hay
        from decimal import Decimal
        total_trans = Decimal('0')
        n_trans = 0
        for m in movs:
            n_trans += m.transacciones.count()
            for t in m.transacciones.all():
                total_trans += t.valor
        ctx['total_transacciones'] = total_trans
        ctx['n_transacciones'] = n_trans
        return ctx


class DashboardKitsView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Dashboard agregado de kits (#65 iter 2): inventario + alertas + histórico."""
    template_name = 'construccion/dashboard_kits.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        from .models import MovimientoKit
        kits = KitCerramiento.objects.filter(proyecto=proyecto).select_related('torre_actual')
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'kits'
        ctx['stats'] = {
            'total': kits.count(),
            'disponibles': kits.filter(estado='DISPONIBLE').count(),
            'en_uso': kits.filter(estado='EN_USO').count(),
            'danados': kits.filter(estado='DAÑADO').count(),
            'perdidos': kits.filter(estado='PERDIDO').count(),
            'demora': sum(1 for k in kits if k.alerta_demora),
        }
        ctx['movimientos_recientes'] = MovimientoKit.objects.filter(
            kit__proyecto=proyecto
        ).select_related('kit', 'torre_origen', 'torre_destino').order_by('-fecha')[:20]
        return ctx


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
        user = self.request.user
        # #62: operario solo ve cilindros de torres con sus cuadrillas
        if getattr(user, 'es_operario_campo', False) and not user.is_superuser:
            torres_user = filtrar_torres_por_cuadrilla(
                TorreConstruccion.objects.filter(proyecto=proyecto), user)
            patas = patas.filter(torre__in=torres_user)
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


# =========================================================================
# Obra Civil — Lista de torres + detalle 4 patas con 6 bloques (#53 #54 #55)
# =========================================================================

def _ensure_torre_relaciones(torre):
    """Defensa para torres legacy creadas sin pasar por TorreCreateView:
    asegura 4 PataObra + FaseTorre. Idempotente."""
    for pata in ['A', 'B', 'C', 'D']:
        PataObra.objects.get_or_create(torre=torre, pata=pata)
    FaseTorre.objects.get_or_create(torre=torre, proyecto=torre.proyecto)


class ObraCivilListView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Lista torres del proyecto con su estado de Obra Civil agregado por pata."""
    template_name = 'construccion/obra_civil_lista.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        torres_qs = torres_qs.prefetch_related('pata_obra').order_by('numero')

        filas = []
        total_alarma = 0
        total_completas = 0
        for torre in torres_qs:
            _ensure_torre_relaciones(torre)
            patas = list(torre.pata_obra.all())
            avance = round(sum(p.porcentaje_completado for p in patas) / 4, 1) if patas else 0
            alarma_mat = any(p.alarma_materiales for p in patas)
            cilindros_pend = sum(len(p.cilindros_pendientes) for p in patas)
            bloque_actual = next((p.bloque_actual for p in patas if p.bloque_actual), 'COMPLETA')
            completa = torre.obra_civil_completa
            if alarma_mat:
                total_alarma += 1
            if completa:
                total_completas += 1
            filas.append({
                'torre': torre,
                'avance': avance,
                'bloque_actual': bloque_actual,
                'alarma_materiales': alarma_mat,
                'cilindros_pendientes': cilindros_pend,
                'completa': completa,
                'puede_iniciar': torre.puede_iniciar_obra_civil,
            })

        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'obra_civil'
        ctx['filas'] = filas
        ctx['stats'] = {
            'total': len(filas),
            'completas': total_completas,
            'alarma': total_alarma,
            'pendientes': len(filas) - total_completas,
        }
        return ctx


class ObraCivilTorreView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Detalle de una torre con sus 4 patas + 6 bloques OC editables.

    POST acepta `pata` (A|B|C|D) para guardar solo esa pata."""
    template_name = 'construccion/obra_civil_torre.html'
    allowed_roles = ALL_ADMIN_ROLES

    def _get_torre(self):
        return get_object_or_404(
            TorreConstruccion,
            id=self.kwargs['torre_id'],
            proyecto_id=self.kwargs['proyecto_id'],
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        torre = self._get_torre()
        _ensure_torre_relaciones(torre)
        patas = list(torre.pata_obra.order_by('pata'))
        active_pata = kwargs.get('active_pata') or self.request.GET.get('pata') or 'A'
        if active_pata not in ['A', 'B', 'C', 'D']:
            active_pata = 'A'
        pata_actual = next((p for p in patas if p.pata == active_pata), patas[0] if patas else None)
        form_override = kwargs.get('form_override')
        form_actual = form_override or PataObraForm(instance=pata_actual,
                                                    prefix=f'pata_{active_pata}')
        ctx['proyecto'] = torre.proyecto
        ctx['torre'] = torre
        ctx['patas'] = patas
        ctx['pata_actual'] = pata_actual
        ctx['form'] = form_actual
        ctx['active_tab'] = 'obra_civil'
        ctx['active_pata'] = active_pata
        return ctx

    def post(self, request, *args, **kwargs):
        torre = self._get_torre()
        _ensure_torre_relaciones(torre)
        pata_letra = request.POST.get('pata') or request.GET.get('pata') or 'A'
        if pata_letra not in ['A', 'B', 'C', 'D']:
            pata_letra = 'A'
        try:
            pata = torre.pata_obra.get(pata=pata_letra)
        except PataObra.DoesNotExist:
            pata = PataObra.objects.create(torre=torre, pata=pata_letra)
        form = PataObraForm(request.POST, instance=pata, prefix=f'pata_{pata_letra}')
        if form.is_valid():
            form.save()
            url = reverse_lazy('construccion:obra_civil_torre',
                               kwargs={'proyecto_id': torre.proyecto.id,
                                       'torre_id': torre.id})
            return HttpResponseRedirect(f'{url}?pata={pata_letra}&saved=1')
        ctx = self.get_context_data(
            form_override=form,
            active_pata=pata_letra,
        )
        return self.render_to_response(ctx)


# =========================================================================
# Montaje — Lista de torres + edición FaseTorre (Montaje+SPT+Pintura) (#56 #57)
# =========================================================================

class MontajeListView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Lista torres con KPI de Montaje."""
    template_name = 'construccion/montaje_lista.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        torres_qs = torres_qs.select_related('fase').order_by('numero')

        filas = []
        listas_para_tendido = 0
        oc_completas = 0
        for torre in torres_qs:
            _ensure_torre_relaciones(torre)
            torre.refresh_from_db()
            fase = torre.fase
            if torre.obra_civil_completa:
                oc_completas += 1
            if fase.entrega_carga_ok:
                listas_para_tendido += 1
            filas.append({
                'torre': torre,
                'fase': fase,
                'puede_iniciar': torre.puede_iniciar_montaje,
                'oc_completa': torre.obra_civil_completa,
            })
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'montaje'
        ctx['filas'] = filas
        ctx['stats'] = {
            'total': len(filas),
            'oc_completas': oc_completas,
            'pendientes': len(filas) - oc_completas,
            'listas_tendido': listas_para_tendido,
        }
        return ctx


class MontajeTorreView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Edición de FaseTorre (sección Montaje + SPT + Pintura)."""
    model = FaseTorre
    form_class = FaseTorreMontajeForm
    template_name = 'construccion/montaje_torre.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_object(self, queryset=None):
        torre = get_object_or_404(
            TorreConstruccion,
            id=self.kwargs['torre_id'],
            proyecto_id=self.kwargs['proyecto_id'],
        )
        _ensure_torre_relaciones(torre)
        return torre.fase

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fase = self.object
        ctx['proyecto'] = fase.torre.proyecto
        ctx['torre'] = fase.torre
        ctx['fase'] = fase
        ctx['active_tab'] = 'montaje'
        return ctx

    def get_success_url(self):
        return reverse_lazy('construccion:montaje_torre',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id'],
                                    'torre_id': self.kwargs['torre_id']}) + '?saved=1'


# =========================================================================
# Tendido — Lista de torres + edición FaseTorre (sección Tendido) (#58)
# =========================================================================

class TendidoListView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Lista torres con KPI de Tendido."""
    template_name = 'construccion/tendido_lista.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        torres_qs = torres_qs.select_related('fase').order_by('numero')

        filas = []
        habilitadas = 0
        completas = 0
        for torre in torres_qs:
            _ensure_torre_relaciones(torre)
            torre.refresh_from_db()
            fase = torre.fase
            puede = fase.puede_iniciar_tendido
            if puede:
                habilitadas += 1
            if fase.porcentaje_tendido >= 100:
                completas += 1
            filas.append({
                'torre': torre,
                'fase': fase,
                'puede_iniciar': puede,
            })
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'tendido'
        ctx['filas'] = filas
        ctx['stats'] = {
            'total': len(filas),
            'habilitadas': habilitadas,
            'bloqueadas': len(filas) - habilitadas,
            'completas': completas,
        }
        return ctx


class TendidoTorreView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Edición de FaseTorre (sección Tendido)."""
    model = FaseTorre
    form_class = FaseTorreTendidoForm
    template_name = 'construccion/tendido_torre.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_object(self, queryset=None):
        torre = get_object_or_404(
            TorreConstruccion,
            id=self.kwargs['torre_id'],
            proyecto_id=self.kwargs['proyecto_id'],
        )
        _ensure_torre_relaciones(torre)
        return torre.fase

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fase = self.object
        ctx['proyecto'] = fase.torre.proyecto
        ctx['torre'] = fase.torre
        ctx['fase'] = fase
        ctx['active_tab'] = 'tendido'
        ctx['bloqueada'] = not fase.puede_iniciar_tendido
        return ctx

    def get_success_url(self):
        return reverse_lazy('construccion:tendido_torre',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id'],
                                    'torre_id': self.kwargs['torre_id']}) + '?saved=1'
