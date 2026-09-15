"""Formularios para emitir y cobrar facturas de ingreso (#249)."""

from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from .models import CicloFacturacion, Cliente, LineaFacturaIngreso, PagoFacturaIngreso, Presupuesto
from apps.contratos.models import Contrato


class FacturaIngresoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        clientes = Cliente.objects.filter(activo=True)
        if self.instance and self.instance.cliente_id:
            clientes = Cliente.objects.filter(pk=self.instance.cliente_id) | clientes
        self.fields["cliente"].queryset = clientes.distinct()
        self.fields["proyecto"].queryset = self.proyectos_compatibles()
        self.fields["presupuesto"].queryset = self.presupuestos_compatibles()

    def presupuestos_compatibles(self):
        cliente_id = self.data.get(self.add_prefix("cliente")) or self.initial.get("cliente")
        proyecto_id = self.data.get(self.add_prefix("proyecto")) or self.initial.get("proyecto")
        fecha = self.data.get(self.add_prefix("fecha_factura"))
        queryset = Presupuesto.objects.none()
        if cliente_id and proyecto_id:
            queryset = Presupuesto.objects.filter(cliente_id=cliente_id, proyecto_id=proyecto_id)
            if fecha:
                try:
                    anio, mes = map(int, fecha.split("-")[:2])
                    queryset = queryset.filter(anio=anio, mes=mes)
                except (TypeError, ValueError):
                    pass
        return queryset.select_related("linea", "proyecto")

    def proyectos_compatibles(self):
        cliente_id = self.data.get(self.add_prefix("cliente")) or self.initial.get("cliente")
        if not cliente_id:
            return Contrato.objects.none()
        cliente = Cliente.objects.filter(pk=cliente_id, activo=True).first()
        if not cliente:
            return Contrato.objects.none()
        return Contrato.objects.filter(
            estado=Contrato.Estado.ACTIVO, cliente__iexact=cliente.nombre
        )
    class Meta:
        model = CicloFacturacion
        fields = (
            "cliente",
            "proyecto",
            "fecha_factura",
            "presupuesto",
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
        if not cleaned.get("proyecto"):
            self.add_error("proyecto", "Seleccione el proyecto de la factura.")
        elif cleaned.get("cliente") and cleaned["proyecto"].cliente.casefold() != cleaned["cliente"].nombre.casefold():
            self.add_error("proyecto", "El proyecto debe pertenecer al cliente seleccionado.")
        presupuesto = cleaned.get("presupuesto")
        if presupuesto and (
            presupuesto.cliente_id != getattr(cleaned.get("cliente"), "pk", None)
            or presupuesto.proyecto_id != getattr(cleaned.get("proyecto"), "pk", None)
            or presupuesto.anio != cleaned["fecha_factura"].year
            or presupuesto.mes != cleaned["fecha_factura"].month
        ):
            self.add_error("presupuesto", "Seleccione un presupuesto compatible con cliente, proyecto y período.")
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
        if valor is not None and valor <= 0:
            self.add_error("valor_unitario", "El valor unitario debe ser mayor que cero.")
        return cleaned


LineaFacturaIngresoFormSet = inlineformset_factory(
    CicloFacturacion,
    LineaFacturaIngreso,
    form=LineaFacturaIngresoForm,
    extra=1,
    min_num=1,
    max_num=20,
    validate_min=True,
    validate_max=True,
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
