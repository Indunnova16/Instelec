from django import forms

from .models import Contrato


CSS = 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'


class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        fields = [
            'unidad_negocio', 'codigo', 'nombre', 'cliente',
            'objeto', 'valor', 'fecha_inicio', 'fecha_fin',
            'estado', 'observaciones',
            'tipo_contrato', 'plazo_ejecucion', 'longitud_linea', 'numero_torres', 'acta_inicio',
        ]
        widgets = {
            'unidad_negocio': forms.Select(attrs={'class': CSS}),
            'codigo': forms.TextInput(attrs={'class': CSS}),
            'nombre': forms.TextInput(attrs={'class': CSS}),
            'cliente': forms.TextInput(attrs={'class': CSS}),
            'objeto': forms.Textarea(attrs={'class': CSS, 'rows': 3}),
            'valor': forms.NumberInput(attrs={'class': CSS, 'step': '0.01'}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': CSS}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': CSS}),
            'estado': forms.Select(attrs={'class': CSS}),
            'observaciones': forms.Textarea(attrs={'class': CSS, 'rows': 3}),
            'tipo_contrato': forms.Select(attrs={'class': CSS}),
            'plazo_ejecucion': forms.NumberInput(attrs={'class': CSS, 'placeholder': 'Ej: 180'}),
            'longitud_linea': forms.NumberInput(attrs={'class': CSS, 'step': '0.01', 'placeholder': 'Ej: 42.5'}),
            'numero_torres': forms.NumberInput(attrs={'class': CSS, 'placeholder': 'Ej: 64', 'min': '1'}),
            'acta_inicio': forms.ClearableFileInput(attrs={'class': CSS}),
        }
