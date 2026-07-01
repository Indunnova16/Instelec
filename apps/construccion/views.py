"""
Views for the construccion (construction) app.
"""
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Q, IntegerField, Value, F, Func
from django.db.models.functions import Cast, NullIf

from apps.core.mixins import RoleRequiredMixin, SubModuloRequiredMixin
from apps.contratos.models import Contrato


def ordenar_torres_construccion(qs, incluir_no_aplica=False):
    """Orden numérico ascendente por la parte numérica de ``numero`` (#100:
    evita T-1, T-10, T-2). Formatos sin número quedan al final.

    #160: por defecto EXCLUYE las torres marcadas "No aplica" (``aplica=False``)
    para que no aparezcan en módulos/dashboards ni cuenten en el avance. La matriz
    de Obra Civil (donde se gestiona el flag) pasa ``incluir_no_aplica=True`` para
    poder ver y re-activar esas torres.
    """
    if not incluir_no_aplica:
        qs = qs.filter(aplica=True)
    return qs.annotate(
        _solo_digitos=Func(
            F('numero'), Value(r'[^0-9]'), Value(''), Value('g'),
            function='regexp_replace',
        ),
    ).annotate(
        _num_ord=Cast(NullIf(F('_solo_digitos'), Value('')), IntegerField()),
    ).order_by(F('_num_ord').asc(nulls_last=True), 'numero')
from .forms import (
    ContratoForm, PataObraForm, FaseTorreMontajeForm, FaseTorreTendidoForm,
    SocialPredialForm, AmbientalTorreForm, ObraCivilFechasForm,
    RiegaManilaTiroFormSet,
)
from django.http import HttpResponseRedirect
from .models import (
    ProyectoConstruccion,
    TorreConstruccion,
    PataObra,
    ObraCivilTorre,
    MontajeEstructuraTorre,
    SPTTorre,
    PinturaPatasTorre,
    PinturaAeronauticaTorre,
    PinturaFranja,
    TendidoTorre,
    TrinchoCuneta,
    DashboardAvanceSemanal,
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
        return ordenar_torres_construccion(qs)

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
        torres = ordenar_torres_construccion(TorreConstruccion.objects.filter(proyecto=proyecto))

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
        torres = ordenar_torres_construccion(TorreConstruccion.objects.filter(proyecto=proyecto))

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
        torres = ordenar_torres_construccion(TorreConstruccion.objects.filter(proyecto=proyecto))

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

    def form_valid(self, form):
        """Además del contrato, persistir lat/lng del proyecto (#155 sub-5).

        Permite que el cliente cargue la ubicación del proyecto desde esta misma
        pantalla; el mapa de /cuadrillas/ la usa. Coordenadas vacías → se borran
        (null) sin romper. Valores no numéricos se ignoran (no 500).
        """
        from decimal import Decimal, InvalidOperation

        response = super().form_valid(form)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id']
        )

        def _parse_coord(raw):
            raw = (raw or '').strip()
            if raw == '':
                return None, True  # vacío → null válido
            try:
                return Decimal(raw), True
            except (InvalidOperation, ValueError):
                return None, False  # inválido → no tocar

        lat, lat_ok = _parse_coord(self.request.POST.get('proyecto_latitud'))
        lng, lng_ok = _parse_coord(self.request.POST.get('proyecto_longitud'))

        changed = False
        if lat_ok and 'proyecto_latitud' in self.request.POST:
            proyecto.latitud = lat
            changed = True
        if lng_ok and 'proyecto_longitud' in self.request.POST:
            proyecto.longitud = lng
            changed = True
        if changed:
            proyecto.save(update_fields=['latitud', 'longitud', 'updated_at'])
        return response

    def get_success_url(self):
        return reverse_lazy('construccion:contrato', kwargs={'proyecto_id': self.kwargs['proyecto_id']})


class IngenieriaView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Redirige al módulo Ingeniería (apps.ingenieria) usando el contrato del
    proyecto. El módulo nuevo (#50) opera por contrato con checklist
    Civil/Montaje/Tendido. Aterrizamos en Civil por defecto; el usuario navega
    sub-tabs dentro de tabla.html."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente',
                     'admin_general', 'coordinador_general', 'admin_construccion']

    def get(self, request, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        return redirect('ingenieria:civil', contrato_id=proyecto.contrato_id)


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
        torres_qs = ordenar_torres_construccion(torres_qs.prefetch_related('pata_obra'))

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
        torres_qs = ordenar_torres_construccion(torres_qs.select_related('fase'))

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
        torres_qs = ordenar_torres_construccion(torres_qs.select_related('fase'))

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
        # #147 item 10: formset inline de tiros de riega de manila + F.T.
        if 'tiros_formset' not in ctx:
            if self.request.method == 'POST':
                ctx['tiros_formset'] = RiegaManilaTiroFormSet(
                    self.request.POST, instance=fase)
            else:
                ctx['tiros_formset'] = RiegaManilaTiroFormSet(instance=fase)
        return ctx

    def form_valid(self, form):
        # #147 item 10: validar el formset de tiros ANTES de guardar nada.
        tiros_formset = RiegaManilaTiroFormSet(
            self.request.POST, instance=form.instance)
        if not tiros_formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, tiros_formset=tiros_formset))

        response = super().form_valid(form)

        # #147: las limpiezas se aplican DESPUÉS de super().form_valid() (que llama
        # form.save() y re-aplica cleaned_data). Como los campos C2/protecciones SÍ
        # están en el form, hacerlas antes las sobrescribía form.save() → regresión
        # (Circuito 2 "No aplica" no limpiaba sus 6 campos). Se guardan con
        # update_fields para que la limpieza gane.
        cambios = []
        if form.cleaned_data.get('circuito_2_aplica') is False:
            self.object.tendido_conductor_c2_a_ok = False
            self.object.tendido_conductor_c2_b_ok = False
            self.object.tendido_conductor_c2_c_ok = False
            self.object.tendido_conductor_c2_a_fecha = None
            self.object.tendido_conductor_c2_b_fecha = None
            self.object.tendido_conductor_c2_c_fecha = None
            # #147 item 11: si C2 no aplica, limpiar también su regulación/flechado.
            self.object.regulacion_flechado_c2_ok = False
            self.object.regulacion_flechado_c2_fecha = None
            cambios += [
                'tendido_conductor_c2_a_ok', 'tendido_conductor_c2_b_ok',
                'tendido_conductor_c2_c_ok', 'tendido_conductor_c2_a_fecha',
                'tendido_conductor_c2_b_fecha', 'tendido_conductor_c2_c_fecha',
                'regulacion_flechado_c2_ok', 'regulacion_flechado_c2_fecha',
            ]

        # #147 item 9: "No aplica" gana sobre "instaladas" (mutuamente excluyentes).
        if form.cleaned_data.get('protecciones_no_aplica') is True:
            self.object.protecciones_ok = False
            self.object.protecciones_fecha = None
            cambios += ['protecciones_ok', 'protecciones_fecha']

        if cambios:
            self.object.save(update_fields=cambios)

        # numero_tiro autoasignado (max+1) para filas nuevas que lo dejaron vacío.
        tiros_formset.instance = self.object
        instancias = tiros_formset.save(commit=False)
        existentes = list(
            self.object.tiros_manila.values_list('numero_tiro', flat=True))
        siguiente = (max(existentes) + 1) if existentes else 1
        for obj in tiros_formset.deleted_objects:
            obj.delete()
        for tiro in instancias:
            if not tiro.numero_tiro:
                tiro.numero_tiro = siguiente
                siguiente += 1
            else:
                siguiente = max(siguiente, tiro.numero_tiro + 1)
            tiro.save()
        tiros_formset.save_m2m()
        return response

    def get_success_url(self):
        return reverse_lazy('construccion:tendido_torre',
                            kwargs={'proyecto_id': self.kwargs['proyecto_id'],
                                    'torre_id': self.kwargs['torre_id']}) + '?saved=1'


