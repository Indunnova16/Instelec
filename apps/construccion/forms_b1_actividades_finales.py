"""B1 — Forms para ActividadFinalTorre.

El form se usa en (a) las vistas de detalle clásicas y (b) en validación
auxiliar de los toggles HTMX. Las reglas de progresión las hace el `clean()`
del modelo — no se duplican aquí.
"""
from django import forms

from .models_b1_actividades_finales import ACTIVIDAD_CAMPOS, ActividadFinalTorre


class ActividadFinalTorreForm(forms.ModelForm):
    class Meta:
        model = ActividadFinalTorre
        fields = ACTIVIDAD_CAMPOS + ['observaciones']
        widgets = {
            'observaciones': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full rounded-lg border border-gray-300 dark:border-gray-600 '
                         'dark:bg-gray-700 dark:text-white text-sm focus:ring-2 '
                         'focus:ring-blue-500 focus:border-blue-500',
            }),
        }


class ActividadToggleForm(forms.Form):
    """Form mínimo para los HTMX toggles. Acepta `campo` y `valor`."""
    campo = forms.ChoiceField(choices=[(c, c) for c in ACTIVIDAD_CAMPOS])
    valor = forms.BooleanField(required=False)
