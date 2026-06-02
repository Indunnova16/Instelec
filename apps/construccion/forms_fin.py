"""B5 (#123 Fase 3/4) — Forms del Módulo Financiero de Construcción.

Tres forms:

1. ``CargarBDContableConstruccionForm`` — carga del .xlsx (BD contable o
   presupuesto). Espejo de ``apps.financiero.forms_finv2.CargarBDContableForm``
   (mismo widget Tailwind file:, misma validación .xlsx + ≤ 20 MB).
2. ``FacturacionConstruccionForm`` — ModelForm de ``FacturacionConstruccion``.
3. ``CostosConstruccionForm``      — ModelForm de ``CostosConstruccion``
   (``costo_total`` se autocalcula en save(), no se expone).

Las clases CSS replican el estilo de los forms existentes de construcción
(``forms_b2_indicadores``) y financiero v2 para consistencia visual.
"""
from django import forms

from apps.financiero.importers_finv2 import MAX_UPLOAD_BYTES

from .models_fin import CostosConstruccion, FacturacionConstruccion


# Clase base reutilizada por los inputs de texto/número/fecha.
_INPUT_CLS = (
    'w-full rounded-lg border-gray-300 dark:border-gray-600 '
    'dark:bg-gray-800 dark:text-white text-sm'
)
_FILE_CLS = (
    'block w-full text-sm text-gray-500 dark:text-gray-400 '
    'file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 '
    'file:text-sm file:font-semibold file:bg-blue-50 '
    'file:text-blue-700 hover:file:bg-blue-100 '
    'dark:file:bg-gray-700 dark:file:text-gray-300'
)


class CargarBDContableConstruccionForm(forms.Form):
    """Carga de archivo .xlsx (BD contable / presupuesto / costos).

    Misma validación que el form de #120: extensión .xlsx + tamaño ≤ 20 MB. El
    tipo concreto de archivo lo decide ``detect_excel_format_construccion`` en la
    vista; este form solo garantiza que sea un .xlsx procesable.
    """

    archivo = forms.FileField(
        label='Archivo Excel (.xlsx)',
        help_text=(
            'Suba el archivo de presupuesto, base de datos contable o costos '
            'en formato .xlsx. Máximo 20 MB.'
        ),
        widget=forms.ClearableFileInput(attrs={
            'accept': '.xlsx',
            'class': _FILE_CLS,
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


class FacturacionConstruccionForm(forms.ModelForm):
    """Alta/edición de una factura del proyecto."""

    class Meta:
        model = FacturacionConstruccion
        fields = [
            'numero_factura', 'fecha_emision', 'monto_facturado',
            'monto_pagado', 'estado', 'observaciones',
        ]
        widgets = {
            'numero_factura': forms.TextInput(attrs={
                'class': _INPUT_CLS, 'placeholder': 'Ej: FV-001',
            }),
            'fecha_emision': forms.DateInput(attrs={
                'class': _INPUT_CLS, 'type': 'date',
            }, format='%Y-%m-%d'),
            'monto_facturado': forms.NumberInput(attrs={
                'class': _INPUT_CLS, 'step': '0.01', 'min': '0',
            }),
            'monto_pagado': forms.NumberInput(attrs={
                'class': _INPUT_CLS, 'step': '0.01', 'min': '0',
            }),
            'estado': forms.Select(attrs={'class': _INPUT_CLS}),
            'observaciones': forms.Textarea(attrs={
                'class': _INPUT_CLS, 'rows': 2,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El widget date necesita el input_format ISO para repoblar al editar.
        self.fields['fecha_emision'].input_formats = ['%Y-%m-%d']

    def clean(self):
        cleaned = super().clean()
        facturado = cleaned.get('monto_facturado')
        pagado = cleaned.get('monto_pagado')
        # Regla de negocio: no se puede pagar más de lo facturado.
        if facturado is not None and pagado is not None and pagado > facturado:
            self.add_error(
                'monto_pagado',
                'El monto pagado no puede superar el monto facturado.',
            )
        return cleaned


class CostosConstruccionForm(forms.ModelForm):
    """Alta/edición de un costo ejecutado.

    ``costo_total`` NO se expone: lo calcula ``CostosConstruccion.save()``
    (cantidad × costo_unitario). El campo ``actividad`` es opcional (FK nullable).
    """

    class Meta:
        model = CostosConstruccion
        fields = [
            'concepto', 'tipo_recurso', 'cantidad', 'costo_unitario',
            'fecha', 'actividad',
        ]
        widgets = {
            'concepto': forms.TextInput(attrs={
                'class': _INPUT_CLS, 'placeholder': 'Ej: Cemento gris 50kg',
            }),
            'tipo_recurso': forms.Select(attrs={'class': _INPUT_CLS}),
            'cantidad': forms.NumberInput(attrs={
                'class': _INPUT_CLS, 'step': '0.01', 'min': '0',
            }),
            'costo_unitario': forms.NumberInput(attrs={
                'class': _INPUT_CLS, 'step': '0.01', 'min': '0',
            }),
            'fecha': forms.DateInput(attrs={
                'class': _INPUT_CLS, 'type': 'date',
            }, format='%Y-%m-%d'),
            'actividad': forms.Select(attrs={'class': _INPUT_CLS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha'].input_formats = ['%Y-%m-%d']
        self.fields['actividad'].required = False
        self.fields['actividad'].empty_label = '— Sin actividad —'

    def clean_cantidad(self):
        cantidad = self.cleaned_data.get('cantidad')
        if cantidad is not None and cantidad < 0:
            raise forms.ValidationError('La cantidad no puede ser negativa.')
        return cantidad

    def clean_costo_unitario(self):
        unitario = self.cleaned_data.get('costo_unitario')
        if unitario is not None and unitario < 0:
            raise forms.ValidationError('El costo unitario no puede ser negativo.')
        return unitario
