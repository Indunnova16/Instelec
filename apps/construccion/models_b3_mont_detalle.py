"""B3a — MontajeEstructuraTorreDetalle (paridad CANT MONTAJE Excel cliente).

Modelo de detalle granular del proceso de Montaje de Estructura por torre, en
paridad campo-a-campo con la hoja CANT MONTAJE del Excel `Documentacion/Montaje.xlsx`
del cliente. Issue #76.

Granularidad: OneToOne con TorreConstruccion (no por pata — el Excel real es
una fila por torre).

`MontajeEstructuraTorre` (legacy, db_table='construccion_montaje_estructura_torre')
se conserva como cache agregado de 4 columnas (estructura_sitio / prearamada /
torre_montada / revisada) para las vistas del dashboard B3. El detalle nuevo
vive en db_table='construccion_mont_detalle' y un signal post_save mantiene
sincronizado el cache (ver signals_b3_mont_detalle.py).

Secciones (7) — ~30 campos:
  1. Info General (3): tipo_torre A/A_esp/B/C/D/portico, cuerpo, @funcion
  2. Recepción Patio (3): fecha, ok_sin_pendientes, observaciones
  3. Pre-armado (6): encargado, estructura_en_sitio_ok, fechas inicio/fin,
     prearmada_ok, prearmado_pct
  4. Montaje (5): encargado, fechas inicio/fin, torre_montada_ok, observaciones
  5. Controles Calidad (5): FT-032 / FT-913 / FT-920, revisada_ok,
     entregada_para_carga_ok
  6. Pesos (2): peso_diseno_kl, peso_instalado_kl + @peso_desviacion_pct + @peso_alerta
  7. Facturación (2): facturada_a_dueno_ok, facturada_por_contratista (CharField)

Decisión AC: `facturada_por_contratista` es CharField(max_length=100), NO Boolean.
El Excel real del cliente trae strings tipo "Cruz" / "Higuita" / "Instelec" (el
nombre del contratista que facturó esa torre).

Pesos avance ponderado (SUMPRODUCT en @avance_ponderado):
  - estructura_en_sitio_ok: 10%
  - prearmada_ok:           20%
  - torre_montada_ok:       45%
  - revisada_ok:            25%
"""
from decimal import Decimal

from django.db import models

from apps.core.models import BaseModel
from .models import ProyectoConstruccion, TorreConstruccion


# Pesos canónicos del Excel (porcentajes 0-100) — fuente de verdad para
# @avance_ponderado. Si cambian, ajustar aquí.
PESO_ESTRUCTURA_SITIO = Decimal('10')
PESO_PREARMADA = Decimal('20')
PESO_TORRE_MONTADA = Decimal('45')
PESO_REVISADA = Decimal('25')

# Umbral de alerta de desviación de peso (paridad #76).
UMBRAL_DESVIACION_PESO_PCT = Decimal('5')


