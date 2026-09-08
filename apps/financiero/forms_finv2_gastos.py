"""Formularios del registro y pago de facturas de gasto (#248)."""
from django import forms
from django.core.exceptions import ValidationError

from .models import FacturaGasto, PagoFacturaGasto, Presupuesto
from .services_finv2_gastos import calcular_totales, estado_inicial_gasto


class FacturaGastoForm(forms.ModelForm):
    class Meta:
        model = FacturaGasto
        fields = ('proveedor', 'contrato', 'presupuesto', 'homologacion', 'numero_documento',
                  'documento', 'fecha', 'concepto', 'categoria', 'centro_costo', 'subtotal')
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'})}

    def clean_presupuesto(self):
        presupuesto = self.cleaned_data.get('presupuesto')
        if presupuesto and presupuesto.estado == Presupuesto.Estado.CERRADO:
            raise ValidationError('No se puede afectar un presupuesto cerrado.')
        return presupuesto

    def clean(self):
        cleaned = super().clean()
        subtotal = cleaned.get('subtotal')
        if subtotal:
            try:
                cleaned['totales'] = calcular_totales(subtotal)
            except ValidationError as error:
                self.add_error('subtotal', error)
        return cleaned

    def save(self, commit=True):
        factura = super().save(commit=False)
        totales = self.cleaned_data['totales']
        factura.subtotal = totales['subtotal']
        factura.iva = totales['iva']
        factura.total = totales['total']
        factura.estado = estado_inicial_gasto(factura.total)
        if commit:
            factura.save()
            self.save_m2m()
        return factura


class PagoFacturaGastoForm(forms.ModelForm):
    class Meta:
        model = PagoFacturaGasto
        fields = ('banco', 'metodo_pago', 'fecha', 'monto', 'referencia')
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'})}

    def clean_referencia(self):
        referencia = (self.cleaned_data.get('referencia') or '').strip()
        if not referencia:
            raise ValidationError('La referencia de pago es obligatoria.')
        return referencia
