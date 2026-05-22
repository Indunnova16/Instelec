"""Forms for construction projects."""
from django import forms
from apps.contratos.models import Contrato
from .models import PataObra, FaseTorre, SocialPredial, AmbientalTorre


INPUT_CLS = ('mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 '
             'px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 '
             'bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm')
DATE_ATTRS = {'class': INPUT_CLS, 'type': 'date'}
CHECK_CLS = 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500'


class ContratoForm(forms.ModelForm):
    """Form for editing contract details."""

    class Meta:
        model = Contrato
        fields = ['codigo', 'nombre', 'cliente', 'objeto', 'valor',
                  'fecha_inicio', 'fecha_fin', 'estado', 'observaciones']
        widgets = {
            'codigo': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'placeholder': 'Ej: CONST-001',
            }),
            'nombre': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'placeholder': 'Nombre del contrato',
            }),
            'cliente': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'placeholder': 'Nombre del cliente',
            }),
            'objeto': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'rows': 3,
                'placeholder': 'Descripción del objeto del contrato',
            }),
            'valor': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'type': 'date',
            }),
            'fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'type': 'date',
            }),
            'estado': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm',
                'rows': 3,
                'placeholder': 'Observaciones adicionales',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['objeto'].required = False
        self.fields['observaciones'].required = False
        self.fields['fecha_inicio'].required = False
        self.fields['fecha_fin'].required = False


# ====== Obra Civil — 1 form por pata con todos los 6 bloques #53-#55 ======

class PataObraForm(forms.ModelForm):
    """Form completo de una pata con sus 6 bloques secuenciales OC."""

    class Meta:
        model = PataObra
        fields = [
            # Bloque 1: Cerramiento
            'cerramiento_finalizado_ok', 'cerramiento_fecha',
            # Bloque 2: Excavación
            'tipo_excavacion', 'aplica_pilotes',
            'excavacion_ok', 'excavacion_fecha', 'excavacion_m3',
            'instalacion_pilotes_ok', 'instalacion_pilotes_fecha',
            # Bloque 3: Solado
            'solado_ok', 'solado_fecha', 'solado_m3',
            # Bloque 4: Acero (con diseño vs real)
            'acero_refuerzo_ok', 'acero_refuerzo_fecha',
            'acero_solicitado_kg', 'acero_instalado_kg', 'acero_kg',
            'nivelacion_ok', 'nivelacion_fecha',
            # Bloque 5: Vaciado + cilindros
            'vaciado_ok', 'vaciado_fecha',
            'concreto_solicitado_m3', 'concreto_instalado_m3', 'concreto_m3',
            'concreto_psi', 'resistencia_especificada_mpa',
            'cilindro_7d_mpa', 'cilindro_14d_mpa',
            'cilindro_21d_mpa', 'cilindro_51d_mpa',
            # Bloque 6: Compactación + SPT base
            'relleno_compactacion_ok', 'relleno_compactacion_fecha', 'relleno_m3',
            'spt_base_ok', 'spt_base_fecha',
            'spt_modulos_ok', 'spt_modulos_fecha',
            # Crew + observations
            'cuadrilla_civil', 'observaciones',
        ]
        widgets = {
            'tipo_excavacion': forms.Select(attrs={'class': INPUT_CLS}),
            'cuadrilla_civil': forms.TextInput(attrs={'class': INPUT_CLS}),
            'concreto_psi': forms.TextInput(attrs={'class': INPUT_CLS}),
            'observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', CHECK_CLS)
            elif isinstance(field.widget, forms.DateInput):
                field.widget = forms.DateInput(format='%Y-%m-%d', attrs=DATE_ATTRS)
                field.input_formats = ['%Y-%m-%d']
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.setdefault('class', INPUT_CLS)
                field.widget.attrs.setdefault('step', 'any')
            field.required = False


# ====== Montaje + SPT + Pintura ======

