"""B2b (#74) — ModelForms por sección de ObraCivilTorreDetalle.

Paridad campo-a-campo con `Documentacion/Obra civil.xlsx` hoja CANT OOCC.
Una sección = un Form que sólo expone los campos de esa sección del
`ObraCivilTorreDetalle`. La vista `ObraCivilDetalleSeccionView` selecciona
el form vía `form_para_seccion(slug)` y lo persiste con `update_or_create`.

Validaciones específicas:
  - `*_pct` (excavación/solado/acero/vaciado/compactación) → Decimal 0–1.
  - métricas m³/kg → no-negativas.
  - texto libre y booleans → sin validación adicional.
"""
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle


# ---------------------------------------------------------------------------
# Helpers de validación reusables
# ---------------------------------------------------------------------------

def _validar_pct_0_1(valor, etiqueta):
    """Valida que `valor` sea Decimal en [0, 1]. None permitido (deja default).
    """
    if valor is None:
        return valor
    try:
        d = Decimal(valor)
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError(f'{etiqueta}: valor inválido (debe ser numérico).')
    if d < Decimal('0') or d > Decimal('1'):
        raise ValidationError(
            f'{etiqueta} debe estar entre 0 y 1 (recibido {d}).'
        )
    return d


def _validar_no_negativo(valor, etiqueta):
    """Valida que `valor` sea ≥ 0 si está presente."""
    if valor is None:
        return valor
    try:
        d = Decimal(valor)
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError(f'{etiqueta}: valor inválido.')
    if d < Decimal('0'):
        raise ValidationError(
            f'{etiqueta} no puede ser negativo (recibido {d}).'
        )
    return d


# ---------------------------------------------------------------------------
# Forms por sección
# ---------------------------------------------------------------------------


class OCSeccionCerramientoForm(forms.ModelForm):
    """Sección 2 — Cerramiento (5 campos)."""

    class Meta:
        model = ObraCivilTorreDetalle
        fields = [
            'cerr_madera_un',
            'cerr_lona_m',
            'cerr_senalizacion_ok',
            'cerr_notas',
            'cerr_finalizado_ok',
        ]

    def clean_cerr_madera_un(self):
        return self.cleaned_data.get('cerr_madera_un')  # PositiveInt ya valida

    def clean_cerr_lona_m(self):
        return _validar_no_negativo(
            self.cleaned_data.get('cerr_lona_m'), 'Lona (m)'
        )


class OCSeccionExcavacionForm(forms.ModelForm):
    """Sección 3 — Excavación (16 campos: cuadrilla + 8 FT + tipo + m3 + 4 más)."""

    class Meta:
        model = ObraCivilTorreDetalle
        fields = [
            'exc_cuadrilla',
            'exc_ft022_ok', 'exc_ft929_ok', 'exc_ft923_ok', 'exc_ft924_ok',
            'exc_ft925_ok', 'exc_ft926_ok', 'exc_ft927_ok', 'exc_ft928_ok',
            'exc_tipo',
            'exc_metros_m3',
            'exc_penetrometro_ok',
            'exc_monitoreo_arq',
            'exc_ejecutada_pct',
            'exc_observaciones',
        ]

    def clean_exc_metros_m3(self):
        return _validar_no_negativo(
            self.cleaned_data.get('exc_metros_m3'), 'Excavación (m³)'
        )

    def clean_exc_ejecutada_pct(self):
        v = _validar_pct_0_1(
            self.cleaned_data.get('exc_ejecutada_pct'), '% Excavación ejecutada'
        )
        # Default cuando viene None — modelo trae default 0
        return v if v is not None else Decimal('0')


class OCSeccionSoladoForm(forms.ModelForm):
    """Sección 4 — Solado (20 campos: ingreso + 12 sub-bloques + 4 trailer)."""

    class Meta:
        model = ObraCivilTorreDetalle
        fields = [
            'sol_ingreso_materiales',
            # Agua
            'sol_agua_calc', 'sol_agua_real', 'sol_agua_obs',
            # Arena
            'sol_arena_calc', 'sol_arena_real', 'sol_arena_obs',
            # Grava
            'sol_grava_calc', 'sol_grava_real', 'sol_grava_obs',
            # Cemento
            'sol_cemento_calc', 'sol_cemento_real', 'sol_cemento_obs',
            'sol_soldadura_prolongas_ok',
            'sol_ejecutado_pct',
            'sol_observaciones',
        ]

    def clean_sol_ejecutado_pct(self):
        v = _validar_pct_0_1(
            self.cleaned_data.get('sol_ejecutado_pct'), '% Solado ejecutado'
        )
        return v if v is not None else Decimal('0')

    def _validar_sub(self, prefijo, etiqueta):
        for sufijo in ('_calc', '_real'):
            campo = f'sol_{prefijo}{sufijo}'
            if campo in self.cleaned_data:
                self.cleaned_data[campo] = _validar_no_negativo(
                    self.cleaned_data.get(campo), f'{etiqueta} {sufijo[1:]}'
                )

    def clean(self):
        cleaned = super().clean()
        self._validar_sub('agua', 'Agua')
        self._validar_sub('arena', 'Arena')
        self._validar_sub('grava', 'Grava')
        self._validar_sub('cemento', 'Cemento')
        return cleaned


