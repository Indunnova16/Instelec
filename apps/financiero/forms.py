"""
Forms for financial management.
"""
from django import forms

from .models import ChecklistFacturacion, Presupuesto


TAILWIND_INPUT = (
    'w-full rounded-lg border-gray-300 dark:border-gray-600 '
    'dark:bg-gray-700 dark:text-white text-sm'
)

MONEY_INPUT = (
    'w-full rounded-lg border-gray-300 dark:border-gray-600 '
    'dark:bg-gray-700 dark:text-white text-sm text-right'
)


class PresupuestoForm(forms.ModelForm):
    """Form for creating/editing a Presupuesto with all 6 budget pillars."""

    class Meta:
        model = Presupuesto
        fields = [
            'anio', 'mes', 'linea', 'estado',
            'dias_hombre_planeados', 'costo_dias_hombre',
            'dias_vehiculo_planeados', 'costo_vehiculos',
            'viaticos_planeados',
            'costo_herramientas', 'costo_ambientales',
            'costo_subcontratistas', 'costo_transporte',
            'costo_materiales', 'costo_garantia',
            'otros_costos',
            'total_presupuestado', 'total_ejecutado',
            'facturacion_esperada',
            'observaciones',
        ]
        widgets = {
            'anio': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': 2020, 'max': 2050}),
            'mes': forms.Select(
                choices=[(i, m) for i, m in enumerate(
                    ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
                    start=0
                ) if i > 0],
                attrs={'class': TAILWIND_INPUT},
            ),
            'linea': forms.Select(attrs={'class': TAILWIND_INPUT}),
            'estado': forms.Select(attrs={'class': TAILWIND_INPUT}),
            'dias_hombre_planeados': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': 0}),
            'costo_dias_hombre': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'dias_vehiculo_planeados': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'min': 0}),
            'costo_vehiculos': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'viaticos_planeados': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'costo_herramientas': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'costo_ambientales': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'costo_subcontratistas': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'costo_transporte': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'costo_materiales': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'costo_garantia': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'otros_costos': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'total_presupuestado': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01', 'readonly': 'readonly'}),
            'total_ejecutado': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'facturacion_esperada': forms.NumberInput(attrs={'class': MONEY_INPUT, 'min': 0, 'step': '0.01'}),
            'observaciones': forms.Textarea(attrs={'class': TAILWIND_INPUT, 'rows': 3}),
        }


class ChecklistEditForm(forms.ModelForm):
    """Inline edit form for numero_factura and observaciones."""

    class Meta:
        model = ChecklistFacturacion
        fields = ['numero_factura', 'observaciones']
        widgets = {
            'numero_factura': forms.TextInput(attrs={
                'class': TAILWIND_INPUT,
                'placeholder': 'Ej: FV-2026-001',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': TAILWIND_INPUT,
                'rows': 3,
                'placeholder': 'Observaciones de facturacion...',
            }),
        }


class ArchivoPeriodoForm(forms.Form):
    """File upload form for period-level attachments."""

    descripcion = forms.CharField(
        label='Descripcion',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': 'Ej: Factura mensual enero 2026',
        }),
    )