class FaseTorreMontajeForm(forms.ModelForm):
    """Sección Montaje + SPT + Pintura de FaseTorre (#56 #57)."""

    class Meta:
        model = FaseTorre
        fields = [
            # Info estructura
            'funcion_torre', 'tipo_torre_montaje', 'cuerpo_torre',
            # Selección + transporte
            'seleccion_estructura_ok', 'seleccion_estructura_fecha',
            'transporte_estructura_ok', 'transporte_estructura_fecha',
            # Recepción patio
            'fecha_recepcion_patio', 'recibida_satisfaccion_ok',
            'pct_completitud_estructura', 'observaciones_recepcion',
            # Prearmado
            'prearmado_ok', 'prearmado_fecha',
            'prearmado_fecha_inicio', 'prearmado_fecha_fin',
            'prearmado_pct', 'cuadrilla_prearmado',
            # Montaje
            'montaje_ok', 'montaje_fecha', 'cuadrilla_montaje',
            'torsion_ok', 'torsion_fecha',
            'entrega_wsp_ok', 'entrega_wsp_fecha',
            # Gate Tendido
            'entrega_carga_ok', 'entrega_carga_fecha',
            'pct_montaje',
            # SPT
            'spt_cantidad_excavacion_m', 'spt_cable_planos_m', 'spt_cable_instalado_m',
            'spt_polvora_tiros_planos', 'spt_polvora_tiros_por_caja',
            'spt_polvora_consumida_cajas',
            'spt_ft068_ok', 'spt_ft029_ok', 'spt_informe_mediciones_ok',
            'spt_pct', 'spt_observaciones',
            # Pintura
            'pintura_ft912_ok', 'pintura_observaciones',
        ]
        widgets = {
            'funcion_torre': forms.Select(attrs={'class': INPUT_CLS}),
            'tipo_torre_montaje': forms.TextInput(attrs={'class': INPUT_CLS}),
            'cuerpo_torre': forms.TextInput(attrs={'class': INPUT_CLS}),
            'cuadrilla_prearmado': forms.TextInput(attrs={'class': INPUT_CLS}),
            'cuadrilla_montaje': forms.TextInput(attrs={'class': INPUT_CLS}),
            'observaciones_recepcion': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
            'spt_observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
            'pintura_observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', CHECK_CLS)
            elif isinstance(field.widget, forms.DateInput):
                field.widget = forms.DateInput(format='%Y-%m-%d', attrs=DATE_ATTRS)
                field.input_formats = ['%Y-%m-%d']
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.setdefault('class', INPUT_CLS)
                field.widget.attrs.setdefault('step', 'any')
            field.required = False


# ====== Tendido (con sub-flujo conductor + circuito 2 + guarda) #58 ======

class FaseTorreTendidoForm(forms.ModelForm):
    """Sección Tendido de FaseTorre (#58)."""

    class Meta:
        model = FaseTorre
        fields = [
            # Vestida
            'vestida_torres_ok', 'vestida_torres_fecha',
            # Sub-flujo conductor
            'riega_manila_ok', 'riega_guaya_ok',
            'ft046_ok', 'ft047_ok', 'ft932_ok',
            'regulacion_flechado_ok', 'ft918_ok',
            'grapado_ok', 'accesorios_ok', 'placas_senalizacion_ok',
            'distancia_vano_adelante_m',
            # Circuito 1
            'tendido_conductor_a_ok', 'tendido_conductor_a_fecha',
            'tendido_conductor_b_ok', 'tendido_conductor_b_fecha',
            'tendido_conductor_c_ok', 'tendido_conductor_c_fecha',
            # OPGW
            'tendido_opgw_izq_ok', 'tendido_opgw_izq_fecha',
            'tendido_opgw_der_ok', 'tendido_opgw_der_fecha',
            # Circuito 2
            'tendido_conductor_c2_a_ok', 'tendido_conductor_c2_a_fecha',
            'tendido_conductor_c2_b_ok', 'tendido_conductor_c2_b_fecha',
            'tendido_conductor_c2_c_ok', 'tendido_conductor_c2_c_fecha',
            # Cable de guarda
            'tendido_guarda_ok', 'tendido_guarda_fecha',
            # Regulación final
            'regulacion_ok', 'regulacion_fecha',
            'cuadrilla_tendido', 'pct_tendido', 'pct_facturacion',
            'observaciones',
        ]
        widgets = {
            'cuadrilla_tendido': forms.TextInput(attrs={'class': INPUT_CLS}),
            'observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', CHECK_CLS)
            elif isinstance(field.widget, forms.DateInput):
                field.widget = forms.DateInput(format='%Y-%m-%d', attrs=DATE_ATTRS)
                field.input_formats = ['%Y-%m-%d']
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.setdefault('class', INPUT_CLS)
                field.widget.attrs.setdefault('step', 'any')
            field.required = False


