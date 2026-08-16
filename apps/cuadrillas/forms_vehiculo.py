"""Formulario del maestro de vehículos (issue #226, A2)."""

from django import forms

from .forms_personal import INPUT_CLS
from .models import Vehiculo


class VehiculoForm(forms.ModelForm):
    """Valida y normaliza los datos operativos de un vehículo."""

    class Meta:
        model = Vehiculo
        fields = [
            "placa", "marca", "tipo", "descripcion", "estado", "observaciones",
            "modelo", "ano", "capacidad_personas", "costo_dia",
        ]
        widgets = {
            "placa": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "Ej: ABC123"}),
            "marca": forms.TextInput(attrs={"class": INPUT_CLS, "placeholder": "Ej: Toyota"}),
            "tipo": forms.Select(attrs={"class": INPUT_CLS}),
            "descripcion": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 3}),
            "estado": forms.Select(attrs={"class": INPUT_CLS}),
            "observaciones": forms.Textarea(attrs={"class": INPUT_CLS, "rows": 3}),
            "modelo": forms.TextInput(attrs={"class": INPUT_CLS}),
            "ano": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 1900, "max": 2100}),
            "capacidad_personas": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 1}),
            "costo_dia": forms.NumberInput(attrs={"class": INPUT_CLS, "min": 0, "step": "0.01"}),
        }

    def clean_placa(self):
        placa = (self.cleaned_data.get("placa") or "").strip().upper()
        if not placa:
            raise forms.ValidationError("La placa es obligatoria.")
        qs = Vehiculo.objects.filter(placa__iexact=placa)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Ya existe un vehículo con la placa "{placa}".')
        return placa

    def clean_marca(self):
        marca = (self.cleaned_data.get("marca") or "").strip()
        if not marca:
            raise forms.ValidationError("La marca es obligatoria.")
        return marca

    def clean_capacidad_personas(self):
        capacidad = self.cleaned_data.get("capacidad_personas")
        if capacidad is not None and capacidad < 1:
            raise forms.ValidationError("La capacidad debe ser de al menos una persona.")
        return capacidad
