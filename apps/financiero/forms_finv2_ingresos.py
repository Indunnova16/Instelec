"""Formularios para emitir y cobrar facturas de ingreso (#249)."""

from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from .models import CicloFacturacion, LineaFacturaIngreso, PagoFacturaIngreso


class FacturaIngresoForm(forms.ModelForm):
    class Meta:
        model = CicloFacturacion
        fields = (
            "presupuesto",
            "cliente",
            "fecha_factura",
            "plazo_pago_dias",
            "referencia_cobro",
            "observaciones",
        )
        widgets = {"fecha_factura": forms.DateInput(attrs={"type": "date"})}

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("cliente"):
            self.add_error("cliente", "Seleccione el cliente al que se emitirá la factura.")
        if not cleaned.get("fecha_factura"):
            self.add_error("fecha_factura", "La fecha de emisión es obligatoria.")
        return cleaned


class LineaFacturaIngresoForm(forms.ModelForm):
    class Meta:
        model = LineaFacturaIngreso
        fields = ("descripcion", "cantidad", "valor_unitario")

    def clean(self):
        cleaned = super().clean()
        cantidad, valor = cleaned.get("cantidad"), cleaned.get("valor_unitario")
        if cantidad is not None and cantidad <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor que cero.")
        if valor is not None and valor < 0:
            self.add_error("valor_unitario", "El valor unitario no puede ser negativo.")
        return cleaned


LineaFacturaIngresoFormSet = inlineformset_factory(
    CicloFacturacion,
    LineaFacturaIngreso,
    form=LineaFacturaIngresoForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class PagoFacturaIngresoForm(forms.ModelForm):
    class Meta:
        model = PagoFacturaIngreso
        fields = ("banco", "metodo_pago", "fecha", "monto", "referencia")
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, saldo=Decimal("0.00"), **kwargs):
        super().__init__(*args, **kwargs)
        self.saldo = saldo

    def clean_monto(self):
        monto = self.cleaned_data["monto"]
        if monto <= 0:
            raise forms.ValidationError("El pago debe ser mayor que cero.")
        if monto > self.saldo:
            raise forms.ValidationError("El pago no puede exceder el saldo pendiente.")
        return monto