# ====== Sociopredial — liberación por torre (#51) ======

class SocialPredialForm(forms.ModelForm):
    """Form completo de Social Predial por torre.

    Liberación basada en las 4 actas (semáforo VERDE)."""

    class Meta:
        model = SocialPredial
        fields = [
            # Info contacto
            'propietario', 'persona_contacto', 'telefono',
            'predio', 'departamento', 'municipio', 'unidad_territorial',
            'fecha_socializacion',
            # PIPC
            'pipc_municipio_fecha', 'pipc_municipio_ok',
            'pipc_unidad_fecha', 'pipc_unidad_ok',
            # 4 actas (estas 4 fechas son el semáforo)
            'acta_vecindad_fecha', 'acta_vecindad_ok',
            'acta_acceso_comunitario_fecha', 'acta_acceso_comunitario_ok',
            'autorizacion_propietario_fecha', 'autorizacion_propietario_ok',
            'acta_acceso_privado_fecha', 'acta_acceso_privado_ok',
            # Liberación + MONC
            'liberacion_predial_pdo_fecha', 'liberacion_predial_pdo_ok',
            'contratacion_monc_fecha', 'contratacion_monc_ok',
            'observaciones',
        ]
        widgets = {
            'propietario': forms.TextInput(attrs={'class': INPUT_CLS}),
            'persona_contacto': forms.TextInput(attrs={'class': INPUT_CLS}),
            'telefono': forms.TextInput(attrs={'class': INPUT_CLS}),
            'predio': forms.TextInput(attrs={'class': INPUT_CLS}),
            'departamento': forms.TextInput(attrs={'class': INPUT_CLS}),
            'municipio': forms.TextInput(attrs={'class': INPUT_CLS}),
            'unidad_territorial': forms.TextInput(attrs={'class': INPUT_CLS}),
            'observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', CHECK_CLS)
            elif isinstance(field.widget, forms.DateInput):
                field.widget = forms.DateInput(format='%Y-%m-%d', attrs=DATE_ATTRS)
                field.input_formats = ['%Y-%m-%d']
            field.required = False


# ====== Ambiental — liberación por torre (#52) ======

class AmbientalTorreForm(forms.ModelForm):
    """Form completo de Ambiental por torre.

    Liberación basada en actividades QUE APLICAN (semáforo Gabriel Valencia)."""

    class Meta:
        model = AmbientalTorre
        fields = [
            # Ahuyentamiento
            'ahuyentamiento_aplica', 'ahuyentamiento_fecha', 'ahuyentamiento_ok',
            # Epífitas
            'epifitas_aplica', 'conteo_epifitas', 'conteo_epifitas_fecha',
            'traslado_epifitas_fecha', 'traslado_epifitas_ok',
            'reubicacion_epifitas_fecha', 'reubicacion_epifitas_ok',
            # Aprovechamiento forestal (torre + vano)
            'aprov_forestal_torre_aplica',
            'aprov_forestal_torre_fecha', 'aprov_forestal_torre_ok',
            'aprov_forestal_vano_aplica',
            'aprov_forestal_vano_fecha', 'aprov_forestal_vano_ok',
            # Arqueología
            'arqueologia_poligonos_fecha', 'arqueologia_poligonos_ok',
            'arqueologia_torre_estado',
            'rescate_arqueologico_aplica',
            'rescate_arqueologico_fecha', 'rescate_arqueologico_ok',
            'monitoreo_arqueologico_aplica',
            # Cambios LA + accesos
            'cambio_menor_la',
            'adecuacion_accesos_fecha', 'adecuacion_accesos_porcentaje',
            'adecuacion_accesos_ok',
            # Liberación final
            'liberacion_pdo_fecha', 'liberacion_pdo_ok',
            'observaciones',
        ]
        widgets = {
            'arqueologia_torre_estado': forms.TextInput(attrs={'class': INPUT_CLS}),
            'cambio_menor_la': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
            'observaciones': forms.Textarea(attrs={'class': INPUT_CLS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', CHECK_CLS)
            elif isinstance(field.widget, forms.DateInput):
                field.widget = forms.DateInput(format='%Y-%m-%d', attrs=DATE_ATTRS)
                field.input_formats = ['%Y-%m-%d']
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.setdefault('class', INPUT_CLS)
                field.widget.attrs.setdefault('step', 'any')
            field.required = False
