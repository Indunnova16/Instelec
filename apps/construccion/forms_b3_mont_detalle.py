"""B3b — ModelForms por seccion para MontajeEstructuraTorreDetalle (paridad
Excel CANT MONTAJE, issue #76).

7 ModelForms (uno por seccion del detalle) sobre el mismo modelo
`MontajeEstructuraTorreDetalle`. Cada form expone solo los `fields` de su
seccion, asi el endpoint POST `MontajeDetalleSaveView` puede aplicar
`update_or_create(torre=t, defaults=cleaned_data)` sin tocar las demas
secciones.

Validaciones especificas:
  - Pre-armado: fecha_fin >= fecha_inicio; prearmado_pct in [0, 100]
  - Montaje:    fecha_fin >= fecha_inicio
  - Pesos:      peso_diseno_kl / peso_instalado_kl no-negativos. La
                desviacion > 5% NO es bloqueante - se muestra como warning
                visual en el partial (`peso_alerta` @property del modelo).
  - Facturacion: `facturada_por_contratista` es CharField (no Boolean):
                el Excel real trae strings tipo "Cruz", "Higuita", "Instelec".

Factory `form_para_seccion(seccion_slug)` resuelve seccion -> clase para uso
del endpoint POST y del template de detalle.
"""
from decimal import Decimal

from django import forms

from .models_b3_mont_detalle import MontajeEstructuraTorreDetalle


# ---------------------------------------------------------------------------
# 1. INFO GENERAL
# ---------------------------------------------------------------------------

class MontSeccionGeneralForm(forms.ModelForm):
    """Tipo de torre + cuerpo. `funcion` se deriva automaticamente en el
    modelo (@property) y se muestra read-only en el partial."""

    class Meta:
        model = MontajeEstructuraTorreDetalle
        fields = ['tipo_torre', 'cuerpo']
        widgets = {
            'tipo_torre': forms.Select(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'cuerpo': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'placeholder': 'Ej. C1, C2...',
            }),
        }


# ---------------------------------------------------------------------------
# 2. RECEPCION EN PATIO
# ---------------------------------------------------------------------------

