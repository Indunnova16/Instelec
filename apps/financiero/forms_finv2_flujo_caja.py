"""Formularios de configuración de la proyección de flujo de caja (#251)."""

from decimal import Decimal

from django import forms

from apps.contratos.models import Contrato


class FlujoCajaFiltroForm(forms.Form):
    contrato = forms.ModelChoiceField(
        queryset=Contrato.objects.none(), required=False, label="Proyecto / contrato"
    )
    horizonte_dias = forms.IntegerField(min_value=1, max_value=365, initial=90, label="Horizonte")
    porcentaje_cobro = forms.DecimalField(
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        initial=Decimal("90"),
        decimal_places=2,
        label="Cobro esperado de facturas emitidas (%)",
    )
    escenario = forms.ChoiceField(
        choices=(("base", "Base"), ("optimista", "Optimista"), ("estres", "Estrés")),
        initial="base",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contrato"].queryset = Contrato.objects.filter(
            estado=Contrato.Estado.ACTIVO
        ).order_by("codigo")