# ==========================================================================
# Obra Civil — matriz torre × columna (#74)
# ==========================================================================

class ObraCivilMatrizView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Matriz Obra Civil del proyecto: torres × 6 columnas (Cerramiento,
    Excavación, Solado, Acero, Vaciado, Compactación) con avance ponderado
    SUMPRODUCT por torre. Cada celda es editable inline (0-100%).

    Reemplaza la vista ObraCivilListView legacy para el cliente. La
    granularidad pata×actividad sigue accesible vía ObraCivilTorreView
    (modelo PataObra) para uso interno.
    """
    template_name = 'construccion/obra_civil_matriz.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        # #160: la matriz de Obra Civil muestra TODAS las torres (incl. "No aplica")
        # para poder marcarlas/re-activarlas; el resto de módulos las excluye.
        torres_qs = ordenar_torres_construccion(torres_qs.select_related(), incluir_no_aplica=True)

        # Asegurar OC para cada torre (crear si no existe — idempotente).
        existentes = {oc.torre_id: oc for oc in ObraCivilTorre.objects.filter(proyecto=proyecto)}
        filas = []
        for torre in torres_qs:
            oc = existentes.get(torre.id)
            if oc is None:
                oc = ObraCivilTorre.objects.create(proyecto=proyecto, torre=torre)
            filas.append(oc)

        pesos = {
            'cerramiento': proyecto.peso_cerramiento_pct,
            'excavacion': proyecto.peso_excavacion_pct,
            'solado': proyecto.peso_solado_pct,
            'acero': proyecto.peso_acero_pct,
            'vaciado': proyecto.peso_vaciado_pct,
            'compactacion': proyecto.peso_compactacion_pct,
        }
        suma_pesos = sum(pesos.values())

        # Totales por columna (promedio entre torres). #150: excluir las torres
        # "No aplica" del denominador del avance por columna (la tabla las sigue
        # mostrando para gestionarlas, pero no cuentan en el %). Montaje y Tendido
        # ya aplican este filtro; Obra Civil quedaba dividiendo sobre todas.
        filas_activas = [f for f in filas if f.torre.aplica]
        if filas_activas:
            totales = {
                k: round(
                    sum(float(getattr(oc, f'avance_{k}')) for oc in filas_activas)
                    / len(filas_activas) * 100, 1)
                for k in pesos
            }
            avance_general = round(
                sum(float(oc.avance_ponderado) for oc in filas_activas)
                / len(filas_activas) * 100, 1
            )
        else:
            totales = {k: 0 for k in pesos}
            avance_general = 0

        ctx['proyecto'] = proyecto
        ctx['filas'] = filas
        ctx['pesos'] = pesos
        ctx['suma_pesos'] = suma_pesos
        ctx['suma_pesos_ok'] = suma_pesos == 100
        ctx['totales'] = totales
        ctx['avance_general'] = avance_general
        ctx['columnas'] = ObraCivilTorre.COLUMNAS
        ctx['active_tab'] = 'obra-civil'
        return ctx


class ObraCivilPesosUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX para actualizar los 6 pesos del proyecto (#74).

    Valida que la suma sea exactamente 100; devuelve 400 si no.
    """
    allowed_roles = ALL_ADMIN_ROLES

    def post(self, request, proyecto_id, *args, **kwargs):
        from django.http import JsonResponse
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        try:
            valores = {
                'peso_cerramiento_pct': int(request.POST.get('cerramiento', 0)),
                'peso_excavacion_pct': int(request.POST.get('excavacion', 0)),
                'peso_solado_pct': int(request.POST.get('solado', 0)),
                'peso_acero_pct': int(request.POST.get('acero', 0)),
                'peso_vaciado_pct': int(request.POST.get('vaciado', 0)),
                'peso_compactacion_pct': int(request.POST.get('compactacion', 0)),
            }
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Los pesos deben ser enteros 0-100.'}, status=400)

        for k, v in valores.items():
            if v < 0 or v > 100:
                return JsonResponse({'error': f'Peso fuera de rango: {k}={v}'}, status=400)
        if sum(valores.values()) != 100:
            return JsonResponse(
                {'error': f'La suma de pesos debe ser 100 (actual: {sum(valores.values())}).'},
                status=400)

        for campo, valor in valores.items():
            setattr(proyecto, campo, valor)
        proyecto.save(update_fields=list(valores.keys()))
        return JsonResponse({'ok': True, 'suma': sum(valores.values())})


class ObraCivilFechasUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX para actualizar las 3 fechas de seguimiento de una torre (#156).

    Espeja ObraCivilPesosUpdateView: valida con ObraCivilFechasForm
    (DateInput format='%Y-%m-%d') y devuelve JsonResponse.
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        from django.http import JsonResponse
        oc = get_object_or_404(
            ObraCivilTorre, proyecto_id=proyecto_id, torre_id=torre_id)
        form = ObraCivilFechasForm(request.POST, instance=oc)
        if not form.is_valid():
            return JsonResponse({'error': 'Fechas inválidas.',
                                 'detail': form.errors}, status=400)
        form.save()
        return JsonResponse({
            'ok': True,
            'alerta_retraso': oc.alerta_retraso,
        })


class ObraCivilAplicaUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX genérico — actualiza un flag de aplicabilidad de una torre.

    Espeja ObraCivilFechasUpdateView (View.post(proyecto_id, torre_id) ->
    get_object_or_404(ObraCivilTorre) -> save -> JsonResponse). Acepta un
    campo whitelisteado y su valor booleano. Sirve a #153
    (aplica_pintura_aeronautica) y al flag global #160 (torre.aplica) con un
    solo endpoint para no duplicar mecanismos de guardado.

    #149 (bounce=5): se eliminó `aplica_obras_proteccion` del whitelist; el
    frontend ya no envía ese campo (checkbox removido). La columna BD queda
    dormida (reversible, sin migración).
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES
    CAMPOS_PERMITIDOS = {'aplica_pintura_aeronautica'}

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        from django.http import JsonResponse
        campo = request.POST.get('campo', '').strip()
        valor = request.POST.get('aplica', '').strip().lower() in ('1', 'true', 'on')
        # #160: flag GLOBAL "torre aplica al proyecto" vive en TorreConstruccion
        # (no en ObraCivilTorre) para excluirla de todo sin el bug INNER JOIN.
        if campo == 'aplica':
            torre = get_object_or_404(
                TorreConstruccion, proyecto_id=proyecto_id, id=torre_id)
            torre.aplica = valor
            torre.save(update_fields=['aplica'])
            return JsonResponse({'ok': True, 'campo': campo, 'valor': valor})
        if campo not in self.CAMPOS_PERMITIDOS:
            return JsonResponse(
                {'error': f'Campo no permitido: {campo!r}'}, status=400)
        oc = get_object_or_404(
            ObraCivilTorre, proyecto_id=proyecto_id, torre_id=torre_id)
        setattr(oc, campo, valor)
        oc.save(update_fields=[campo, 'updated_at'])
        return JsonResponse({'ok': True, 'campo': campo, 'valor': valor})


class ObraCivilAvanceUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """410 Gone — endpoint reemplazado por edición detallada por sección.

    Reemplazado por ObraCivilDetalleSeccionView (B2b, paridad campo-a-campo Excel).
    Cliente debe editar en /construccion/<p>/obra-civil/<t>/detalle/?pata=X&seccion=Y/.
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        from django.http import JsonResponse
        return JsonResponse({
            'error': 'gone',
            'detail': 'Este endpoint fue reemplazado por el editor detallado por sección. '
                      'Editá en /construccion/<proyecto>/obra-civil/<torre>/detalle/?pata=A&seccion=cerramiento.',
        }, status=410)


# ==========================================================================
# Montaje — matriz torre × etapa CANT MONTAJE (#76)
# ==========================================================================

class MontajeMatrizView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Matriz CANT MONTAJE: torres × 4 etapas (Estructura en sitio, Prearmada,
    Torre montada, Revisada) con SUMPRODUCT por torre.
    """
    template_name = 'construccion/montaje_matriz.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion,
                                     id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        # #150/#160: listar TODAS las torres (incl. "No aplica") para poder
        # verlas/marcarlas desde Montaje; el avance abajo solo cuenta las activas.
        torres_qs = ordenar_torres_construccion(torres_qs.select_related(), incluir_no_aplica=True)

        existentes = {m.torre_id: m for m in
                      MontajeEstructuraTorre.objects.filter(proyecto=proyecto)}
        filas = []
        for torre in torres_qs:
            m = existentes.get(torre.id)
            if m is None:
                m = MontajeEstructuraTorre.objects.create(proyecto=proyecto, torre=torre)
            filas.append(m)

        pesos = {
            'estructura_sitio': proyecto.peso_mont_estructura_sitio_pct,
            'prearamada': proyecto.peso_mont_prearamada_pct,
            'torre_montada': proyecto.peso_mont_torre_montada_pct,
            'revisada': proyecto.peso_mont_revisada_pct,
        }
        suma_pesos = sum(pesos.values())

        # #150: el promedio cuenta SOLO las torres que aplican (display=todas,
        # conteo=solo aplica=True) para que una torre "No aplica" no baje el %.
        filas_activas = [f for f in filas if f.torre.aplica]
        if filas_activas:
            totales = {
                k: round(
                    sum(float(getattr(m, f'avance_{k}')) for m in filas_activas)
                    / len(filas_activas) * 100, 1)
                for k in pesos
            }
            avance_general = round(
                sum(float(m.avance_ponderado) for m in filas_activas)
                / len(filas_activas) * 100, 1
            )
        else:
            totales = {k: 0 for k in pesos}
            avance_general = 0

        ctx['proyecto'] = proyecto
        ctx['filas'] = filas
        ctx['pesos'] = pesos
        ctx['suma_pesos'] = suma_pesos
        ctx['suma_pesos_ok'] = suma_pesos == 100
        ctx['totales'] = totales
        ctx['avance_general'] = avance_general
        ctx['columnas'] = MontajeEstructuraTorre.COLUMNAS
        ctx['active_tab'] = 'montaje'
        return ctx


class MontajePesosUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — actualiza los 4 pesos de Montaje del proyecto."""
    allowed_roles = ALL_ADMIN_ROLES

    def post(self, request, proyecto_id, *args, **kwargs):
        from django.http import JsonResponse
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        try:
            valores = {
                'peso_mont_estructura_sitio_pct': int(request.POST.get('estructura_sitio', 0)),
                'peso_mont_prearamada_pct': int(request.POST.get('prearamada', 0)),
                'peso_mont_torre_montada_pct': int(request.POST.get('torre_montada', 0)),
                'peso_mont_revisada_pct': int(request.POST.get('revisada', 0)),
            }
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Los pesos deben ser enteros 0-100.'}, status=400)
        for k, v in valores.items():
            if v < 0 or v > 100:
                return JsonResponse({'error': f'Peso fuera de rango: {k}={v}'}, status=400)
        if sum(valores.values()) != 100:
            return JsonResponse(
                {'error': f'La suma de pesos debe ser 100 (actual: {sum(valores.values())}).'},
                status=400)
        for campo, valor in valores.items():
            setattr(proyecto, campo, valor)
        proyecto.save(update_fields=list(valores.keys()))
        return JsonResponse({'ok': True})


class MontajeAvanceUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """410 Gone — endpoint reemplazado por edición detallada por sección.

    Reemplazado por MontajeDetalleSaveView (B3b, paridad campo-a-campo Excel).
    Cliente debe editar en /construccion/<p>/montaje/<t>/detalle/?seccion=Y/.
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        from django.http import JsonResponse
        return JsonResponse({
            'error': 'gone',
            'detail': 'Este endpoint fue reemplazado por el editor detallado por sección. '
                      'Editá en /construccion/<proyecto>/montaje/<torre>/detalle/?seccion=montaje.',
        }, status=410)


# ==========================================================================
# SPT y Pintura (#78) — captura por torre del Excel `SPT PINTURA.xlsx`
# ==========================================================================

SPT_FIELDS_NUMERICOS = [
    'excavacion_m', 'cable_planos_m', 'cable_instalado_m',
    'cantidad_tiros', 'polvora_teorica_cajas', 'polvora_real_kg',
    'porcentaje_avance',
]
SPT_FIELDS_TEXTO = ['cuadrilla_spt', 'observaciones_cable', 'observaciones_polvora']
SPT_FIELDS_BOOL = ['control_compensacion', 'control_medicion', 'informe_mediciones']

PINTURA_PATAS_FIELDS_BOOL = ['control_espesor', 'torres_pintadas', 'medicion_espesor', 'entrega_pintura']
PINTURA_PATAS_FIELDS_TEXTO = ['cuadrilla', 'observaciones']

PINTURA_AERO_FIELDS_BOOL = ['revision_espesor_micras', 'entrega_pintura']

FRANJA_FIELDS_NUMERICOS = [
    'porcentaje_base', 'cantidad_base_proyectada', 'cantidad_base_consumida',
    'porcentaje_color', 'cantidad_color_proyectada', 'cantidad_color_consumida',
]
FRANJA_FIELDS_TEXTO = ['observaciones_base', 'observaciones_color']


class SPTPinturaIndexView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Lista de torres del proyecto con su estado SPT / Pintura agregado."""
    template_name = 'construccion/spt_pintura_index.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        # #153: SPT y Pintura de Patas son OBLIGATORIOS para TODAS las torres;
        # solo la subsección "Pintura Aeronáutica" es opcional (se gatea por
        # obra_civil.aplica_pintura_aeronautica en el detalle/template). Por eso
        # el índice muestra todas las torres (no filtramos acá).
        torres_qs = ordenar_torres_construccion(torres_qs.select_related().prefetch_related(
            'spt', 'pintura_patas', 'pintura_aeronautica__franjas',
        ))

        filas = []
        for torre in torres_qs:
            try:
                spt = torre.spt
            except SPTTorre.DoesNotExist:
                spt = None
            try:
                patas = torre.pintura_patas
            except PinturaPatasTorre.DoesNotExist:
                patas = None
            try:
                aero = torre.pintura_aeronautica
                franjas_completas = sum(
                    1 for f in aero.franjas.all()
                    if f.porcentaje_base >= 100 and f.porcentaje_color >= 100
                )
            except PinturaAeronauticaTorre.DoesNotExist:
                aero = None
                franjas_completas = 0
            filas.append({
                'torre': torre,
                'spt_pct': spt.porcentaje_avance if spt else 0,
                'spt_controles': sum(int(getattr(spt, c, False)) for c in SPT_FIELDS_BOOL) if spt else 0,
                'patas_completa': all(getattr(patas, c, False) for c in PINTURA_PATAS_FIELDS_BOOL) if patas else False,
                'aero_franjas_completas': franjas_completas,
            })
        ctx['proyecto'] = proyecto
        ctx['filas'] = filas
        ctx['active_tab'] = 'spt-pintura'
        return ctx


class SPTPinturaTorreView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Detalle SPT + Pintura Patas + Pintura Aeronáutica (7 franjas) para una torre."""
    template_name = 'construccion/spt_pintura_torre.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    # #153: ya NO se redirige cuando la torre no aplica a Pintura Aeronáutica —
    # SPT y Pintura de Patas son obligatorios para todas las torres; solo la
    # subsección Pintura Aeronáutica se oculta en el template si no aplica.

    def _get_or_create_estructuras(self, proyecto, torre):
        spt, _ = SPTTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
        patas, _ = PinturaPatasTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
        # Crear la estructura de Pintura Aeronáutica SOLO si la torre la aplica.
        oc = ObraCivilTorre.objects.filter(proyecto=proyecto, torre=torre).first()
        aplica_aero = oc.aplica_pintura_aeronautica if oc is not None else True
        aero = None
        if aplica_aero:
            aero, _ = PinturaAeronauticaTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
            # Signal post_save crea las 7 franjas si la aero es nueva; defensivo si fallaron.
            for n in range(1, 8):
                color = PinturaFranja.Color.NARANJA if n % 2 == 1 else PinturaFranja.Color.BLANCO
                PinturaFranja.objects.get_or_create(
                    pintura_aeronautica=aero, numero_franja=n,
                    defaults={'color': color},
                )
        return spt, patas, aero

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        torre = get_object_or_404(TorreConstruccion, id=self.kwargs['torre_id'], proyecto=proyecto)
        spt, patas, aero = self._get_or_create_estructuras(proyecto, torre)
        # aero es None si la torre no aplica Pintura Aeronáutica (#153).
        franjas = list(aero.franjas.order_by('numero_franja')) if aero else []
        aplica_aero = aero is not None

        # Navegación prev/next (por orden alfabético de numero)
        torres = list(ordenar_torres_construccion(TorreConstruccion.objects.filter(proyecto=proyecto)))
        idx = next((i for i, t in enumerate(torres) if t.id == torre.id), None)
        prev_t = torres[idx - 1] if idx is not None and idx > 0 else None
        next_t = torres[idx + 1] if idx is not None and idx < len(torres) - 1 else None

        ctx.update({
            'proyecto': proyecto,
            'torre': torre,
            'spt': spt,
            'patas': patas,
            'aero': aero,
            'aplica_aero': aplica_aero,
            'franjas': franjas,
            'prev_torre': prev_t,
            'next_torre': next_t,
            'posicion': (idx + 1) if idx is not None else 0,
            'total_torres': len(torres),
            'active_tab': 'spt-pintura',
        })
        return ctx


class SPTPinturaTorreUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — actualiza una sección de SPT/Pintura para la torre.

    Body: seccion ∈ {spt, patas, aero, franja_<N>}, y los campos a actualizar.
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        from decimal import Decimal, InvalidOperation
        from django.http import JsonResponse
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        torre = get_object_or_404(TorreConstruccion, id=torre_id, proyecto=proyecto)
        seccion = request.POST.get('seccion', '').strip()

        def _set_decimal(obj, field, raw):
            if raw == '' or raw is None:
                setattr(obj, field, None)
                return None
            try:
                v = Decimal(raw)
            except (TypeError, InvalidOperation):
                return f'{field}: valor decimal inválido'
            setattr(obj, field, v)
            return None

        def _set_int(obj, field, raw, lo=None, hi=None):
            if raw == '' or raw is None:
                setattr(obj, field, 0 if field == 'porcentaje_avance' else None)
                return None
            try:
                v = int(raw)
            except (TypeError, ValueError):
                return f'{field}: valor entero inválido'
            if lo is not None and v < lo:
                return f'{field}: debe ser ≥ {lo}'
            if hi is not None and v > hi:
                return f'{field}: debe ser ≤ {hi}'
            setattr(obj, field, v)
            return None

        def _set_bool(obj, field, raw):
            setattr(obj, field, raw in ('1', 'true', 'on', 'True'))

        if seccion == 'spt':
            spt, _ = SPTTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
            for f in ['excavacion_m', 'cable_planos_m', 'cable_instalado_m',
                      'polvora_teorica_cajas', 'polvora_real_kg']:
                if f in request.POST:
                    err = _set_decimal(spt, f, request.POST.get(f, '').strip())
                    if err:
                        return JsonResponse({'error': err}, status=400)
            if 'cantidad_tiros' in request.POST:
                err = _set_int(spt, 'cantidad_tiros', request.POST.get('cantidad_tiros', '').strip())
                if err:
                    return JsonResponse({'error': err}, status=400)
            if 'porcentaje_avance' in request.POST:
                err = _set_int(spt, 'porcentaje_avance', request.POST.get('porcentaje_avance', '0'), 0, 100)
                if err:
                    return JsonResponse({'error': err}, status=400)
            for f in SPT_FIELDS_TEXTO:
                if f in request.POST:
                    setattr(spt, f, request.POST[f])
            for f in SPT_FIELDS_BOOL:
                if f in request.POST:
                    _set_bool(spt, f, request.POST[f])
            spt.save()
            return JsonResponse({
                'ok': True,
                'diferencia_cable': float(spt.diferencia_cable) if spt.diferencia_cable is not None else None,
                'diferencia_polvora': float(spt.diferencia_polvora) if spt.diferencia_polvora is not None else None,
            })

        if seccion == 'patas':
            patas, _ = PinturaPatasTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
            for f in PINTURA_PATAS_FIELDS_BOOL:
                if f in request.POST:
                    _set_bool(patas, f, request.POST[f])
            for f in PINTURA_PATAS_FIELDS_TEXTO:
                if f in request.POST:
                    setattr(patas, f, request.POST[f])
            patas.save()
            return JsonResponse({'ok': True})

        if seccion == 'aero':
            aero, _ = PinturaAeronauticaTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
            for f in PINTURA_AERO_FIELDS_BOOL:
                if f in request.POST:
                    _set_bool(aero, f, request.POST[f])
            aero.save()
            return JsonResponse({'ok': True})

        if seccion.startswith('franja_'):
            try:
                numero = int(seccion.split('_', 1)[1])
            except ValueError:
                return JsonResponse({'error': 'Número de franja inválido'}, status=400)
            if not 1 <= numero <= 7:
                return JsonResponse({'error': 'Franja debe estar entre 1 y 7'}, status=400)
            aero, _ = PinturaAeronauticaTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
            color = PinturaFranja.Color.NARANJA if numero % 2 == 1 else PinturaFranja.Color.BLANCO
            franja, _ = PinturaFranja.objects.get_or_create(
                pintura_aeronautica=aero, numero_franja=numero,
                defaults={'color': color},
            )
            for f in ['porcentaje_base', 'porcentaje_color']:
                if f in request.POST:
                    err = _set_int(franja, f, request.POST.get(f, '0'), 0, 100)
                    if err:
                        return JsonResponse({'error': err}, status=400)
            for f in ['cantidad_base_proyectada', 'cantidad_base_consumida',
                      'cantidad_color_proyectada', 'cantidad_color_consumida']:
                if f in request.POST:
                    err = _set_decimal(franja, f, request.POST.get(f, '').strip())
                    if err:
                        return JsonResponse({'error': err}, status=400)
            for f in FRANJA_FIELDS_TEXTO:
                if f in request.POST:
                    setattr(franja, f, request.POST[f])
            franja.save()
            return JsonResponse({
                'ok': True,
                'diferencia_base': float(franja.diferencia_base) if franja.diferencia_base is not None else None,
                'diferencia_color': float(franja.diferencia_color) if franja.diferencia_color is not None else None,
            })

        return JsonResponse({'error': f'Sección inválida: {seccion!r}'}, status=400)


# ==========================================================================
# CANT TENDIDO (#79) — matriz torre × actividades conductor + fibra OPGW
# ==========================================================================

TENDIDO_CONDUCTOR_FIELDS = {
    'riega_manila_conductor', 'riega_guaya_conductor', 'tendido_conductor',
    'grapado_amarre_conductor', 'accesorios_puentes', 'balizas_desviadores',
}
TENDIDO_FIBRA_FIELDS = {
    'riega_manila_fibra', 'riega_guaya_opgw', 'tendido_opgw',
    'grapado_amarre_fibra', 'empalmes_opgw',
}
TENDIDO_EXTRA_BOOL = {
    'vestida_conductor', 'placas_senalizacion', 'facturadas_hmv',
    'vestida_fibra',
}
TENDIDO_TODOS_BOOL = TENDIDO_CONDUCTOR_FIELDS | TENDIDO_FIBRA_FIELDS | TENDIDO_EXTRA_BOOL


class TendidoMatrizView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Matriz CANT TENDIDO con sección Conductor (7 cols + 2 admin) + Fibra (6 cols)."""
    template_name = 'construccion/tendido_matriz.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        # #150/#160: listar TODAS las torres (incl. "No aplica") para poder
        # verlas/marcarlas desde Tendido; el avance abajo solo cuenta las activas.
        torres_qs = ordenar_torres_construccion(torres_qs.select_related(), incluir_no_aplica=True)

        existentes = {t.torre_id: t for t in TendidoTorre.objects.filter(proyecto=proyecto)}
        filas = []
        for torre in torres_qs:
            t = existentes.get(torre.id)
            if t is None:
                t = TendidoTorre.objects.create(proyecto=proyecto, torre=torre)
            filas.append(t)

        pesos_conductor = {
            'riega_manila_conductor': proyecto.peso_tend_riega_manila_pct,
            'riega_guaya_conductor': proyecto.peso_tend_riega_guaya_pct,
            'tendido_conductor': proyecto.peso_tend_tendido_conductor_pct,
            'grapado_amarre_conductor': proyecto.peso_tend_grapado_pct,
            'accesorios_puentes': proyecto.peso_tend_accesorios_pct,
            'balizas_desviadores': proyecto.peso_tend_balizas_pct,
        }
        pesos_fibra = {
            'riega_manila_fibra': proyecto.peso_tend_riega_manila_fibra_pct,
            'riega_guaya_opgw': proyecto.peso_tend_riega_guaya_opgw_pct,
            'tendido_opgw': proyecto.peso_tend_tendido_opgw_pct,
            'grapado_amarre_fibra': proyecto.peso_tend_grapado_fibra_pct,
            'empalmes_opgw': proyecto.peso_tend_empalmes_opgw_pct,
        }
        suma_c = sum(pesos_conductor.values())
        suma_f = sum(pesos_fibra.values())

        # #150: el promedio cuenta SOLO las torres que aplican (display=todas,
        # conteo=solo aplica=True) para que una torre "No aplica" no baje el %.
        filas_activas = [f for f in filas if f.torre.aplica]
        if filas_activas:
            avance_general_conductor = round(
                sum(t.avance_conductor for t in filas_activas) / len(filas_activas) * 100, 1)
            avance_general_fibra = round(
                sum(t.avance_fibra for t in filas_activas) / len(filas_activas) * 100, 1)
        else:
            avance_general_conductor = avance_general_fibra = 0

        ctx.update({
            'proyecto': proyecto,
            'filas': filas,
            'pesos_conductor': pesos_conductor,
            'pesos_fibra': pesos_fibra,
            'suma_conductor': suma_c,
            'suma_fibra': suma_f,
            'suma_conductor_ok': suma_c == 100,
            'suma_fibra_ok': suma_f == 100,
            'columnas_conductor': TendidoTorre.COLUMNAS_CONDUCTOR,
            'columnas_fibra': TendidoTorre.COLUMNAS_FIBRA,
            'avance_general_conductor': avance_general_conductor,
            'avance_general_fibra': avance_general_fibra,
            'active_tab': 'tendido',
        })
        return ctx


class TendidoPesosUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — actualiza pesos Conductor o Fibra (cada uno suma 100 independiente)."""
    allowed_roles = ALL_ADMIN_ROLES

    def post(self, request, proyecto_id, *args, **kwargs):
        from django.http import JsonResponse
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        seccion = request.POST.get('seccion', '').strip()
        if seccion not in ('conductor', 'fibra'):
            return JsonResponse({'error': 'seccion debe ser conductor o fibra'}, status=400)

        if seccion == 'conductor':
            mapeo = {
                'riega_manila': 'peso_tend_riega_manila_pct',
                'riega_guaya': 'peso_tend_riega_guaya_pct',
                'tendido': 'peso_tend_tendido_conductor_pct',
                'grapado': 'peso_tend_grapado_pct',
                'accesorios': 'peso_tend_accesorios_pct',
                'balizas': 'peso_tend_balizas_pct',
            }
        else:
            mapeo = {
                'riega_manila_fibra': 'peso_tend_riega_manila_fibra_pct',
                'riega_guaya_opgw': 'peso_tend_riega_guaya_opgw_pct',
                'tendido_opgw': 'peso_tend_tendido_opgw_pct',
                'grapado_fibra': 'peso_tend_grapado_fibra_pct',
                'empalmes_opgw': 'peso_tend_empalmes_opgw_pct',
            }
        try:
            valores = {k: int(request.POST.get(k, 0)) for k in mapeo}
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Los pesos deben ser enteros 0-100.'}, status=400)
        for k, v in valores.items():
            if v < 0 or v > 100:
                return JsonResponse({'error': f'Peso fuera de rango: {k}={v}'}, status=400)
        if sum(valores.values()) != 100:
            return JsonResponse(
                {'error': f'La suma de pesos {seccion} debe ser 100 (actual: {sum(valores.values())}).'},
                status=400)

        for clave, campo in mapeo.items():
            setattr(proyecto, campo, valores[clave])
        proyecto.save(update_fields=list(mapeo.values()))
        return JsonResponse({'ok': True, 'seccion': seccion})


class TendidoToggleView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — toggle de una actividad bool de una torre del módulo Tendido."""
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        from django.http import JsonResponse
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        torre = get_object_or_404(TorreConstruccion, id=torre_id, proyecto=proyecto)
        campo = request.POST.get('campo', '').strip()
        if campo not in TENDIDO_TODOS_BOOL:
            return JsonResponse({'error': f'Campo inválido: {campo!r}'}, status=400)
        valor = request.POST.get('valor', '').strip() in ('1', 'true', 'on', 'True')

        # Cuadrillas también se actualizan por este endpoint
        t, _ = TendidoTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
        setattr(t, campo, valor)
        t.save(update_fields=[campo, 'updated_at'])
        return JsonResponse({
            'ok': True,
            'avance_conductor': t.avance_conductor,
            'avance_conductor_pct': t.avance_conductor_pct,
            'avance_fibra': t.avance_fibra,
            'avance_fibra_pct': t.avance_fibra_pct,
        })


class TendidoRealizoUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — actualiza cuadrilla 'realizó' (conductor o fibra) para una torre."""
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        from django.http import JsonResponse
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        torre = get_object_or_404(TorreConstruccion, id=torre_id, proyecto=proyecto)
        seccion = request.POST.get('seccion', '').strip()
        if seccion not in ('conductor', 'fibra'):
            return JsonResponse({'error': 'seccion inválida'}, status=400)
        valor = request.POST.get('valor', '').strip()[:100]
        campo = 'realizo_conductor' if seccion == 'conductor' else 'realizo_fibra'
        t, _ = TendidoTorre.objects.get_or_create(proyecto=proyecto, torre=torre)
        setattr(t, campo, valor)
        t.save(update_fields=[campo, 'updated_at'])
        return JsonResponse({'ok': True})


# ==========================================================================
# Trinchos y Cunetas (#80) — captura por torre con materiales
# ==========================================================================

TRINCHO_MATERIALES = [
    'tubo_metalico', 'malla_eslabonada', 'alambre_galvanizado',
    'geotextil', 'cemento', 'arena', 'grava',
]


class TrinchosCunetasListView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Lista de obras de protección (trinchos/cunetas) del proyecto."""
    template_name = 'construccion/trinchos_cunetas_lista.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        # #149 (bounce=5, decisión HITL): se ELIMINA el mecanismo de aplicabilidad
        # por-torre `aplica_obras_proteccion`. El cliente pidió quitar el checkbox
        # (no mejorar el filtro). El módulo Obras de Protección ahora lista TODAS
        # las torres APLICABLES del proyecto, gobernadas SOLO por el flag global
        # torre.aplica (#160) — la torre anulada (aplica=False) sigue excluida.
        # `incluir_no_aplica=False` materializa "todas las torres aplicables" y
        # evita colar la torre anulada (E25). La columna BD
        # ObraCivilTorre.aplica_obras_proteccion queda DORMIDA (sin migración).
        torres_ordenadas = list(
            ordenar_torres_construccion(torres_qs, incluir_no_aplica=False))
        # El LISTADO es torre-driven (una fila por torre aplicable): cada torre
        # aparece con su obra capturada (estado real) o como fila placeholder
        # "Pendiente". Las obras existentes ya no se filtran por el flag eliminado.
        obras = list(TrinchoCuneta.objects
                     .filter(proyecto=proyecto)
                     .select_related('torre').order_by('torre__numero'))
        obras_por_torre = {o.torre_id: o for o in obras}
        # `filas`: una entrada por torre que aplica. `obra` es la TrinchoCuneta
        # capturada o None (pendiente de captura). El template itera `filas`.
        filas = [
            {'torre': t, 'obra': obras_por_torre.get(t.id)}
            for t in torres_ordenadas
        ]

        # Totales y resumen por cuadrilla — calculados sobre las obras CAPTURADAS.
        total_metros = sum(o.total_metros_obra for o in obras)
        completadas = sum(1 for o in obras if o.completado)
        pendientes = sum(1 for f in filas if f['obra'] is None)
        por_cuadrilla = {}
        for o in obras:
            por_cuadrilla.setdefault(o.cuadrilla or '—', []).append(o)

        ctx.update({
            'proyecto': proyecto,
            # #149: `filas` (torre-driven) es la fuente del listado; `obras`
            # (capturadas) se mantiene para métricas/compatibilidad.
            'filas': filas,
            'obras': obras,
            'total_torres': len(filas),
            'pendientes': pendientes,
            # #149 (bounce=5): el módulo Obras de Protección se rige SOLO por el
            # flag global torre.aplica (#160). El selector ofrece todas las torres
            # aplicables del proyecto (la torre anulada queda excluida vía
            # incluir_no_aplica=False).
            'torres_disponibles': torres_ordenadas,
            'total_metros': total_metros,
            'completadas': completadas,
            'por_cuadrilla': por_cuadrilla,
            'active_tab': 'obras-proteccion',
            'tipo_choices': TrinchoCuneta.TipoObra.choices,
        })
        return ctx


class ResumenMaterialesView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Resumen consolidado de materiales del proyecto (#154).

    Vista de solo lectura: agrega los materiales de obra de todas las torres
    (vía ``ProyectoConstruccion.resumen_materiales()``) y los presenta con un
    total del proyecto + desglose por torre, en tabla + gráfico.
    """
    template_name = 'construccion/resumen_materiales.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        import json

        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        resumen = proyecto.resumen_materiales()

        # #154 (O2, QA 29-jun): tabla invertida — 1 fila por MATERIAL (no por
        # torre), con un valor por torre + columna Total al final de la fila.
        # Antes: Torre=filas / Material=columnas (~25 columnas, scroll
        # horizontal excesivo). Ahora: Material=filas / Torre=columnas, mismo
        # mapeo material↔valor de `resumen`, solo se invierte qué eje es fila
        # y cuál es columna. `torres_labels` alimenta el header (1 <th> por
        # torre) y cada fila trae `valores` alineado a ese mismo orden +
        # `total` = Σ de esa fila (ese material) a través de todas las torres.
        torres_labels = [f['torre'] for f in resumen['torres']]
        filas_tabla = [
            {
                'material': col['label'],
                'unidad': col['unidad'],
                'valores': [f[col['key']] for f in resumen['torres']],
                'total': resumen['total'][col['key']],
            }
            for col in resumen['columnas']
        ]

        # Serie para Chart.js: labels = torres, datasets = materiales (con datos).
        # Se pasa CRUDO (json.dumps) y se entrega al template vía json_script en el
        # template (no aquí) — acá solo construimos el objeto Python. El template
        # lo emite con {{ resumen_chart|json_script:"..." }} (memoria portafolio
        # #139: objeto crudo, NO doble-encode). Solo materiales con algún dato > 0
        # entran como serie, para que el gráfico no se llene de barras en cero.
        labels = [f['torre'] for f in resumen['torres']]
        series = []
        for col in resumen['columnas']:
            key = col['key']
            data = [float(f[key]) for f in resumen['torres']]
            if any(v > 0 for v in data):
                series.append({
                    'label': f"{col['label']} ({col['unidad']})",
                    'data': data,
                })
        resumen_chart = {'labels': labels, 'series': series}

        ctx.update({
            'proyecto': proyecto,
            'resumen': resumen,
            'filas_tabla': filas_tabla,
            'torres_labels': torres_labels,
            'resumen_chart': resumen_chart,
            'active_tab': 'resumen-materiales',
        })
        return ctx


class TrinchosCunetasUpsertView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — crea o actualiza una obra de protección.

    Body: torre_id (uuid), medida_manejo, metros_trinchos, metros_cunetas,
    7 materiales, cuadrilla, completado, notas.
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, proyecto_id, *args, **kwargs):
        from decimal import Decimal, InvalidOperation
        from django.http import JsonResponse
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        torre_id = request.POST.get('torre_id', '').strip()
        if not torre_id:
            return JsonResponse({'error': 'torre_id requerido'}, status=400)
        torre = get_object_or_404(TorreConstruccion, id=torre_id, proyecto=proyecto)

        # #149 (bounce=5): se eliminó la aplicabilidad por-torre
        # `aplica_obras_proteccion`. El upsert ya NO la usa como guardia; la
        # aplicabilidad la gobierna el flag global torre.aplica (#160).

        tipo = request.POST.get('medida_manejo', '').strip()
        if tipo not in dict(TrinchoCuneta.TipoObra.choices):
            return JsonResponse({'error': f'medida_manejo inválida: {tipo!r}'}, status=400)

        # Lecturas
        def to_decimal(raw, allow_null=False):
            raw = (raw or '').strip()
            if not raw:
                return None if allow_null else Decimal('0')
            try:
                return Decimal(raw)
            except InvalidOperation:
                return 'INVALID'

        metros_t = to_decimal(request.POST.get('metros_trinchos'), allow_null=True)
        metros_c = to_decimal(request.POST.get('metros_cunetas'), allow_null=True)
        if metros_t == 'INVALID' or metros_c == 'INVALID':
            return JsonResponse({'error': 'metros inválidos'}, status=400)

        # Validación: si tipo requiere trincho, debe haber metros_trinchos>0
        if tipo == TrinchoCuneta.TipoObra.TRINCHO and not (metros_t and metros_t > 0):
            return JsonResponse({'error': 'Tipo TRINCHO requiere metros_trinchos > 0.'}, status=400)
        if tipo == TrinchoCuneta.TipoObra.CUNETA and not (metros_c and metros_c > 0):
            return JsonResponse({'error': 'Tipo CUNETA requiere metros_cunetas > 0.'}, status=400)
        if tipo == TrinchoCuneta.TipoObra.AMBAS:
            if not (metros_t and metros_t > 0):
                return JsonResponse({'error': 'Tipo AMBAS requiere metros_trinchos > 0.'}, status=400)
            if not (metros_c and metros_c > 0):
                return JsonResponse({'error': 'Tipo AMBAS requiere metros_cunetas > 0.'}, status=400)

        # Materiales
        materiales = {}
        for f in TRINCHO_MATERIALES:
            v = to_decimal(request.POST.get(f))
            if v == 'INVALID':
                return JsonResponse({'error': f'{f}: valor inválido'}, status=400)
            if v < 0:
                return JsonResponse({'error': f'{f}: no puede ser negativo'}, status=400)
            materiales[f] = v

        obj, created = TrinchoCuneta.objects.update_or_create(
            proyecto=proyecto, torre=torre,
            defaults={
                'medida_manejo': tipo,
                'metros_trinchos': metros_t,
                'metros_cunetas': metros_c,
                'notas': request.POST.get('notas', '').strip(),
                'cuadrilla': request.POST.get('cuadrilla', '').strip()[:100],
                'completado': request.POST.get('completado', '').strip() in ('1', 'true', 'on'),
                **materiales,
            },
        )
        return JsonResponse({
            'ok': True,
            'created': created,
            'id': str(obj.id),
            'total_metros': float(obj.total_metros_obra),
            'estado': obj.estado,
        })


