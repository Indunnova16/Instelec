"""Views B2 — Indicadores Construcción (#98).

CRUDs para IndicadorFinancieroConstruccion, IndicadorTecnicoConstruccion,
IndicadorDesempenoLinea + endpoint POST recalcular on-demand.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from apps.core.mixins import RoleRequiredMixin, SubModuloRequiredMixin

from .models import ProyectoConstruccion
from .models_b2_indicadores import (
    IndicadorFinancieroConstruccion,
    IndicadorTecnicoConstruccion,
    IndicadorDesempenoLinea,
)
from .forms_b2_indicadores import (
    IndicadorFinancieroForm,
    IndicadorTecnicoForm,
    IndicadorDesempenoLineaForm,
)


# ---------------------------------------------------------------------------
# Mixin común: proyecto contextualizado
# ---------------------------------------------------------------------------

class ProyectoB2Mixin(LoginRequiredMixin):
    """Inyecta el proyecto al contexto y maneja proyecto_id en URL."""
    required_submodulo = 'INDICADORES_CONSTRUCCION'

    def get_proyecto(self):
        return get_object_or_404(
            ProyectoConstruccion, pk=self.kwargs['proyecto_id']
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['proyecto'] = self.get_proyecto()
        return ctx


# ===========================================================================
# 1. INDICADOR FINANCIERO
# ===========================================================================

class IndicadorFinancieroListView(ProyectoB2Mixin, ListView):
    """Lista indicadores financieros del proyecto."""
    model = IndicadorFinancieroConstruccion
    template_name = 'construccion/indicadores_lista.html'
    context_object_name = 'indicadores'
    paginate_by = 25

    def get_queryset(self):
        return (IndicadorFinancieroConstruccion.objects
                .filter(proyecto_id=self.kwargs['proyecto_id'])
                .select_related('actualizado_por', 'proyecto')
                .order_by('-fecha'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tipo'] = 'financiero'
        ctx['titulo'] = 'Indicadores Financieros'
        ctx['crear_url'] = reverse(
            'construccion:b2_indicador_financiero_crear',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )
        return ctx


class IndicadorFinancieroCreateView(ProyectoB2Mixin, CreateView):
    """Crear nuevo IndicadorFinancieroConstruccion."""
    model = IndicadorFinancieroConstruccion
    form_class = IndicadorFinancieroForm
    template_name = 'construccion/indicadores_form_financiero.html'

    def form_valid(self, form):
        form.instance.proyecto = self.get_proyecto()
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Indicador financiero creado. Margen: '
            f'{self.object.margen_operativo:.2f}%' if self.object.margen_operativo is not None
            else 'Indicador financiero creado (margen no calculable, ingresos = 0).'
        )
        return response

    def get_success_url(self):
        return reverse(
            'construccion:b2_indicador_financiero_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


class IndicadorFinancieroUpdateView(ProyectoB2Mixin, UpdateView):
    """Editar IndicadorFinancieroConstruccion."""
    model = IndicadorFinancieroConstruccion
    form_class = IndicadorFinancieroForm
    template_name = 'construccion/indicadores_form_financiero.html'

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'construccion:b2_indicador_financiero_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


class IndicadorFinancieroDeleteView(ProyectoB2Mixin, DeleteView):
    """Eliminar IndicadorFinancieroConstruccion."""
    model = IndicadorFinancieroConstruccion
    # Sin template — GET no se soporta, sólo POST (cumple HX-Delete o form simple)
    http_method_names = ['post', 'delete']

    def get_success_url(self):
        messages.success(self.request, 'Indicador financiero eliminado.')
        return reverse(
            'construccion:b2_indicador_financiero_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


# ===========================================================================
# 2. INDICADOR TÉCNICO
# ===========================================================================

class IndicadorTecnicoListView(ProyectoB2Mixin, ListView):
    """Lista indicadores técnicos."""
    model = IndicadorTecnicoConstruccion
    template_name = 'construccion/indicadores_lista.html'
    context_object_name = 'indicadores'
    paginate_by = 25

    def get_queryset(self):
        return (IndicadorTecnicoConstruccion.objects
                .filter(proyecto_id=self.kwargs['proyecto_id'])
                .order_by('-fecha'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tipo'] = 'tecnico'
        ctx['titulo'] = 'Indicadores Técnicos'
        ctx['crear_url'] = reverse(
            'construccion:b2_indicador_tecnico_crear',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )
        return ctx


class IndicadorTecnicoCreateView(ProyectoB2Mixin, CreateView):
    """Crear IndicadorTecnicoConstruccion."""
    model = IndicadorTecnicoConstruccion
    form_class = IndicadorTecnicoForm
    template_name = 'construccion/indicadores_form_tecnico.html'

    def form_valid(self, form):
        form.instance.proyecto = self.get_proyecto()
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Indicador técnico creado.')
        return response

    def get_success_url(self):
        return reverse(
            'construccion:b2_indicador_tecnico_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


class IndicadorTecnicoUpdateView(ProyectoB2Mixin, UpdateView):
    """Editar IndicadorTecnicoConstruccion."""
    model = IndicadorTecnicoConstruccion
    form_class = IndicadorTecnicoForm
    template_name = 'construccion/indicadores_form_tecnico.html'

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'construccion:b2_indicador_tecnico_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


class IndicadorTecnicoDeleteView(ProyectoB2Mixin, DeleteView):
    """Eliminar IndicadorTecnicoConstruccion."""
    model = IndicadorTecnicoConstruccion
    # Sin template — GET no se soporta, sólo POST (cumple HX-Delete o form simple)
    http_method_names = ['post', 'delete']

    def get_success_url(self):
        messages.success(self.request, 'Indicador técnico eliminado.')
        return reverse(
            'construccion:b2_indicador_tecnico_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


# ===========================================================================
# 3. INDICADOR DESEMPEÑO LÍNEA
# ===========================================================================

class IndicadorDesempenoListView(ProyectoB2Mixin, ListView):
    """Lista indicadores desempeño línea."""
    model = IndicadorDesempenoLinea
    template_name = 'construccion/indicadores_lista.html'
    context_object_name = 'indicadores'
    paginate_by = 25

    def get_queryset(self):
        return (IndicadorDesempenoLinea.objects
                .filter(proyecto_id=self.kwargs['proyecto_id'])
                .select_related('linea', 'cuadrilla')
                .order_by('-fecha', 'linea', 'tipo_trabajo'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tipo'] = 'desempeno'
        ctx['titulo'] = 'Indicadores Desempeño por Línea'
        ctx['crear_url'] = reverse(
            'construccion:b2_indicador_desempeno_crear',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )
        return ctx


class IndicadorDesempenoCreateView(ProyectoB2Mixin, CreateView):
    """Crear IndicadorDesempenoLinea."""
    model = IndicadorDesempenoLinea
    form_class = IndicadorDesempenoLineaForm
    template_name = 'construccion/indicadores_desempeno_linea_form.html'

    def form_valid(self, form):
        form.instance.proyecto = self.get_proyecto()
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Indicador desempeño creado. Estado: {self.object.get_estado_display()}'
        )
        return response

    def get_success_url(self):
        return reverse(
            'construccion:b2_indicador_desempeno_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


class IndicadorDesempenoUpdateView(ProyectoB2Mixin, UpdateView):
    """Editar IndicadorDesempenoLinea."""
    model = IndicadorDesempenoLinea
    form_class = IndicadorDesempenoLineaForm
    template_name = 'construccion/indicadores_desempeno_linea_form.html'

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'construccion:b2_indicador_desempeno_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


class IndicadorDesempenoDeleteView(ProyectoB2Mixin, DeleteView):
    """Eliminar IndicadorDesempenoLinea."""
    model = IndicadorDesempenoLinea
    # Sin template — GET no se soporta, sólo POST (cumple HX-Delete o form simple)
    http_method_names = ['post', 'delete']

    def get_success_url(self):
        messages.success(self.request, 'Indicador desempeño eliminado.')
        return reverse(
            'construccion:b2_indicador_desempeno_lista',
            kwargs={'proyecto_id': self.kwargs['proyecto_id']},
        )


# ===========================================================================
# 4. RECALCULAR ON-DEMAND
# ===========================================================================

@method_decorator(require_POST, name='dispatch')
class RecalcularIndicadoresView(LoginRequiredMixin, View):
    """POST /construccion/<uuid:proyecto_id>/indicadores/recalcular/

    Re-corre el cálculo sobre TODOS los indicadores del proyecto. Útil tras
    bug-fix de calculadora o ajuste de datos legacy. Retorna JSON con
    {'financieros': N, 'tecnicos': M, 'desempeno': K}.
    """

    def post(self, request, proyecto_id):
        proyecto = get_object_or_404(ProyectoConstruccion, pk=proyecto_id)
        fin_count = tec_count = des_count = 0

        for ind in IndicadorFinancieroConstruccion.objects.filter(proyecto=proyecto):
            ind.recalcular()
            ind.save(update_fields=['margen_operativo', 'desviacion_presupuestal', 'updated_at'])
            fin_count += 1

        for ind in IndicadorTecnicoConstruccion.objects.filter(proyecto=proyecto):
            ind.recalcular()
            ind.save(update_fields=[
                'ejecucion_presupuestal', 'avance_obra', 'cumplimiento_cronograma',
                'productividad', 'rendimiento_cuadrillas', 'updated_at',
            ])
            tec_count += 1

        for ind in IndicadorDesempenoLinea.objects.filter(proyecto=proyecto):
            ind.clasificar()
            ind.save(update_fields=['estado', 'updated_at'])
            des_count += 1

        if request.headers.get('HX-Request') or request.headers.get('Accept', '').startswith('application/json'):
            return JsonResponse({
                'ok': True,
                'financieros': fin_count,
                'tecnicos': tec_count,
                'desempeno': des_count,
            })
        messages.success(
            request,
            f'Recalculo OK: {fin_count} financieros, {tec_count} técnicos, '
            f'{des_count} desempeño.'
        )
        return HttpResponseRedirect(
            reverse('construccion:b2_indicador_financiero_lista',
                    kwargs={'proyecto_id': proyecto_id})
        )
