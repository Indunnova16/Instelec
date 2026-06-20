"""
Vistas CRUD de Programación semanal de cuadrillas (#155, B2).

Sub-feature B2 del bloque `programacion_cuadrillas`. Implementa crear / editar /
detalle de `ProgramacionSemanalCuadrilla` (modelos S1), expuesto bajo la
subsección administrativa de Construcción (`construccion:` namespace).

Patrón: hereda de las vistas de `apps/construccion/views.py`
(`LoginRequiredMixin` + `RoleRequiredMixin` con `allowed_roles`). El detalle deja
anchors/placeholders para que B3 inserte el inline de ejecución
(`#ejecucion-inline`) y B4 el dashboard.

============================================================================
RUTAS A REGISTRAR (las cabla F4 / B1 en apps/construccion/urls_pc.py — NO las
toco yo, dueño = B1). Contrato del BLUEPRINT, namespace `construccion:`:

    path('programacion-cuadrillas/crear/',
         views_pc_programacion.ProgramacionCuadrillaCreateView.as_view(),
         name='programacion_cuadrilla_crear'),
    path('programacion-cuadrillas/<uuid:pk>/',
         views_pc_programacion.ProgramacionCuadrillaDetailView.as_view(),
         name='programacion_cuadrilla_detalle'),
    path('programacion-cuadrillas/<uuid:pk>/editar/',
         views_pc_programacion.ProgramacionCuadrillaUpdateView.as_view(),
         name='programacion_cuadrilla_editar'),

(import: `from apps.cuadrillas import views_pc_programacion`)
============================================================================
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView

from apps.core.mixins import RoleRequiredMixin

from . import calculators_pc
from .forms_pc import ProgramacionSemanalCuadrillaForm
from .models_pc import ProgramacionSemanalCuadrilla

# Roles con acceso administrativo (espeja apps/construccion/views.py::ALL_ADMIN_ROLES).
PROGRAMACION_ROLES = [
    'admin', 'director', 'coordinador', 'ing_residente',
    'admin_general', 'coordinador_general', 'admin_construccion',
]


class ProgramacionCuadrillaCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    """Crear una nueva programación semanal de cuadrilla."""

    model = ProgramacionSemanalCuadrilla
    form_class = ProgramacionSemanalCuadrillaForm
    template_name = 'construccion/programacion_cuadrilla_form.html'
    allowed_roles = PROGRAMACION_ROLES

    def get_initial(self):
        """Prefill Año y Semana con el año/semana ISO actuales (#155, editable).

        Usamos `date.today().isocalendar()` para que el AÑO sea el ISO (no
        `date.today().year`): en los bordes de año la semana ISO 1/52/53 puede
        caer en un año distinto al calendario, y la programación se indexa por
        semana ISO. Ambos quedan como `initial` → editables por el usuario.
        """
        initial = super().get_initial()
        iso = date.today().isocalendar()
        initial.setdefault('anio', iso[0])
        initial.setdefault('semana', iso[1])
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['es_edicion'] = False
        context['titulo'] = 'Nueva programación semanal'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Programación creada: {self.object}.'
        )
        return response

    def get_success_url(self):
        # Tras crear, ir al detalle (donde B3 registrará la ejecución).
        return reverse_lazy(
            'construccion:programacion_cuadrilla_detalle',
            kwargs={'pk': self.object.pk},
        )


class ProgramacionCuadrillaUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Editar una programación semanal existente."""

    model = ProgramacionSemanalCuadrilla
    form_class = ProgramacionSemanalCuadrillaForm
    template_name = 'construccion/programacion_cuadrilla_form.html'
    allowed_roles = PROGRAMACION_ROLES

    def get_queryset(self):
        # select_related para evitar N+1 al renderizar el form (cuadrilla/proyecto).
        return ProgramacionSemanalCuadrilla.objects.select_related(
            'cuadrilla', 'proyecto'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['es_edicion'] = True
        context['titulo'] = f'Editar programación — {self.object}'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Programación actualizada.')
        return response

    def get_success_url(self):
        return reverse_lazy(
            'construccion:programacion_cuadrilla_detalle',
            kwargs={'pk': self.object.pk},
        )


class ProgramacionCuadrillaDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """
    Detalle de una programación semanal.

    Muestra los datos de la programación y deja el anchor `#ejecucion-inline`
    como placeholder para que B3 inserte el inline de guardado de ejecución, y
    una sección de dashboard para B4. Pasa al contexto la ejecución existente
    (si la hay) y un form de ejecución vacío para que B3 lo reutilice.
    """

    model = ProgramacionSemanalCuadrilla
    template_name = 'construccion/programacion_cuadrilla_detalle.html'
    context_object_name = 'programacion'
    allowed_roles = PROGRAMACION_ROLES

    def get_queryset(self):
        return ProgramacionSemanalCuadrilla.objects.select_related(
            'cuadrilla', 'proyecto'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programacion = self.object
        # Edge case: ejecución puede no existir todavía (1:1 opcional).
        ejecucion = getattr(programacion, 'ejecucion', None)
        context['ejecucion'] = ejecucion
        context['tiene_ejecucion'] = ejecucion is not None
        # rendimiento_pct es propiedad del modelo Ejecucion (guard div/0 en S1).
        context['rendimiento_pct'] = (
            ejecucion.rendimiento_pct if ejecucion is not None else None
        )

        # #155 sub-2: dashboard de cumplimiento inline (reemplaza el placeholder).
        # Reusa la MISMA lógica que ProgramacionCuadrillaDashboardView vía
        # calculators_pc (NO se duplica). Alcance: las programaciones de ESTA
        # cuadrilla en el mismo año, para contextualizar el cumplimiento semanal.
        qs = (
            ProgramacionSemanalCuadrilla.objects
            .filter(cuadrilla=programacion.cuadrilla, anio=programacion.anio)
            .select_related('cuadrilla', 'ejecucion')
        )
        filas = calculators_pc.rendimiento_por_cuadrilla(qs)
        resumen = calculators_pc.resumen_por_cuadrilla(filas)

        total_prog = sum(f['torres_programadas'] for f in filas)
        total_ejec = sum(f['torres_ejecutadas'] for f in filas)
        rendimiento_global = (
            round(total_ejec / total_prog * 100, 1) if total_prog > 0 else 0.0
        )

        # Payload para la gráfica: OBJETO Python crudo (el template lo serializa
        # con json_script → evita doble-encoding, memoria instelec #139).
        chart_data = {
            'labels': [f['periodo'] for f in filas],
            'programadas': [f['torres_programadas'] for f in filas],
            'ejecutadas': [f['torres_ejecutadas'] for f in filas],
        }

        context.update({
            'cumplimiento_filas': filas,
            'cumplimiento_resumen': resumen,
            'cumplimiento_chart_data': chart_data,
            'cumplimiento_total_programadas': total_prog,
            'cumplimiento_total_ejecutadas': total_ejec,
            'cumplimiento_rendimiento_global': rendimiento_global,
        })
        return context