class MontSeccionRecepcionForm(forms.ModelForm):
    class Meta:
        model = MontajeEstructuraTorreDetalle
        fields = [
            'fecha_recibida_patio',
            'recepcion_sin_pendientes_ok',
            'recepcion_observaciones',
        ]
        widgets = {
            'fecha_recibida_patio': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'recepcion_sin_pendientes_ok': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 '
                         'focus:ring-blue-500',
            }),
            'recepcion_observaciones': forms.Textarea(attrs={
                'rows': 3,
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
        }


# ---------------------------------------------------------------------------
# 3. PRE-ARMADO
# ---------------------------------------------------------------------------

class MontSeccionPrearmadoForm(forms.ModelForm):
    class Meta:
        model = MontajeEstructuraTorreDetalle
        fields = [
            'prearmado_encargado',
            'estructura_en_sitio_ok',
            'prearmado_fecha_inicio',
            'prearmado_fecha_fin',
            'prearmada_ok',
            'prearmado_pct',
        ]
        widgets = {
            'prearmado_encargado': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'estructura_en_sitio_ok': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 '
                         'focus:ring-blue-500',
            }),
            'prearmado_fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'prearmado_fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'prearmada_ok': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 '
                         'focus:ring-blue-500',
            }),
            'prearmado_pct': forms.NumberInput(attrs={
                'min': '0', 'max': '100', 'step': '0.01',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get('prearmado_fecha_inicio')
        fin = cleaned.get('prearmado_fecha_fin')
        if inicio and fin and fin < inicio:
            raise forms.ValidationError(
                'La fecha fin de pre-armado no puede ser anterior a la fecha de inicio.'
            )
        pct = cleaned.get('prearmado_pct')
        if pct is not None and (pct < Decimal('0') or pct > Decimal('100')):
            self.add_error('prearmado_pct',
                           'El porcentaje de pre-armado debe estar entre 0 y 100.')
        return cleaned


# ---------------------------------------------------------------------------
# 4. MONTAJE
# ---------------------------------------------------------------------------

class MontSeccionMontajeForm(forms.ModelForm):
    class Meta:
        model = MontajeEstructuraTorreDetalle
        fields = [
            'montaje_encargado',
            'montaje_fecha_inicio',
            'montaje_fecha_fin',
            'torre_montada_ok',
            'montaje_observaciones',
        ]
        widgets = {
            'montaje_encargado': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'montaje_fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'montaje_fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'torre_montada_ok': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 '
                         'focus:ring-blue-500',
            }),
            'montaje_observaciones': forms.Textarea(attrs={
                'rows': 3,
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get('montaje_fecha_inicio')
        fin = cleaned.get('montaje_fecha_fin')
        if inicio and fin and fin < inicio:
            raise forms.ValidationError(
                'La fecha fin de montaje no puede ser anterior a la fecha de inicio.'
            )
        return cleaned


# ---------------------------------------------------------------------------
# 5. CONTROLES DE CALIDAD
# ---------------------------------------------------------------------------

class MontSeccionControlesForm(forms.ModelForm):
    class Meta:
        model = MontajeEstructuraTorreDetalle
        fields = [
            'ft032_control_montaje_ok',
            'ft913_verticalidad_torsion_ok',
            'ft920_recepcion_montaje_ok',
            'revisada_ok',
            'entregada_para_carga_ok',
        ]
        widgets = {
            f: forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 '
                         'focus:ring-blue-500',
            })
            for f in [
                'ft032_control_montaje_ok',
                'ft913_verticalidad_torsion_ok',
                'ft920_recepcion_montaje_ok',
                'revisada_ok',
                'entregada_para_carga_ok',
            ]
        }


# ---------------------------------------------------------------------------
# 6. PESOS
# ---------------------------------------------------------------------------

class MontSeccionPesosForm(forms.ModelForm):
    """Pesos diseno vs instalado. La desviacion > 5% se muestra como warning
    visual en el partial; NO bloquea el guardado (decision AC)."""

    class Meta:
        model = MontajeEstructuraTorreDetalle
        fields = ['peso_diseno_kl', 'peso_instalado_kl']
        widgets = {
            'peso_diseno_kl': forms.NumberInput(attrs={
                'min': '0', 'step': '0.01',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
            'peso_instalado_kl': forms.NumberInput(attrs={
                'min': '0', 'step': '0.01',
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
            }),
        }

    def clean_peso_diseno_kl(self):
        v = self.cleaned_data.get('peso_diseno_kl')
        if v is not None and v < Decimal('0'):
            raise forms.ValidationError('El peso de diseno no puede ser negativo.')
        return v

    def clean_peso_instalado_kl(self):
        v = self.cleaned_data.get('peso_instalado_kl')
        if v is not None and v < Decimal('0'):
            raise forms.ValidationError('El peso instalado no puede ser negativo.')
        return v


# ---------------------------------------------------------------------------
# 7. FACTURACION
# ---------------------------------------------------------------------------

class MontSeccionFacturacionForm(forms.ModelForm):
    """`facturada_por_contratista` es CharField (no Boolean): el Excel real
    trae strings tipo "Cruz", "Higuita", "Instelec" (nombre del subcontratista).
    """

    class Meta:
        model = MontajeEstructuraTorreDetalle
        fields = ['facturada_a_dueno_ok', 'facturada_por_contratista']
        widgets = {
            'facturada_a_dueno_ok': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 '
                         'focus:ring-blue-500',
            }),
            'facturada_por_contratista': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm '
                         'focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'placeholder': 'Cruz / Higuita / Instelec...',
                'maxlength': '100',
            }),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Slugs de seccion -> clase form. Sincronizado con SECCIONES en views_b3_mont_detalle.
SECCION_FORM_MAP = {
    'general': MontSeccionGeneralForm,
    'recepcion': MontSeccionRecepcionForm,
    'prearmado': MontSeccionPrearmadoForm,
    'montaje': MontSeccionMontajeForm,
    'controles': MontSeccionControlesForm,
    'pesos': MontSeccionPesosForm,
    'facturacion': MontSeccionFacturacionForm,
}


def form_para_seccion(seccion_slug):
    """Devuelve la clase Form para el slug de seccion, o None si no existe."""
    return SECCION_FORM_MAP.get(seccion_slug)