class OCSeccionAceroForm(forms.ModelForm):
    """Sección 5 — Acero (12 campos)."""

    class Meta:
        model = ObraCivilTorreDetalle
        fields = [
            'ace_ingreso',
            'ace_ft028_ok', 'ace_ft930_ok',
            'ace_corte_flejado_ok',
            'ace_armado_sitio_ok',
            'ace_spt_herramientas_ok',
            'ace_solicitado_kg', 'ace_instalado_kg',
            'ace_observaciones',
            'ace_instalacion_pct',
            'ace_instalacion_obs',
        ]

    def clean_ace_solicitado_kg(self):
        return _validar_no_negativo(
            self.cleaned_data.get('ace_solicitado_kg'), 'Acero solicitado (kg)'
        )

    def clean_ace_instalado_kg(self):
        return _validar_no_negativo(
            self.cleaned_data.get('ace_instalado_kg'), 'Acero instalado (kg)'
        )

    def clean_ace_instalacion_pct(self):
        v = _validar_pct_0_1(
            self.cleaned_data.get('ace_instalacion_pct'), '% Acero instalado'
        )
        return v if v is not None else Decimal('0')


class OCSeccionVaciadoForm(forms.ModelForm):
    """Sección 6 — Vaciado (32 campos)."""

    class Meta:
        model = ObraCivilTorreDetalle
        fields = [
            'vac_ft916_ok', 'vac_nivelacion_stub_ok', 'vac_encofrado_ok',
            'vac_ingreso_materiales', 'vac_it380_ok', 'vac_ft056_ok',
            'vac_tipo_concreto', 'vac_mpa_teorica',
            # Agua
            'vac_agua_calc', 'vac_agua_real', 'vac_agua_obs',
            # Arena
            'vac_arena_calc', 'vac_arena_real', 'vac_arena_obs',
            # Grava
            'vac_grava_calc', 'vac_grava_real', 'vac_grava_obs',
            # Cemento
            'vac_cemento_calc', 'vac_cemento_real', 'vac_cemento_obs',
            'vac_slump_ok',
            'vac_fecha_vaciado', 'vac_fecha_cilindros',
            'vac_inspeccion_stub_ok',
            'vac_encargado_puntas',
            'vac_desencofrado_ok',
            'vac_ejecutado_pct',
            'vac_observaciones',
        ]

    def clean_vac_ejecutado_pct(self):
        v = _validar_pct_0_1(
            self.cleaned_data.get('vac_ejecutado_pct'), '% Vaciado ejecutado'
        )
        return v if v is not None else Decimal('0')

    def _validar_sub(self, prefijo, etiqueta):
        for sufijo in ('_calc', '_real'):
            campo = f'vac_{prefijo}{sufijo}'
            if campo in self.cleaned_data:
                self.cleaned_data[campo] = _validar_no_negativo(
                    self.cleaned_data.get(campo), f'{etiqueta} {sufijo[1:]}'
                )

    def clean(self):
        cleaned = super().clean()
        self._validar_sub('agua', 'Agua')
        self._validar_sub('arena', 'Arena')
        self._validar_sub('grava', 'Grava')
        self._validar_sub('cemento', 'Cemento')
        # Coherencia opcional: cilindros >= vaciado
        fv = cleaned.get('vac_fecha_vaciado')
        fc = cleaned.get('vac_fecha_cilindros')
        if fv and fc and fc < fv:
            raise ValidationError({
                'vac_fecha_cilindros':
                    'La fecha de toma de cilindros no puede ser anterior al vaciado.'
            })
        return cleaned


class OCSeccionCompactacionForm(forms.ModelForm):
    """Sección 7 — Compactación (7 campos)."""

    class Meta:
        model = ObraCivilTorreDetalle
        fields = [
            'com_ft914_ok',
            'com_suelo_natural_ok',
            'com_suelo_cemento_ok',
            'com_suelo_prestamo_ok',
            'com_volumen_m3',
            'com_finalizada_pct',
            'com_observaciones',
        ]

    def clean_com_volumen_m3(self):
        return _validar_no_negativo(
            self.cleaned_data.get('com_volumen_m3'), 'Volumen compactación (m³)'
        )

    def clean_com_finalizada_pct(self):
        v = _validar_pct_0_1(
            self.cleaned_data.get('com_finalizada_pct'), '% Compactación finalizada'
        )
        return v if v is not None else Decimal('0')


# ---------------------------------------------------------------------------
# Factory + registry
# ---------------------------------------------------------------------------

SECCIONES = [
    ('cerramiento', 'Cerramiento', OCSeccionCerramientoForm),
    ('excavacion', 'Excavación', OCSeccionExcavacionForm),
    ('solado', 'Solado', OCSeccionSoladoForm),
    ('acero', 'Acero', OCSeccionAceroForm),
    ('vaciado', 'Vaciado', OCSeccionVaciadoForm),
    ('compactacion', 'Compactación', OCSeccionCompactacionForm),
]

SECCION_SLUGS = [s[0] for s in SECCIONES]
SECCION_LABELS = {s[0]: s[1] for s in SECCIONES}
SECCION_FORMS = {s[0]: s[2] for s in SECCIONES}


def form_para_seccion(seccion_slug):
    """Devuelve la clase Form asociada al slug. Raise KeyError si inválido."""
    if seccion_slug not in SECCION_FORMS:
        raise KeyError(
            f"Sección inválida: {seccion_slug!r} (válidas: {SECCION_SLUGS})"
        )
    return SECCION_FORMS[seccion_slug]
