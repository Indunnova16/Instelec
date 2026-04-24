"""
Forms for transmission lines and towers.
"""
from django import forms
from .models import Torre


class TorreForm(forms.ModelForm):
    """
    Form for creating/editing towers.
    Only shows the fields: numero, tipo, municipio, observaciones
    """

    class Meta:
        model = Torre
        fields = ['numero', 'tipo', 'municipio', 'observaciones']
        widgets = {
            'numero': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'placeholder': 'Ej: T-001',
                'required': True
            }),
            'tipo': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'required': True
            }),
            'municipio': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'placeholder': 'Ej: Bogotá'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': 4,
                'placeholder': 'Añada cualquier observación importante...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make observaciones optional explicitly
        self.fields['observaciones'].required = False
        self.fields['municipio'].required = False


class TorreMasivaForm(forms.Form):
    """Form for creating multiple towers at once."""
    cantidad = forms.IntegerField(
        label='Cantidad de Torres',
        min_value=1,
        max_value=10000,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            'placeholder': 'Ej: 10',
            'required': True
        })
    )
    numero_inicial = forms.CharField(
        label='Número Inicial',
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            'placeholder': 'Ej: T-001',
            'required': True
        })
    )
    tipo = forms.ChoiceField(
        label='Tipo de Torre',
        choices=Torre.TipoTorre.choices,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            'required': True
        })
    )
    municipio = forms.CharField(
        label='Municipio',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            'placeholder': 'Ej: Bogotá'
        })
    )
