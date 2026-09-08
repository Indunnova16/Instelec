"""Formularios del registro operativo de producción diaria (#252)."""

from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from .forms_pc import INPUT_CLS
from .models_produccion_diaria import (
    ActividadProduccion,
    MaterialProduccion,
    NovedadProduccion,
    ProduccionDiaria,
    RegistroPersonalProduccion,
)


class ProduccionDiariaForm(forms.ModelForm):
    """Cabecera del reporte; la fecha debe pertenecer a la semana programada."""

    class Meta:
        model = ProduccionDiaria
        fields = ("programacion", "fecha", "calidad_trabajo", "observaciones")
        widgets = {
            "programacion": forms.Select(attrs={"class": INPUT_CLS}),
            "fecha": forms.DateInput(attrs={"class": INPUT_CLS, "type": "date"}),
            "calidad_trabajo": forms.Select(attrs={"class": INPUT_CLS}),
            "observaciones": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        programacion = cleaned.get("programacion")
        fecha = cleaned.get("fecha")
        if programacion and fecha:
            iso = fecha.isocalendar()
            if (iso.year, iso.week) != (programacion.anio, programacion.semana):
                raise forms.ValidationError(
                    "La fecha debe pertenecer a la semana ISO de la programación."
                )
        return cleaned


class RegistroPersonalProduccionForm(forms.ModelForm):
    class Meta:
        model = RegistroPersonalProduccion
        fields = ("personal", "horas_trabajadas", "motivo_ausencia", "observacion")
        widgets = {
            "personal": forms.Select(attrs={"class": INPUT_CLS}),
            "horas_trabajadas": forms.NumberInput(
                attrs={"class": INPUT_CLS, "min": 0, "max": 24, "step": "0.25"}
            ),
            "motivo_ausencia": forms.Select(attrs={"class": INPUT_CLS}),
            "observacion": forms.TextInput(attrs={"class": INPUT_CLS}),
        }

    def clean_horas_trabajadas(self):
        horas = self.cleaned_data.get("horas_trabajadas")
        if horas is not None and not Decimal("0") <= horas <= Decimal("24"):
            raise forms.ValidationError("Las horas trabajadas deben estar entre 0 y 24.")
        return horas

    def clean(self):
        cleaned = super().clean()
        horas = cleaned.get("horas_trabajadas")
        motivo = cleaned.get("motivo_ausencia")
        if horas == 0 and not motivo:
            self.add_error("motivo_ausencia", "Indique el motivo de ausencia si no hubo horas.")
        if horas and motivo:
            self.add_error("motivo_ausencia", "No indique ausencia cuando hubo horas trabajadas.")
        return cleaned


class ActividadProduccionForm(forms.ModelForm):
    class Meta:
        model = ActividadProduccion
        fields = ("descripcion", "avance_pct", "observacion")
        widgets = {
            "descripcion": forms.TextInput(attrs={"class": INPUT_CLS}),
            "avance_pct": forms.NumberInput(
                attrs={"class": INPUT_CLS, "min": 0, "max": 100, "step": "0.01"}
            ),
            "observacion": forms.TextInput(attrs={"class": INPUT_CLS}),
        }

    def clean_avance_pct(self):
        avance = self.cleaned_data.get("avance_pct")
        if avance is not None and not Decimal("0") <= avance <= Decimal("100"):
            raise forms.ValidationError("El avance debe estar entre 0% y 100%.")
        return avance


class NovedadProduccionForm(forms.ModelForm):
    class Meta:
        model = NovedadProduccion
        fields = ("tipo", "descripcion", "foto")
        widgets = {
            "tipo": forms.Select(attrs={"class": INPUT_CLS}),
            "descripcion": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 2}),
            "foto": forms.ClearableFileInput(attrs={"class": INPUT_CLS, "accept": "image/*"}),
        }

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if (
            foto
            and getattr(foto, "content_type", "")
            and not foto.content_type.startswith("image/")
        ):
            raise forms.ValidationError("La evidencia adjunta debe ser una imagen.")
        return foto


class MaterialProduccionForm(forms.ModelForm):
    class Meta:
        model = MaterialProduccion
        fields = ("descripcion", "cantidad", "costo_unitario_estimado")
        widgets = {
            "descripcion": forms.TextInput(attrs={"class": INPUT_CLS}),
            "cantidad": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 0.01, "step": "0.01"}),
            "costo_unitario_estimado": forms.NumberInput(
                attrs={"class": INPUT_CLS, "min": 0, "step": "0.01"}
            ),
        }

    def clean_cantidad(self):
        cantidad = self.cleaned_data.get("cantidad")
        if cantidad is not None and cantidad <= 0:
            raise forms.ValidationError("La cantidad de material debe ser mayor que cero.")
        return cantidad

    def clean_costo_unitario_estimado(self):
        costo = self.cleaned_data.get("costo_unitario_estimado")
        if costo is not None and costo < 0:
            raise forms.ValidationError("El costo unitario no puede ser negativo.")
        return costo


RegistroPersonalFormSet = inlineformset_factory(
    ProduccionDiaria,
    RegistroPersonalProduccion,
    form=RegistroPersonalProduccionForm,
    extra=1,
    can_delete=True,
)
ActividadFormSet = inlineformset_factory(
    ProduccionDiaria,
    ActividadProduccion,
    form=ActividadProduccionForm,
    extra=1,
    can_delete=True,
)
NovedadFormSet = inlineformset_factory(
    ProduccionDiaria,
    NovedadProduccion,
    form=NovedadProduccionForm,
    extra=1,
    can_delete=True,
)
MaterialFormSet = inlineformset_factory(
    ProduccionDiaria,
    MaterialProduccion,
    form=MaterialProduccionForm,
    extra=1,
    can_delete=True,
)
