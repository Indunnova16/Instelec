"""Vistas operativas de conciliación bancaria (#250)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import FormView, ListView

from apps.core.mixins import RoleRequiredMixin

from .forms_finv2_conciliacion import ImportarMovimientosCsvForm, OverrideConciliacionForm
from .models import ConciliacionBancaria
from .services_finv2_conciliacion import aplicar_override, importar_movimientos_csv


class ConciliacionImportarView(LoginRequiredMixin, RoleRequiredMixin, FormView):
    template_name = "financiero/conciliacion_importar.html"
    form_class = ImportarMovimientosCsvForm
    allowed_roles = ["tesoreria", "contador"]

    def form_valid(self, form):
        try:
            resultado = importar_movimientos_csv(form.cleaned_data["archivo"])
        except ValidationError as error:
            form.add_error("archivo", error)
            return self.form_invalid(form)
        messages.success(
            self.request, f"Importación completada: {resultado['creados']} movimiento(s) creado(s)."
        )
        if resultado["duplicados"]:
            messages.warning(
                self.request,
                f"Se omitieron {resultado['duplicados']} movimiento(s) ya importado(s).",
            )
        return redirect("financiero:conciliacion_pendientes")


class MovimientosPendientesView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = "financiero/conciliacion_pendientes.html"
    context_object_name = "conciliaciones"
    allowed_roles = ["tesoreria", "contador"]

    def get_queryset(self):
        return ConciliacionBancaria.objects.select_related(
            "movimiento", "movimiento__banco", "factura_gasto", "ciclo_ingreso", "usuario_override"
        ).exclude(estado=ConciliacionBancaria.Estado.CONCILIADA)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["override_form"] = kwargs.get("override_form", OverrideConciliacionForm())
        return context

    def post(self, request, *args, **kwargs):
        conciliacion = get_object_or_404(
            ConciliacionBancaria, pk=request.POST.get("conciliacion_id")
        )
        form = OverrideConciliacionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(override_form=form))
        try:
            aplicar_override(conciliacion, usuario=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
            return self.render_to_response(self.get_context_data(override_form=form))
        messages.success(
            request, "La conciliación fue actualizada con trazabilidad de usuario, fecha y motivo."
        )
        return redirect(reverse("financiero:conciliacion_pendientes"))
