"""Registro y consulta de producción diaria (#252, B1)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from datetime import timedelta

from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from apps.core.mixins import RoleRequiredMixin

from .forms_produccion_diaria import (
    ActividadFormSet,
    MaterialFormSet,
    NovedadFormSet,
    ProduccionDiariaForm,
    RegistroPersonalFormSet,
)
from .models_pc import ProgramacionSemanalCuadrilla
from .models_produccion_diaria import ProduccionDiaria
from .services_produccion_diaria import importar_asistencias

REGISTRO_PRODUCCION_ROLES = ["admin", "coordinador", "supervisor"]
CONSULTA_PRODUCCION_ROLES = REGISTRO_PRODUCCION_ROLES + ["director"]


class ProduccionDiariaCreateView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Persiste cabecera e inlines en una única transacción."""

    template_name = "construccion/produccion_diaria/registro_form.html"
    allowed_roles = REGISTRO_PRODUCCION_ROLES

    def _forms(self, data=None, files=None, initial=None):
        initial = initial or {}
        return {
            "form": ProduccionDiariaForm(data, initial=initial.get("form")),
            "personal_formset": RegistroPersonalFormSet(data, files, prefix="personal", initial=initial.get("personal")),
            "actividad_formset": ActividadFormSet(data, files, prefix="actividad"),
            "novedad_formset": NovedadFormSet(data, files, prefix="novedad"),
            "material_formset": MaterialFormSet(data, files, prefix="material"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(kwargs.get("forms") or self._forms())
        context["titulo"] = "Registrar producción diaria"
        return context

    def get(self, request, *args, **kwargs):
        programacion_id = request.GET.get("programacion")
        fecha_texto = request.GET.get("fecha")
        if not (programacion_id and fecha_texto):
            return super().get(request, *args, **kwargs)
        try:
            fecha = timezone.datetime.fromisoformat(fecha_texto).date()
        except ValueError:
            messages.error(request, "Seleccione una fecha válida para importar asistencia.")
            return super().get(request, *args, **kwargs)
        programacion = get_object_or_404(ProgramacionSemanalCuadrilla, pk=programacion_id)
        try:
            produccion, _, omitidas = importar_asistencias(programacion, fecha, request.user)
        except ValueError as error:
            messages.error(request, str(error))
            return super().get(request, *args, **kwargs)
        if omitidas:
            messages.warning(request, "No se importó personal sin ficha de cuadrilla: " + ", ".join(omitidas))
        return redirect("construccion:produccion_diaria_editar", pk=produccion.pk)

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
    allowed_roles = CONSULTA_PRODUCCION_ROLES

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


class ProduccionDiariaEditView(ProduccionDiariaCreateView):
    """Edita exclusivamente el registro operativo durante 48 h; conserva importación."""

    template_name = "construccion/produccion_diaria/registro_form.html"

    def get_object(self):
        return get_object_or_404(ProduccionDiaria, pk=self.kwargs["pk"])

    def puede_editar(self, produccion):
        if self.request.user.rol == "admin":
            return True
        return timezone.now() <= produccion.created_at + timedelta(hours=48)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.puede_editar(self.object):
            return HttpResponseForbidden("El registro solo puede editarse durante 48 horas.")
        return super().dispatch(request, *args, **kwargs)

    def _forms(self, data=None, files=None, initial=None):
        if data is None:
            return {
                "form": ProduccionDiariaForm(instance=self.object),
                "personal_formset": RegistroPersonalFormSet(instance=self.object, prefix="personal"),
                "actividad_formset": ActividadFormSet(instance=self.object, prefix="actividad"),
                "novedad_formset": NovedadFormSet(instance=self.object, prefix="novedad"),
                "material_formset": MaterialFormSet(instance=self.object, prefix="material"),
            }
        return {
            "form": ProduccionDiariaForm(data, instance=self.object),
            "personal_formset": RegistroPersonalFormSet(data, files, instance=self.object, prefix="personal"),
            "actividad_formset": ActividadFormSet(data, files, instance=self.object, prefix="actividad"),
            "novedad_formset": NovedadFormSet(data, files, instance=self.object, prefix="novedad"),
            "material_formset": MaterialFormSet(data, files, instance=self.object, prefix="material"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Completar producción importada"
        context["produccion"] = self.object
        return context

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 302:
            self.object.ultima_edicion_por = request.user
            self.object.ultima_edicion_en = timezone.now()
            self.object.save(update_fields=["ultima_edicion_por", "ultima_edicion_en", "updated_at"])
        return response