class TrinchosCunetasDeleteView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ALL_ADMIN_ROLES

    def post(self, request, proyecto_id, pk, *args, **kwargs):
        from django.http import JsonResponse
        obra = get_object_or_404(TrinchoCuneta, id=pk, proyecto_id=proyecto_id)
        obra.delete()
        return JsonResponse({'ok': True})


# ==========================================================================
# Dashboards Curva S (#75 Obra Civil · #77 Montaje)
# ==========================================================================

class _DashboardCurvaSBase(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Vista común para Dashboards Curva S. Subclases definen FASE_DEFAULT,
    template_name y nombre de URL update."""
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES
    FASE_DEFAULT = None  # override

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        fase = self.request.GET.get('fase', self.FASE_DEFAULT).upper()
        if fase not in {f for f, _ in DashboardAvanceSemanal.Fase.choices}:
            fase = self.FASE_DEFAULT

        semanas = list(DashboardAvanceSemanal.objects
            .filter(proyecto=proyecto, fase=fase)
            .order_by('semana'))
        total_torres = proyecto.torres.count() or 0

        # Indicadores
        if semanas:
            ultimo = semanas[-1]
            varianza_acum = ultimo.varianza_acum
            pct_prog = float(ultimo.pct_programado)
            pct_cons = float(ultimo.pct_construido)
            tasa = (sum(int(s.torres_construidas_semana) for s in semanas) / len(semanas)
                    if semanas else 0)
            torres_restantes = max(0, total_torres - int(ultimo.torres_construidas_acum))
            semanas_restantes = (torres_restantes / tasa) if tasa else None
        else:
            varianza_acum = pct_prog = pct_cons = tasa = 0
            semanas_restantes = None

        ctx.update({
            'proyecto': proyecto,
            'fase_activa': fase,
            'fases_disponibles': DashboardAvanceSemanal.Fase.choices,
            'semanas': semanas,
            'total_torres': total_torres,
            'varianza_acum': varianza_acum,
            'pct_programado_total': round(pct_prog, 1),
            'pct_construido_total': round(pct_cons, 1),
            'tasa_torres_semana': round(tasa, 2),
            'semanas_restantes': (round(semanas_restantes, 1) if semanas_restantes else None),
            'datos_chart': self._build_chart_data(semanas),
            'active_tab': self.FASE_DEFAULT.lower() if self.FASE_DEFAULT else 'dashboard',
        })
        return ctx

    @staticmethod
    def _build_chart_data(semanas):
        import json
        return json.dumps({
            'labels': [s.semana.isoformat() for s in semanas],
            'planeado': [float(s.pct_programado) for s in semanas],
            'ejecutado': [float(s.pct_construido) for s in semanas],
        })


class DashboardObraCivilView(_DashboardCurvaSBase):
    """Dashboard Curva S de Obra Civil (#75) + 3 gráficas gerenciales (#141).

    Además de la Curva S por torres-construidas, expone:
      G1  serie consolidada de la Curva S (todo el proyecto)
      G2  avance por etapa OC (barras % torres completas)
      G3  desviación de materiales de vaciado (calc vs real + semáforo)
    Los 3 datasets viajan pre-serializados (JSON) al template para evitar
    floats es-CO crudos en el JS inline (memoria recurrente del portafolio).
    """
    template_name = 'construccion/dashboard_curva_s.html'
    FASE_DEFAULT = 'OOCC'

    def get_context_data(self, **kwargs):
        import json
        from .calculators import (
            avance_por_etapa_oc,
            curva_s_consolidada,
            desviacion_materiales_solado,
            desviacion_materiales_vaciado,
            UMBRAL_DESVIACION_DEFAULT,
        )
        ctx = super().get_context_data(**kwargs)
        proyecto = ctx['proyecto']

        try:
            umbral = float(self.request.GET.get('umbral', UMBRAL_DESVIACION_DEFAULT))
            if umbral <= 0:
                umbral = UMBRAL_DESVIACION_DEFAULT
        except (TypeError, ValueError):
            umbral = UMBRAL_DESVIACION_DEFAULT

        avance_etapas = avance_por_etapa_oc(proyecto)
        # #141 — G3 por etapa: el cliente necesita ver Solado y Vaciado por
        # separado para saber en cuál hay sobreconsumo de materiales.
        desviacion_solado = desviacion_materiales_solado(proyecto, umbral)
        desviacion_vaciado = desviacion_materiales_vaciado(proyecto, umbral)
        consolidada = curva_s_consolidada(proyecto)

        # Para los assert_contains del journey y las leyendas visibles, también
        # pasamos las listas crudas (Django las escapa) además del JSON para el
        # Chart.js init.
        ctx.update({
            'mostrar_graficas_141': True,
            'umbral_desviacion': umbral,
            'avance_etapas': avance_etapas,
            'desviacion_solado': desviacion_solado,
            'desviacion_vaciado': desviacion_vaciado,
            'tiene_alerta_desviacion': any(
                m['semaforo'] == 'rojo'
                for m in (desviacion_solado + desviacion_vaciado)
            ),
            'graficas_json': json.dumps({
                'avance_etapas': avance_etapas,
                'desviacion_solado': desviacion_solado,
                'desviacion_vaciado': desviacion_vaciado,
                'curva_consolidada': consolidada,
            }),
        })
        return ctx


class DashboardMontajeView(_DashboardCurvaSBase):
    """Dashboard Curva S de Montaje (#77)."""
    template_name = 'construccion/dashboard_curva_s.html'
    FASE_DEFAULT = 'MONTAJE'


class DashboardSemanaUpsertView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — crea o actualiza una semana del dashboard. Recalcula
    acumulados y porcentajes para toda la serie de la fase.
    """
    allowed_roles = ALL_ADMIN_ROLES

    def post(self, request, proyecto_id, *args, **kwargs):
        from datetime import date
        from django.http import JsonResponse
        from .models import recalcular_dashboard_acumulados
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        fase = request.POST.get('fase', '').upper()
        if fase not in {f for f, _ in DashboardAvanceSemanal.Fase.choices}:
            return JsonResponse({'error': f'fase inválida: {fase!r}'}, status=400)
        semana_str = request.POST.get('semana', '').strip()
        try:
            semana = date.fromisoformat(semana_str)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'semana debe ser ISO YYYY-MM-DD'}, status=400)
        try:
            prog = int(request.POST.get('torres_programadas_semana', '0') or 0)
            cons = int(request.POST.get('torres_construidas_semana', '0') or 0)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'valores deben ser enteros'}, status=400)
        total_torres = proyecto.torres.count()
        if prog < 0 or cons < 0:
            return JsonResponse({'error': 'no se permiten valores negativos'}, status=400)
        if total_torres and prog > total_torres:
            return JsonResponse(
                {'error': f'prog ({prog}) > total torres del proyecto ({total_torres})'},
                status=400)
        if total_torres and cons > total_torres:
            return JsonResponse(
                {'error': f'cons ({cons}) > total torres del proyecto ({total_torres})'},
                status=400)

        obj, created = DashboardAvanceSemanal.objects.update_or_create(
            proyecto=proyecto, fase=fase, semana=semana,
            defaults={
                'torres_programadas_semana': prog,
                'torres_construidas_semana': cons,
                'torres_incluidas_prog': request.POST.get('torres_incluidas_prog', '').strip()[:300],
                'torres_incluidas_cons': request.POST.get('torres_incluidas_cons', '').strip()[:300],
                'pendientes': request.POST.get('pendientes', '').strip(),
            },
        )
        recalcular_dashboard_acumulados(proyecto, fase)
        obj.refresh_from_db()
        return JsonResponse({
            'ok': True,
            'created': created,
            'id': str(obj.id),
            'prog_acum': int(obj.torres_programadas_acum),
            'cons_acum': int(obj.torres_construidas_acum),
            'pct_programado': float(obj.pct_programado),
            'pct_construido': float(obj.pct_construido),
        })


class DashboardSemanaDeleteView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ALL_ADMIN_ROLES

    def post(self, request, proyecto_id, pk, *args, **kwargs):
        from django.http import JsonResponse
        from .models import recalcular_dashboard_acumulados
        sem = get_object_or_404(DashboardAvanceSemanal, id=pk, proyecto_id=proyecto_id)
        proyecto = sem.proyecto
        fase = sem.fase
        sem.delete()
        recalcular_dashboard_acumulados(proyecto, fase)
        return JsonResponse({'ok': True})


class DashboardChartDataView(LoginRequiredMixin, RoleRequiredMixin, View):
    """GET JSON con los datos de la Curva S para Chart.js.

    Soporta ``?fase=OOCC|MONTAJE|TENDIDO`` (serie por fase) y
    ``?fase=CONSOLIDADA`` (#141 — serie consolidada de todo el proyecto,
    unión de todas las fases con datos).
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get(self, request, proyecto_id, *args, **kwargs):
        from django.http import JsonResponse
        from .calculators import curva_s_consolidada
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        fase = request.GET.get('fase', 'OOCC').upper()
        if fase == 'CONSOLIDADA':
            return JsonResponse(curva_s_consolidada(proyecto))
        if fase not in {f for f, _ in DashboardAvanceSemanal.Fase.choices}:
            return JsonResponse({'error': 'fase inválida'}, status=400)
        # #122 Fase 2: Obra Civil sirve el CONTEO de torres por fechas reales
        # (mismo payload que el render inicial), para que el selector "Serie →
        # Obra Civil" no vuelva a la serie vacía de DashboardAvanceSemanal.
        if fase == 'OOCC':
            from .views_dashboards import _curva_s_chart_payload
            return JsonResponse(_curva_s_chart_payload(proyecto, 'OOCC'))
        semanas = DashboardAvanceSemanal.objects.filter(
            proyecto=proyecto, fase=fase).order_by('semana')
        return JsonResponse({
            'labels': [s.semana.isoformat() for s in semanas],
            'planeado': [float(s.pct_programado) for s in semanas],
            'ejecutado': [float(s.pct_construido) for s in semanas],
        })


class DashboardGraficasDataView(LoginRequiredMixin, RoleRequiredMixin, View):
    """GET JSON con los datos de las 3 gráficas del Dashboard de Obra Civil (#141).

    Single source of truth para G1 (Curva S consolidada), G2 (avance por etapa)
    y G3 (desviación de materiales de vaciado). Reusa los agregadores puros de
    ``calculators.py`` — el template del dashboard también los consume vía el
    context para el render inicial; este endpoint sirve el refresh/AJAX y el
    contrato que valida el journey E2E.

    Query params:
      - ``?umbral=`` (float, default 10.0): umbral del semáforo de G3.

    Robusto ante proyecto sin torres / sin vaciado: devuelve arreglos vacíos o
    materiales en 0 con semáforo 'sin_datos', siempre HTTP 200.
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get(self, request, proyecto_id, *args, **kwargs):
        from django.http import JsonResponse
        from .calculators import (
            avance_por_etapa_oc,
            curva_s_consolidada,
            desviacion_materiales_solado,
            desviacion_materiales_vaciado,
            UMBRAL_DESVIACION_DEFAULT,
        )
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        # Umbral del semáforo — edge: valor inválido cae al default (no 500).
        try:
            umbral = float(request.GET.get('umbral', UMBRAL_DESVIACION_DEFAULT))
            if umbral <= 0:
                umbral = UMBRAL_DESVIACION_DEFAULT
        except (TypeError, ValueError):
            umbral = UMBRAL_DESVIACION_DEFAULT

        # Curva S: planeado/ejecutado de la fase OOCC + serie consolidada.
        semanas_oc = DashboardAvanceSemanal.objects.filter(
            proyecto=proyecto, fase='OOCC').order_by('semana')
        consolidada = curva_s_consolidada(proyecto)

        return JsonResponse({
            'curva_s': {
                'labels': [s.semana.isoformat() for s in semanas_oc],
                'planeado': [float(s.pct_programado) for s in semanas_oc],
                'ejecutado': [float(s.pct_construido) for s in semanas_oc],
                'consolidada': consolidada,
            },
            'avance_etapas': avance_por_etapa_oc(proyecto),
            # #141 — G3 por etapa: Solado y Vaciado separados.
            'desviacion_solado': desviacion_materiales_solado(proyecto, umbral),
            'desviacion_vaciado': desviacion_materiales_vaciado(proyecto, umbral),
            'umbral': umbral,
        })


# ==========================================================================
# Placeholders para módulos pendientes (sidebar #73)
# ==========================================================================

class ModuloPlaceholderView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Vista placeholder para módulos del sidebar que aún están en construcción.

    Cada URL la usa con `extra_context = {'modulo_titulo': '...', 'modulo_slug': '...'}`.
    """
    template_name = 'construccion/placeholder.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proyecto_id = self.kwargs.get('proyecto_id')
        context['proyecto'] = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        context['modulo_titulo'] = self.extra_context.get('modulo_titulo') if self.extra_context else 'Módulo'
        context['modulo_slug'] = self.extra_context.get('modulo_slug') if self.extra_context else ''
        return context


# === /modulo indicadores_construccion_sub_run_a — split de archivo magnet ===
# F2 scaffolding agregó estos imports. Las vistas nuevas van en los archivos
# dedicados, NO en este archivo.
from .views_b1_actividades_finales import *  # noqa: F401, F403
from .views_b2_indicadores import *  # noqa: F401, F403
from .views_b3_dashboard_indicadores import *  # noqa: F401, F403

# === /modulo excel_paridad_oc_montaje — split de archivo magnet ===
# F2 scaffolding: B2b (OC detalle views) y B3b (Montaje detalle views) en F3.
from .views_b3_oc_detalle import *  # noqa: E402,F401,F403
from .views_b3_mont_detalle import *  # noqa: E402,F401,F403
