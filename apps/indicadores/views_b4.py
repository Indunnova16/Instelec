"""
B4 — Vistas del dashboard de mantenimiento detallado + CRUD.

URLs montadas en apps/indicadores/urls_b4.py bajo el prefijo
``/indicadores/mantenimiento-v2/`` y ``/indicadores/mantenimiento-v2/...``.

Componentes:
- ``DashboardMantenimientoV2View``: 4 secciones (Financiero, Tecnico, ANS,
  Produccion Cuadrilla) + puntaje ANS prominente + tendencia 6 meses
  Chart.js + barras progress por componente.
- CRUD para los 3 modelos via CreateView / UpdateView / ListView.
"""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    ListView,
    TemplateView,
    UpdateView,
)

from .calculators_b4 import (
    resumen_mensual,
    serie_componentes_ans,
    tendencia_ans_6_meses,
)
from .forms_b4 import (
    IndicadorANSContractualForm,
    IndicadorMantenimientoFinancieroForm,
    IndicadorMantenimientoTecnicoForm,
)
from .models_b4_mantenimiento_detallado import (
    IndicadorANSContractual,
    IndicadorMantenimientoFinanciero,
    IndicadorMantenimientoTecnico,
)


def _decimal_default(o):
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(f"Object {o!r} not JSON serializable")


# ---------------------------------------------------------------------------
# Dashboard principal
# ---------------------------------------------------------------------------
class DashboardMantenimientoV2View(LoginRequiredMixin, TemplateView):
    """Dashboard 4 secciones + ANS prominente + tendencia 6 meses."""

    template_name = "indicadores/dashboard_mantenimiento_v2.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        try:
            anio = int(self.request.GET.get("anio", hoy.year))
        except (TypeError, ValueError):
            anio = hoy.year
        try:
            mes = int(self.request.GET.get("mes", hoy.month))
        except (TypeError, ValueError):
            mes = hoy.month

        # Filtro opcional por linea (None = agregado del proyecto)
        linea_id = self.request.GET.get("linea") or None
        from apps.lineas.models import Linea

        linea = None
        if linea_id:
            linea = Linea.objects.filter(pk=linea_id).first()

        resumen = resumen_mensual(linea=linea, anio=anio, mes=mes)
        ans = serie_componentes_ans(linea=linea, anio=anio, mes=mes)
        tendencia = tendencia_ans_6_meses(
            linea=linea, hasta=date(anio, mes, 1)
        )

        # Estado al cliente: si no hay ANS del periodo, render placeholder.
        ctx.update(
            {
                "anio": anio,
                "mes": mes,
                "linea": linea,
                "lineas": Linea.objects.filter(activa=True).order_by("codigo"),
                "resumen": resumen,
                "ans_actual": ans,
                "componentes_ans": ans.componentes if ans else [],
                "tendencia_json": json.dumps(
                    tendencia, default=_decimal_default
                ),
                "has_ans": ans is not None,
                "anios": list(range(hoy.year - 2, hoy.year + 1)),
                "meses": [
                    (i, n)
                    for i, n in enumerate(
                        [
                            "Ene",
                            "Feb",
                            "Mar",
                            "Abr",
                            "May",
                            "Jun",
                            "Jul",
                            "Ago",
                            "Sep",
                            "Oct",
                            "Nov",
                            "Dic",
                        ],
                        start=1,
                    )
                ],
            }
        )
        return ctx


# ---------------------------------------------------------------------------
# CRUD Financiero
# ---------------------------------------------------------------------------
class IndicadorMantFinancieroListView(LoginRequiredMixin, ListView):
    model = IndicadorMantenimientoFinanciero
    template_name = "indicadores/indicadores_mantenimiento_financiero_form.html"
    context_object_name = "items"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "list"
        ctx["titulo"] = "Indicadores Mantenimiento Financiero"
        return ctx


class IndicadorMantFinancieroCreateView(LoginRequiredMixin, CreateView):
    model = IndicadorMantenimientoFinanciero
    form_class = IndicadorMantenimientoFinancieroForm
    template_name = "indicadores/indicadores_mantenimiento_financiero_form.html"
    success_url = reverse_lazy("indicadores:mant_fin_list")

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "create"
        ctx["titulo"] = "Nuevo Indicador Financiero"
        return ctx


class IndicadorMantFinancieroUpdateView(LoginRequiredMixin, UpdateView):
    model = IndicadorMantenimientoFinanciero
    form_class = IndicadorMantenimientoFinancieroForm
    template_name = "indicadores/indicadores_mantenimiento_financiero_form.html"
    success_url = reverse_lazy("indicadores:mant_fin_list")

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "edit"
        ctx["titulo"] = "Editar Indicador Financiero"
        return ctx


# ---------------------------------------------------------------------------
# CRUD Tecnico
# ---------------------------------------------------------------------------
class IndicadorMantTecnicoListView(LoginRequiredMixin, ListView):
    model = IndicadorMantenimientoTecnico
    template_name = "indicadores/_tecnico_form.html"
    context_object_name = "items"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "list"
        ctx["titulo"] = "Indicadores Mantenimiento Tecnico"
        return ctx


class IndicadorMantTecnicoCreateView(LoginRequiredMixin, CreateView):
    model = IndicadorMantenimientoTecnico
    form_class = IndicadorMantenimientoTecnicoForm
    template_name = "indicadores/_tecnico_form.html"
    success_url = reverse_lazy("indicadores:mant_tec_list")

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "create"
        ctx["titulo"] = "Nuevo Indicador Tecnico"
        return ctx


class IndicadorMantTecnicoUpdateView(LoginRequiredMixin, UpdateView):
    model = IndicadorMantenimientoTecnico
    form_class = IndicadorMantenimientoTecnicoForm
    template_name = "indicadores/_tecnico_form.html"
    success_url = reverse_lazy("indicadores:mant_tec_list")

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "edit"
        ctx["titulo"] = "Editar Indicador Tecnico"
        return ctx


# ---------------------------------------------------------------------------
# CRUD ANS
# ---------------------------------------------------------------------------
class IndicadorANSListView(LoginRequiredMixin, ListView):
    model = IndicadorANSContractual
    template_name = "indicadores/_ans_form.html"
    context_object_name = "items"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "list"
        ctx["titulo"] = "Indicadores ANS Contractual"
        return ctx


class IndicadorANSCreateView(LoginRequiredMixin, CreateView):
    model = IndicadorANSContractual
    form_class = IndicadorANSContractualForm
    template_name = "indicadores/_ans_form.html"
    success_url = reverse_lazy("indicadores:ans_list")

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "create"
        ctx["titulo"] = "Nuevo Indicador ANS"
        return ctx


class IndicadorANSUpdateView(LoginRequiredMixin, UpdateView):
    model = IndicadorANSContractual
    form_class = IndicadorANSContractualForm
    template_name = "indicadores/_ans_form.html"
    success_url = reverse_lazy("indicadores:ans_list")

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.actualizado_por = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["modo"] = "edit"
        ctx["titulo"] = "Editar Indicador ANS"
        return ctx
