"""
Forms del módulo Programación / Ejecución semanal de cuadrillas (#155, B2).

`ProgramacionSemanalCuadrillaForm` es un ModelForm sobre
`models_pc.ProgramacionSemanalCuadrilla` (scaffolding S1). Se usa para crear y
editar la programación semanal desde la subsección administrativa de
Construcción.

`EjecucionSemanalCuadrillaForm` lo deja preparado B2 para que B3 lo reutilice en
el guardado inline AJAX (lectura compartida declarada en el BLUEPRINT). Es un
ModelForm mínimo sobre `EjecucionSemanalCuadrilla` (solo `torres_ejecutadas` +
`observaciones`; la FK `programacion` la asigna la vista).

Notas es-CO (lecciones de memoria):
- Los campos numéricos (`anio`, `semana`, `torres_programadas`,
  `torres_ejecutadas`) usan `NumberInput` con enteros — NO hay floats ni fechas,
  así que no aplica el bug de `floatformat`/`input type=date` con coma decimal.
- No se inyecta JSON/float crudo en `x-data`; el form no usa Alpine.
"""
from django import forms

from .models_pc import EjecucionSemanalCuadrilla, ProgramacionSemanalCuadrilla

# Clase Tailwind compartida (espeja apps/construccion/forms.py::INPUT_CLS).
INPUT_CLS = (
    'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 '
    'px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 '
    'bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm'
)


class ProgramacionSemanalCuadrillaForm(forms.ModelForm):
    """Crear/editar una programación semanal de cuadrilla."""

    class Meta:
        model = ProgramacionSemanalCuadrilla
        fields = [
            'cuadrilla', 'proyecto', 'bloque', 'anio', 'semana',
            'torres_programadas', 'actividades_programadas', 'observaciones',
        ]
        widgets = {
            'cuadrilla': forms.Select(attrs={'class': INPUT_CLS}),
            'proyecto': forms.Select(attrs={'class': INPUT_CLS}),
            'bloque': forms.Select(attrs={'class': INPUT_CLS}),
            'anio': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 2000, 'max': 2100, 'step': 1,
                'placeholder': 'Ej: 2026',
            }),
            'semana': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 1, 'max': 53, 'step': 1,
                'placeholder': '1-53',
            }),
            'torres_programadas': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 0, 'step': 1, 'placeholder': '0',
            }),
            'actividades_programadas': forms.Textarea(attrs={
                'class': INPUT_CLS, 'rows': 3,
                'placeholder': 'Actividades planeadas para la semana',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': INPUT_CLS, 'rows': 2,
                'placeholder': 'Observaciones (opcional)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Proyecto es opcional: dejar etiqueta vacía explícita.
        self.fields['proyecto'].required = False
        self.fields['proyecto'].empty_label = '— Sin proyecto —'
        # Ordenar cuadrillas por código para una selección predecible.
        self.fields['cuadrilla'].queryset = (
            self.fields['cuadrilla'].queryset.order_by('codigo')
        )

    def clean_semana(self):
        """Edge case: semana ISO válida (1..53)."""
        semana = self.cleaned_data.get('semana')
        if semana is not None and not (1 <= semana <= 53):
            raise forms.ValidationError(
                'La semana ISO debe estar entre 1 y 53.'
            )
        return semana

    def clean_anio(self):
        """Edge case: año en un rango razonable (evita typos tipo 20226)."""
        anio = self.cleaned_data.get('anio')
        if anio is not None and not (2000 <= anio <= 2100):
            raise forms.ValidationError(
                'El año debe estar entre 2000 y 2100.'
            )
        return anio

    def clean(self):
        """
        Edge case: respetar `unique_together` (cuadrilla, anio, semana) con un
        mensaje de dominio claro en vez del IntegrityError crudo. El ModelForm
        ya valida unique_together, pero personalizamos el mensaje.
        """
        cleaned = super().clean()
        cuadrilla = cleaned.get('cuadrilla')
        anio = cleaned.get('anio')
        semana = cleaned.get('semana')
        if cuadrilla and anio and semana:
            qs = ProgramacionSemanalCuadrilla.objects.filter(
                cuadrilla=cuadrilla, anio=anio, semana=semana,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f'Ya existe una programación para la cuadrilla '
                    f'{cuadrilla} en {anio}-S{semana:02d}.'
                )
        return cleaned


class EjecucionSemanalCuadrillaForm(forms.ModelForm):
    """
    Form de ejecución semanal — preparado por B2 para reuso de B3 (inline AJAX).
    La FK `programacion` la asigna la vista (no se expone en el form).
    """

    class Meta:
        model = EjecucionSemanalCuadrilla
        fields = ['torres_ejecutadas', 'observaciones']
        widgets = {
            'torres_ejecutadas': forms.NumberInput(attrs={
                'class': INPUT_CLS, 'min': 0, 'step': 1,
                'name': 'torres_ejecutadas',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': INPUT_CLS, 'rows': 2,
                'placeholder': 'Observaciones de la ejecución (opcional)',
            }),
        }

    def clean_torres_ejecutadas(self):
        torres = self.cleaned_data.get('torres_ejecutadas')
        if torres is not None and torres < 0:
            raise forms.ValidationError(
                'Las torres ejecutadas no pueden ser negativas.'
            )
        return torres
