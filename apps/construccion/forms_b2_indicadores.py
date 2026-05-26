"""Forms B2 — Indicadores Construcción (#98)."""
from django import forms

from .models_b2_indicadores import (
    IndicadorFinancieroConstruccion,
    IndicadorTecnicoConstruccion,
    IndicadorDesempenoLinea,
)


INPUT_CLS = ('mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 '
             'px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 '
             'bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm')


class IndicadorFinancieroForm(forms.ModelForm):
    """Form para crear/editar IndicadorFinancieroConstruccion.

    Los campos derivados (margen_operativo, desviacion_presupuestal) NO se
    incluyen en el form — se auto-calculan en save() del modelo.
    """

    class Meta:
        model = IndicadorFinancieroConstruccion
        fields = [
            'fecha',
            'ingresos_ejecutados', 'costos_directos', 'gastos',
            'costo_real', 'costo_presupuestado',
            'observaciones',
        ]
        widgets = {
            'fecha': forms.DateInput(format='%Y-%m-%d', attrs={'class': INPUT_CLS, 'type': 'date'}),
            'ingresos_ejecutados': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'costos_directos': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'gastos': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'costo_real': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'costo_presupuestado': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        ie = cleaned.get('ingresos_ejecutados')
        cp = cleaned.get('costo_presupuestado')
        if ie is not None and ie < 0:
            self.add_error('ingresos_ejecutados', 'No puede ser negativo.')
        if cp is not None and cp < 0:
            self.add_error('costo_presupuestado', 'No puede ser negativo.')
        return cleaned


class IndicadorTecnicoForm(forms.ModelForm):
    """Form para crear/editar IndicadorTecnicoConstruccion."""

    class Meta:
        model = IndicadorTecnicoConstruccion
        fields = [
            'fecha',
            'presupuesto_ejecutado_pct', 'presupuesto_planeado_pct',
            'obra_ejecutada', 'obra_programada',
            'actividades_completadas', 'actividades_planificadas',
            'cantidad_ejecutada', 'horas_hombre',
            'observaciones',
        ]
        widgets = {
            'fecha': forms.DateInput(format='%Y-%m-%d', attrs={'class': INPUT_CLS, 'type': 'date'}),
            'presupuesto_ejecutado_pct': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'presupuesto_planeado_pct': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'obra_ejecutada': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'obra_programada': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'actividades_completadas': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '1', 'min': '0'}),
            'actividades_planificadas': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '1', 'min': '0'}),
            'cantidad_ejecutada': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'horas_hombre': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        ac = cleaned.get('actividades_completadas') or 0
        ap = cleaned.get('actividades_planificadas') or 0
        if ap and ac > ap:
            self.add_error('actividades_completadas',
                          'No puede ser mayor que actividades planificadas.')
        return cleaned


class IndicadorDesempenoLineaForm(forms.ModelForm):
    """Form para crear/editar IndicadorDesempenoLinea.

    El campo 'estado' NO se incluye — se auto-clasifica en save().
    """

    class Meta:
        model = IndicadorDesempenoLinea
        fields = [
            'fecha', 'linea', 'cuadrilla', 'tipo_trabajo', 'unidad',
            'rendimiento', 'meta', 'actual', 'observaciones',
        ]
        widgets = {
            'fecha': forms.DateInput(format='%Y-%m-%d', attrs={'class': INPUT_CLS, 'type': 'date'}),
            'linea': forms.Select(attrs={'class': INPUT_CLS}),
            'cuadrilla': forms.Select(attrs={'class': INPUT_CLS}),
            'tipo_trabajo': forms.Select(attrs={'class': INPUT_CLS}),
            'unidad': forms.Select(attrs={'class': INPUT_CLS}),
            'rendimiento': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01'}),
            'meta': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'actual': forms.NumberInput(attrs={'class': INPUT_CLS, 'step': '0.01', 'min': '0'}),
            'observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def clean_meta(self):
        meta = self.cleaned_data.get('meta')
        if meta is not None and meta < 0:
            raise forms.ValidationError('La meta no puede ser negativa.')
        return meta