class MontajeEstructuraTorreDetalle(BaseModel):
    """Detalle CANT MONTAJE Excel — una fila por torre (OneToOne).

    Mantenido en sincronía con `MontajeEstructuraTorre` (cache) vía signal
    `recalcular_montaje_torre` en signals_b3_mont_detalle.py.
    """

    class TipoTorre(models.TextChoices):
        A = 'A', 'A — Suspensión'
        A_ESP = 'A_esp', 'A especial — Suspensión'
        B = 'B', 'B — Retención'
        C = 'C', 'C — Retención'
        D = 'D', 'D — Retención'
        PORTICO = 'portico', 'Pórtico — Retención'

    # Tipos de torre que se consideran de Suspensión (resto = Retención).
    SUSPENSION_TIPOS = {'A', 'A_esp'}

    torre = models.OneToOneField(
        TorreConstruccion,
        on_delete=models.CASCADE,
        related_name='mont_detalle',
        verbose_name='Torre',
    )
    proyecto = models.ForeignKey(
        ProyectoConstruccion,
        on_delete=models.CASCADE,
        related_name='mont_detalles',
        verbose_name='Proyecto',
    )

    # ===== 1. INFO GENERAL =====
    tipo_torre = models.CharField(
        'Tipo de torre', max_length=10,
        choices=TipoTorre.choices, blank=True,
    )
    cuerpo = models.CharField(
        'Cuerpo / tramo', max_length=30, blank=True,
        help_text='Identificador del cuerpo según planos del proyecto',
    )

    # ===== 2. RECEPCIÓN EN PATIO =====
    fecha_recibida_patio = models.DateField(
        'Fecha de recepción en patio', null=True, blank=True,
    )
    recepcion_sin_pendientes_ok = models.BooleanField(
        'Recibida sin pendientes', default=False,
    )
    recepcion_observaciones = models.TextField(
        'Observaciones de recepción', blank=True,
    )

    # ===== 3. PRE-ARMADO =====
    prearmado_encargado = models.CharField(
        'Encargado pre-armado', max_length=100, blank=True,
    )
    estructura_en_sitio_ok = models.BooleanField(
        'Estructura en sitio (peso 10%)', default=False,
    )
    prearmado_fecha_inicio = models.DateField(
        'Pre-armado — fecha inicio', null=True, blank=True,
    )
    prearmado_fecha_fin = models.DateField(
        'Pre-armado — fecha fin', null=True, blank=True,
    )
    prearmada_ok = models.BooleanField(
        'Prearmada (peso 20%)', default=False,
    )
    prearmado_pct = models.DecimalField(
        '% avance pre-armado', max_digits=5, decimal_places=2,
        default=Decimal('0'),
        help_text='0..100 (avance granular si la torre no está 100% prearmada)',
    )

    # ===== 4. MONTAJE =====
    montaje_encargado = models.CharField(
        'Encargado montaje', max_length=100, blank=True,
    )
    montaje_fecha_inicio = models.DateField(
        'Montaje — fecha inicio', null=True, blank=True,
    )
    montaje_fecha_fin = models.DateField(
        'Montaje — fecha fin', null=True, blank=True,
    )
    torre_montada_ok = models.BooleanField(
        'Torre montada (peso 45%)', default=False,
    )
    montaje_observaciones = models.TextField(
        'Observaciones de montaje', blank=True,
    )

    # ===== 5. CONTROLES DE CALIDAD =====
    ft032_control_montaje_ok = models.BooleanField(
        'FT-032 Control montaje', default=False,
    )
    ft913_verticalidad_torsion_ok = models.BooleanField(
        'FT-913 Verticalidad y torsión', default=False,
    )
    ft920_recepcion_montaje_ok = models.BooleanField(
        'FT-920 Recepción de montaje', default=False,
    )
    revisada_ok = models.BooleanField(
        'Revisada (peso 25%)', default=False,
    )
    entregada_para_carga_ok = models.BooleanField(
        'Entregada para carga (habilita Tendido)', default=False,
    )

    # ===== 6. PESOS DISEÑO vs INSTALADO =====
    peso_diseno_kl = models.DecimalField(
        'Peso diseño (kL)', max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text='Peso teórico según planos, en kilo-libras (kL)',
    )
    peso_instalado_kl = models.DecimalField(
        'Peso instalado (kL)', max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text='Peso real montado, en kilo-libras (kL)',
    )

    # ===== 7. FACTURACIÓN =====
    facturada_a_dueno_ok = models.BooleanField(
        'Facturada al dueño', default=False,
    )
    facturada_por_contratista = models.CharField(
        'Facturada por contratista', max_length=100, blank=True,
        help_text='Nombre del contratista que facturó (ej. Cruz, Higuita, Instelec)',
    )

    class Meta:
        db_table = 'construccion_mont_detalle'
        verbose_name = 'Montaje — Detalle por torre'
        verbose_name_plural = 'Montaje — Detalle por torre'
        ordering = ['torre__numero']

    def __str__(self):
        return f'MontDetalle T{self.torre.numero}'

    # ======================================================================
    # Properties calculadas (paridad Excel)
    # ======================================================================

    @property
    def funcion(self):
        """Suspensión si tipo_torre ∈ {A, A_esp}; Retención en el resto.

        Devuelve '' si tipo_torre no está definido (no asumir).
        """
        if not self.tipo_torre:
            return ''
        return 'Suspensión' if self.tipo_torre in self.SUSPENSION_TIPOS else 'Retención'

    @property
    def dias_montaje(self):
        """Diferencia (fecha_fin - fecha_inicio) en días. None si falta alguna."""
        if not self.montaje_fecha_inicio or not self.montaje_fecha_fin:
            return None
        return (self.montaje_fecha_fin - self.montaje_fecha_inicio).days

    @property
    def peso_desviacion_pct(self):
        """|peso_instalado - peso_diseno| / peso_diseno * 100. None si diseño=0/None.

        Decimal con 2 decimales.
        """
        if self.peso_diseno_kl is None or self.peso_instalado_kl is None:
            return None
        if self.peso_diseno_kl == 0:
            return None
        desv = abs(self.peso_instalado_kl - self.peso_diseno_kl) / self.peso_diseno_kl * Decimal('100')
        return desv.quantize(Decimal('0.01'))

    @property
    def peso_alerta(self):
        """True si la desviación de peso supera el umbral (5%). False si dentro
        o no calculable."""
        desv = self.peso_desviacion_pct
        if desv is None:
            return False
        return desv > UMBRAL_DESVIACION_PESO_PCT

    @property
    def avance_ponderado(self):
        """SUMPRODUCT(pesos, booleans) / 100 → valor 0..1.

        Pesos canónicos:
          estructura_en_sitio_ok 10 · prearmada_ok 20 ·
          torre_montada_ok 45 · revisada_ok 25
        """
        suma = Decimal('0')
        if self.estructura_en_sitio_ok:
            suma += PESO_ESTRUCTURA_SITIO
        if self.prearmada_ok:
            suma += PESO_PREARMADA
        if self.torre_montada_ok:
            suma += PESO_TORRE_MONTADA
        if self.revisada_ok:
            suma += PESO_REVISADA
        return suma / Decimal('100')

    @property
    def avance_ponderado_pct(self):
        """Avance ponderado como 0..100 con 1 decimal (para UI)."""
        return float((self.avance_ponderado * Decimal('100')).quantize(Decimal('0.1')))
