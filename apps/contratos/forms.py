from django import forms

from .models import Contrato


class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        fields = [
            'unidad_negocio', 'codigo', 'nombre', 'cliente',
            'objeto', 'valor', 'fecha_inicio', 'fecha_fin',
            'estado', 'observaciones',
        ]
        widgets = {
            'unidad_negocio': forms.Select(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'}),
            'codigo': forms.TextInput(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'}),
            'nombre': forms.TextInput(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'}),
            'cliente': forms.TextInput(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'}),
            'objeto': forms.Textarea(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full', 'rows': 3}),
            'valor': forms.NumberInput(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full', 'step': '0.01'}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'}),
            'estado': forms.Select(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full'}),
            'observaciones': forms.Textarea(attrs={'class': 'rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white w-full', 'rows': 3}),
        }
