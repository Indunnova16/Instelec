"""Formularios del registro, pago e importación masiva de facturas de gasto (#248)."""

from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError

from .models import FacturaGasto, PagoFacturaGasto, Presupuesto, Proveedor
from .services_finv2_gastos import calcular_totales, estado_inicial_gasto


class FacturaGastoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True)

    class Meta:
        model = FacturaGasto
        fields = (
            "proveedor",
            "contrato",
            "presupuesto",
            "homologacion",
            "numero_documento",
            "documento",
            "fecha",
            "concepto",
            "categoria",
            "centro_costo",
            "subtotal",
        )
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"})}

    def clean_presupuesto(self):
        presupuesto = self.cleaned_data.get("presupuesto")
        if presupuesto and presupuesto.estado == Presupuesto.Estado.CERRADO:
            raise ValidationError("No se puede afectar un presupuesto cerrado.")
        return presupuesto

    def clean(self):
        cleaned = super().clean()
        subtotal = cleaned.get("subtotal")
        if subtotal:
            try:
                cleaned["totales"] = calcular_totales(subtotal)
            except ValidationError as error:
                self.add_error("subtotal", error)
        return cleaned

    def save(self, commit=True):
        factura = super().save(commit=False)
        totales = self.cleaned_data["totales"]
        factura.subtotal = totales["subtotal"]
        factura.iva = totales["iva"]
        factura.total = totales["total"]
        factura.estado = estado_inicial_gasto(factura.total)
        if not factura.fecha_vencimiento and factura.fecha:
            # #248: el checklist pide alertar "próximas a vencer" pero el
            # modelo no tenía ese campo -- supuesto documentado (30 días
            # desde la fecha de factura), ver models_finv2_facturas.py.
            factura.fecha_vencimiento = factura.fecha + timedelta(days=30)
        if commit:
            factura.save()
            self.save_m2m()
        return factura


class ImportarFacturasGastoForm(forms.Form):
    """Sube el archivo de carga masiva (#248 sección 5 del checklist)."""

    archivo = forms.FileField(label="Archivo CSV o XLSX")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = archivo.name.lower()
        if not (nombre.endswith(".csv") or nombre.endswith(".xlsx")):
            raise ValidationError("El archivo debe ser CSV UTF-8 o XLSX.")
        return archivo


class PagoFacturaGastoForm(forms.ModelForm):
    class Meta:
        model = PagoFacturaGasto
        fields = ("banco", "metodo_pago", "fecha", "monto", "referencia")
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"})}

    def clean_referencia(self):
        referencia = (self.cleaned_data.get("referencia") or "").strip()
        if not referencia:
            raise ValidationError("La referencia de pago es obligatoria.")
        return referencia
