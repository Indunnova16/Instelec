"""
Forms financiero v2 — B1 (#120).
"""
from django import forms

from .importers_finv2 import MAX_UPLOAD_BYTES
from .models_finv2_mapeo import MapeoCtaRubro


class CargarBDContableForm(forms.Form):
    """Form de carga del archivo 'BASE DE DATOS.xlsx' (pestaña 1)."""

    archivo = forms.FileField(
        label='Archivo Excel (.xlsx)',
        help_text=(
            'Suba archivo con transacciones contables. Los datos se agruparán '
            'por cuenta (columna O). Máximo 20 MB.'
        ),
        widget=forms.ClearableFileInput(attrs={
            'accept': '.xlsx',
            'class': (
                'block w-full text-sm text-gray-500 dark:text-gray-400 '
                'file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 '
                'file:text-sm file:font-semibold file:bg-blue-50 '
                'file:text-blue-700 hover:file:bg-blue-100 '
                'dark:file:bg-gray-700 dark:file:text-gray-300'
            ),
        }),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        nombre = (getattr(archivo, 'name', '') or '').lower()
        if not nombre.endswith('.xlsx'):
            raise forms.ValidationError(
                'Archivo inválido. Verifique que sea .xlsx con estructura '
                'correcta.'
            )
        if getattr(archivo, 'size', 0) > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                'El archivo excede el tamaño máximo (20 MB).'
            )
        return archivo


class MapeoCtaRubroForm(forms.ModelForm):
    """Form para el CRUD inline de mapeos cuenta → rubro (pestaña 2)."""

    class Meta:
        model = MapeoCtaRubro
        fields = ['cta_equivalente', 'rubro_presupuestal', 'activo']
        widgets = {
            'cta_equivalente': forms.TextInput(attrs={
                'class': (
                    'w-full rounded-lg border-gray-300 dark:border-gray-600 '
                    'dark:bg-gray-800 dark:text-white text-sm'
                ),
                'placeholder': 'Ej: Ingresos Operacionales',
            }),
            'rubro_presupuestal': forms.TextInput(attrs={
                'class': (
                    'w-full rounded-lg border-gray-300 dark:border-gray-600 '
                    'dark:bg-gray-800 dark:text-white text-sm'
                ),
                'placeholder': 'Ej: Líneas de Transmisión',
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'rounded border-gray-300 text-blue-600',
            }),
        }

    def clean_cta_equivalente(self):
        return (self.cleaned_data['cta_equivalente'] or '').strip()

    def clean_rubro_presupuestal(self):
        return (self.cleaned_data['rubro_presupuestal'] or '').strip()
