"""Registro y consulta de producción diaria (#252, B1)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.views.generic import DetailView, TemplateView

from apps.core.mixins import RoleRequiredMixin

from .forms_produccion_diaria import (
    ActividadFormSet,
    MaterialFormSet,
    NovedadFormSet,
    ProduccionDiariaForm,
    RegistroPersonalFormSet,
)
from .models_produccion_diaria import ProduccionDiaria

REGISTRO_PRODUCCION_ROLES = ["admin", "director", "coordinador", "supervisor"]


class ProduccionDiariaCreateView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Persiste cabecera e inlines en una única transacción."""

    template_name = "construccion/produccion_diaria/registro_form.html"
    allowed_roles = REGISTRO_PRODUCCION_ROLES

    def _forms(self, data=None, files=None):
        return {
            "form": ProduccionDiariaForm(data),
            "personal_formset": RegistroPersonalFormSet(data, files, prefix="personal"),
            "actividad_formset": ActividadFormSet(data, files, prefix="actividad"),
            "novedad_formset": NovedadFormSet(data, files, prefix="novedad"),
            "material_formset": MaterialFormSet(data, files, prefix="material"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(kwargs.get("forms") or self._forms())
        context["titulo"] = "Registrar producción diaria"
        return context

    def post(self, request, *args, **kwargs):
        forms = self._forms(request.POST, request.FILES)
        if not all(item.is_valid() for item in forms.values()):
            messages.error(request, "Revise los datos marcados antes de guardar el registro.")
            return self.render_to_response(self.get_context_data(forms=forms), status=400)
        try:
            with transaction.atomic():
                produccion = forms["form"].save(commit=False)
                produccion.registrado_por = request.user
                produccion.save()
                for key in (
                    "personal_formset",
                    "actividad_formset",
                    "novedad_formset",
                    "material_formset",
                ):
                    formset = forms[key]
                    formset.instance = produccion
                    formset.save()
        except IntegrityError:
            forms["form"].add_error(None, "Ya existe un registro para esta programación y fecha.")
            return self.render_to_response(self.get_context_data(forms=forms), status=400)
        messages.success(request, "Producción diaria registrada correctamente.")
        return self.redirect_to_detail(produccion)

    def redirect_to_detail(self, produccion):
        from django.shortcuts import redirect

        return redirect("construccion:produccion_diaria_detalle", pk=produccion.pk)


class ProduccionDiariaDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    template_name = "construccion/produccion_diaria/registro_detail.html"
    context_object_name = "produccion"
    allowed_roles = REGISTRO_PRODUCCION_ROLES

    def get_queryset(self):
        return ProduccionDiaria.objects.select_related(
            "programacion", "programacion__cuadrilla", "registrado_por"
        ).prefetch_related("registros_personal__personal", "actividades", "novedades", "materiales")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["costo_materiales"] = sum(
            (material.costo_estimado for material in self.object.materiales.all()), start=0
        )
        return context
