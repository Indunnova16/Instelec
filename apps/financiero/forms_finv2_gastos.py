"""Formularios del registro, pago e importación masiva de facturas de gasto (#248)."""

from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError

from .models import CargaFinanciera, FacturaGasto, PagoFacturaGasto, Presupuesto, Proveedor
from .services_finv2_gastos import (
    calcular_totales,
    cargas_elegibles_para_generar_gastos,
    estado_inicial_gasto,
)


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


class GenerarFacturasGastoForm(forms.Form):
    """Selecciona la `CargaFinanciera` (proyecto+período) origen (#248).

    Reemplaza `ImportarFacturasGastoForm`: en vez de subir un archivo con
    columnas propias, las facturas de gasto se generan 1:1 desde las líneas
    YA cargadas y homologadas por #246 (`LineaCargaFinanciera`, tipo=REAL) --
    ver PLAN_2026-09-23_248_facturas_gasto_desde_carga_financiera.md.
    """

    carga_financiera = forms.ModelChoiceField(
        queryset=CargaFinanciera.objects.none(),
        label="Carga financiera (proyecto y período)",
        empty_label="Seleccione una carga procesada con líneas reales",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["carga_financiera"].queryset = cargas_elegibles_para_generar_gastos()


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
