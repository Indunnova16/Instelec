"""Formularios del flujo de importación y corrección de conciliación (#250)."""

from django import forms
from django.core.exceptions import ValidationError

from .models import FacturaGasto
from .models_base import CicloFacturacion


class ImportarMovimientosCsvForm(forms.Form):
    archivo = forms.FileField(label="Archivo CSV")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".csv"):
            raise ValidationError("El extracto debe ser un archivo CSV.")
        if archivo.size == 0:
            raise ValidationError("El archivo CSV está vacío.")
        if archivo.size > 5 * 1024 * 1024:
            raise ValidationError("El archivo CSV supera el máximo de 5 MB.")
        return archivo


class OverrideConciliacionForm(forms.Form):
    accion = forms.ChoiceField(
        choices=(
            ("confirmar", "Confirmar match"),
            ("deshacer", "Deshacer conciliación"),
            ("redirigir", "Redirigir manualmente"),
        ),
        widget=forms.HiddenInput,
    )
    factura_gasto = forms.ModelChoiceField(
        queryset=FacturaGasto.objects.none(), required=False, empty_label="Seleccione gasto"
    )
    ciclo_ingreso = forms.ModelChoiceField(
        queryset=CicloFacturacion.objects.none(), required=False, empty_label="Seleccione ingreso"
    )
    motivo_override = forms.CharField(max_length=1000, required=False, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["factura_gasto"].queryset = FacturaGasto.objects.order_by("-fecha")
        self.fields["ciclo_ingreso"].queryset = CicloFacturacion.objects.order_by("-created_at")

    def clean(self):
        cleaned = super().clean()
        accion = cleaned.get("accion")
        gasto = cleaned.get("factura_gasto")
        ingreso = cleaned.get("ciclo_ingreso")
        motivo = (cleaned.get("motivo_override") or "").strip()
        if accion == "redirigir":
            if bool(gasto) == bool(ingreso):
                raise ValidationError("Seleccione exactamente una factura de gasto o de ingreso.")
            if not motivo:
                self.add_error("motivo_override", "El motivo es obligatorio al redirigir.")
        return cleaned
