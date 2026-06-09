"""B2a (#74) — ObraCivilTorreDetalle paridad campo-a-campo con Excel CANT OOCC.

Granularidad torre × pata (4 patas A/B/C/D, unique_together).
~110 campos en 7 secciones (Identidad + Cerramiento + Excavación + Solado +
Acero + Vaciado + Compactación + trailer).

`avance_ponderado` calcula SUMPRODUCT(pesos del proyecto, avances de cada
sección) — mismos pesos editables de ProyectoConstruccion (#61).

ObraCivilTorre (legacy, agregada por torre) sigue existiendo como cache para
dashboards rápidos; un signal post_save de este modelo la recalcula tomando
el promedio de las 4 patas.
"""
import uuid
from decimal import Decimal

from django.db import models

from apps.core.models import BaseModel


# ---------------------------------------------------------------------------
# Choices declarativos
# ---------------------------------------------------------------------------

PATA_CHOICES = [
    ('A', 'Pata A'),
    ('B', 'Pata B'),
    ('C', 'Pata C'),
    ('D', 'Pata D'),
]

EXC_TIPO_CHOICES = [
    ('MANUAL', 'Manual'),
    ('MAQUINA', 'Con máquina'),
    ('HELICOIDAL', 'Helicoidal'),
]

EXC_MONITOREO_CHOICES = [
    ('EJECUCION', 'En ejecución'),
    ('LIBERADA', 'Liberada'),
]

VAC_TIPO_CONCRETO_CHOICES = [
    ('PREMEZCLADO', 'Premezclado'),
    ('OBRA', 'Hecho en obra'),
]


class ObraCivilTorreDetalle(BaseModel):
    """Detalle CANT OOCC paridad Excel — torre × pata, ~110 campos en 7 secciones.

    Paridad campo-a-campo con `Documentacion/Obra civil.xlsx` hoja CANT OOCC.
    El registro existe por cada pata (A/B/C/D) de cada torre; el avance
    ponderado de la pata se calcula con los pesos editables del proyecto.

    El cache ObraCivilTorre.avance_* (modelo legacy, #74) se refresca
    automáticamente vía signal en post_save (promedio sobre las 4 patas).
    """

    # =====================================================================
    # 1. Identidad (5)
    # =====================================================================
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='obra_civil_detalles',
        verbose_name='Proyecto',
    )
    torre = models.ForeignKey(
        'construccion.TorreConstruccion',
        on_delete=models.CASCADE,
        related_name='obra_civil_detalles',
        verbose_name='Torre',
    )
    pata = models.CharField(
        'Pata', max_length=1, choices=PATA_CHOICES,
    )
    diseno_construido = models.CharField(
        'Diseño construido', max_length=50, blank=True,
        help_text='Código/tipo del diseño efectivamente construido por pata.',
    )
    replanteo_topografico_ok = models.BooleanField(
        'Replanteo topográfico OK', default=False,
    )

    # =====================================================================
    # 2. Cerramiento (5)
    # =====================================================================
    cerr_madera_un = models.PositiveIntegerField(
        'Cerramiento — madera (un)', null=True, blank=True,
    )
    cerr_lona_m = models.DecimalField(
        'Cerramiento — lona o alambre de púa (m)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    cerr_senalizacion_ok = models.BooleanField(
        'Cerramiento — señalización OK', default=False,
    )
    cerr_notas = models.TextField('Cerramiento — notas', blank=True)
    cerr_finalizado_ok = models.BooleanField(
        'Cerramiento finalizado', default=False,
        help_text='Equivalente al ok del bloque secuencial de PataObra (#53).',
    )

    # =====================================================================
    # 3. Excavación (16)
    # =====================================================================
    exc_cuadrilla = models.CharField(
        'Excavación — cuadrilla', max_length=100, blank=True,
    )
    # 8 FT (Formatos Técnicos) booleans del Excel CANT OOCC
    exc_ft022_ok = models.BooleanField('FT-022 OK', default=False)
    exc_ft929_ok = models.BooleanField('FT-929 OK', default=False)
    exc_ft923_ok = models.BooleanField('FT-923 OK', default=False)
    exc_ft924_ok = models.BooleanField('FT-924 OK', default=False)
    exc_ft925_ok = models.BooleanField('FT-925 OK', default=False)
    exc_ft926_ok = models.BooleanField('FT-926 OK', default=False)
    exc_ft927_ok = models.BooleanField('FT-927 OK', default=False)
    exc_ft928_ok = models.BooleanField('FT-928 OK', default=False)
    exc_tipo = models.CharField(
        'Tipo excavación', max_length=20, choices=EXC_TIPO_CHOICES, blank=True,
    )
    exc_metros_m3 = models.DecimalField(
        'Excavación (m3)', max_digits=10, decimal_places=2,
        null=True, blank=True,
    )
    exc_penetrometro_ok = models.BooleanField(
        'Penetrómetro OK', default=False,
    )
    exc_monitoreo_arq = models.CharField(
        'Monitoreo arqueológico', max_length=20,
        choices=EXC_MONITOREO_CHOICES, blank=True,
    )
    exc_ejecutada_pct = models.DecimalField(
        '% Excavación ejecutada', max_digits=5, decimal_places=4,
        default=Decimal('0'),
        help_text='0–1 (peso 0.30 del avance ponderado por defecto).',
    )
    exc_observaciones = models.TextField(
        'Excavación — observaciones', blank=True,
    )

    # =====================================================================
    # 4. Solado (20) — sub-bloques agua/arena/grava/cemento × (calc/real/obs)
    # =====================================================================
    sol_ingreso_materiales = models.BooleanField(
        'Solado — ingreso materiales OK', default=False,
    )
    # Agua
    sol_agua_calc = models.DecimalField(
        'Solado agua (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_agua_real = models.DecimalField(
        'Solado agua (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_agua_obs = models.CharField(
        'Solado agua (obs)', max_length=200, blank=True,
    )
    # Arena
    sol_arena_calc = models.DecimalField(
        'Solado arena (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_arena_real = models.DecimalField(
        'Solado arena (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_arena_obs = models.CharField(
        'Solado arena (obs)', max_length=200, blank=True,
    )
    # Grava
    sol_grava_calc = models.DecimalField(
        'Solado grava (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_grava_real = models.DecimalField(
        'Solado grava (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_grava_obs = models.CharField(
        'Solado grava (obs)', max_length=200, blank=True,
    )
    # Cemento
    sol_cemento_calc = models.DecimalField(
        'Solado cemento (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_cemento_real = models.DecimalField(
        'Solado cemento (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    sol_cemento_obs = models.CharField(
        'Solado cemento (obs)', max_length=200, blank=True,
    )
    sol_soldadura_prolongas_ok = models.BooleanField(
        'Solado — soldadura prolongas OK', default=False,
    )
    sol_ejecutado_pct = models.DecimalField(
        '% Solado ejecutado', max_digits=5, decimal_places=4,
        default=Decimal('0'),
        help_text='0–1 (peso 0.05 por defecto).',
    )
    sol_observaciones = models.TextField(
        'Solado — observaciones', blank=True,
    )

    # =====================================================================
    # 5. Acero (12)
    # =====================================================================
    ace_ingreso = models.BooleanField('Acero — ingreso OK', default=False)
    ace_ft028_ok = models.BooleanField('FT-028 OK', default=False)
    ace_ft930_ok = models.BooleanField('FT-930 OK', default=False)
    ace_corte_flejado_ok = models.BooleanField(
        'Acero — corte/flejado OK', default=False,
    )
    ace_armado_sitio_ok = models.BooleanField(
        'Acero — armado en sitio OK', default=False,
    )
    ace_spt_herramientas_ok = models.BooleanField(
        'Acero — SPT herramientas OK', default=False,
    )
    ace_solicitado_kg = models.DecimalField(
        'Acero solicitado (kg)', max_digits=10, decimal_places=2,
        null=True, blank=True,
    )
    ace_instalado_kg = models.DecimalField(
        'Acero instalado (kg)', max_digits=10, decimal_places=2,
        null=True, blank=True,
    )
    ace_observaciones = models.TextField(
        'Acero — observaciones', blank=True,
    )
    ace_instalacion_pct = models.DecimalField(
        '% Acero instalado', max_digits=5, decimal_places=4,
        default=Decimal('0'),
        help_text='0–1 (peso 0.10 por defecto).',
    )
    ace_instalacion_obs = models.TextField(
        'Acero instalación — observaciones', blank=True,
    )

    # =====================================================================
    # 6. Vaciado (32)
    # =====================================================================
    vac_ft916_ok = models.BooleanField('FT-916 OK', default=False)
    vac_nivelacion_stub_ok = models.BooleanField(
        'Vaciado — nivelación stub OK', default=False,
    )
    vac_encofrado_ok = models.BooleanField(
        'Vaciado — encofrado OK', default=False,
    )
    vac_ingreso_materiales = models.BooleanField(
        'Vaciado — ingreso materiales OK', default=False,
    )
    vac_it380_ok = models.BooleanField('IT-380 OK', default=False)
    vac_ft056_ok = models.BooleanField('FT-056 OK', default=False)
    vac_tipo_concreto = models.CharField(
        'Tipo de concreto', max_length=20,
        choices=VAC_TIPO_CONCRETO_CHOICES, blank=True,
    )
    vac_mpa_teorica = models.PositiveSmallIntegerField(
        'MPa teórica', null=True, blank=True,
        help_text='Resistencia esperada (ej. 21, 28).',
    )
    # Sub-bloques agua/arena/grava/cemento × (calc/real/obs)
    vac_agua_calc = models.DecimalField(
        'Vaciado agua (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_agua_real = models.DecimalField(
        'Vaciado agua (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_agua_obs = models.CharField(
        'Vaciado agua (obs)', max_length=200, blank=True,
    )
    vac_arena_calc = models.DecimalField(
        'Vaciado arena (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_arena_real = models.DecimalField(
        'Vaciado arena (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_arena_obs = models.CharField(
        'Vaciado arena (obs)', max_length=200, blank=True,
    )
    vac_grava_calc = models.DecimalField(
        'Vaciado grava (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_grava_real = models.DecimalField(
        'Vaciado grava (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_grava_obs = models.CharField(
        'Vaciado grava (obs)', max_length=200, blank=True,
    )
    vac_cemento_calc = models.DecimalField(
        'Vaciado cemento (calc)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_cemento_real = models.DecimalField(
        'Vaciado cemento (real)', max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    vac_cemento_obs = models.CharField(
        'Vaciado cemento (obs)', max_length=200, blank=True,
    )
    vac_slump_ok = models.BooleanField('Vaciado — slump OK', default=False)
    vac_fecha_vaciado = models.DateField(
        'Fecha vaciado', null=True, blank=True,
        help_text='Trigger alarmas cilindros 7/14/21/51 días (#55).',
    )
    vac_fecha_cilindros = models.DateField(
        'Fecha toma de cilindros', null=True, blank=True,
    )
    vac_inspeccion_stub_ok = models.BooleanField(
        'Vaciado — inspección stub OK', default=False,
    )
    vac_encargado_puntas = models.CharField(
        'Vaciado — encargado de puntas', max_length=100, blank=True,
    )
    vac_desencofrado_ok = models.BooleanField(
        'Vaciado — desencofrado OK', default=False,
    )
    vac_ejecutado_pct = models.DecimalField(
        '% Vaciado ejecutado', max_digits=5, decimal_places=4,
        default=Decimal('0'),
        help_text='0–1 (peso 0.30 por defecto).',
    )
    vac_observaciones = models.TextField(
        'Vaciado — observaciones', blank=True,
    )

    # =====================================================================
    # 7. Compactación (7)
    # =====================================================================
    com_ft914_ok = models.BooleanField('FT-914 OK', default=False)
    com_suelo_natural_ok = models.BooleanField(
        'Compactación — suelo natural OK', default=False,
    )
    com_suelo_cemento_ok = models.BooleanField(
        'Compactación — suelo cemento OK', default=False,
    )
    com_suelo_prestamo_ok = models.BooleanField(
        'Compactación — suelo préstamo OK', default=False,
    )
    com_volumen_m3 = models.DecimalField(
        'Compactación — volumen (m3)', max_digits=10, decimal_places=2,
        null=True, blank=True,
    )
    com_finalizada_pct = models.DecimalField(
        '% Compactación finalizada', max_digits=5, decimal_places=4,
        default=Decimal('0'),
        help_text='0–1 (peso 0.15 por defecto).',
    )
    com_observaciones = models.TextField(
        'Compactación — observaciones', blank=True,
    )

    # =====================================================================
    # 8. Trailer (2)
    # =====================================================================
    ejecutado_por = models.CharField(
        'Ejecutado por', max_length=100, blank=True,
    )
    comentario_general = models.TextField(
        'Comentario general', blank=True,
    )

    class Meta:
        db_table = 'construccion_oc_detalle'
        verbose_name = 'Obra Civil — Detalle por pata'
        verbose_name_plural = 'Obra Civil — Detalle por pata'
        unique_together = [('torre', 'pata')]
        ordering = ['torre__numero', 'pata']

    def __str__(self):
        return f"{self.torre.numero_display} - Pata {self.pata} (CANT OOCC)"

    # =====================================================================
    # Computed properties — avance ponderado y desviaciones sub-bloques
    # =====================================================================

    SECCIONES_PESO = [
        ('cerr_finalizado_ok', 'peso_cerramiento_pct', True),
        ('exc_ejecutada_pct', 'peso_excavacion_pct', False),
        ('sol_ejecutado_pct', 'peso_solado_pct', False),
        ('ace_instalacion_pct', 'peso_acero_pct', False),
        ('vac_ejecutado_pct', 'peso_vaciado_pct', False),
        ('com_finalizada_pct', 'peso_compactacion_pct', False),
    ]

    @property
    def avance_ponderado(self):
        """SUMPRODUCT(pesos del proyecto, avance por sección) / 100.

        Mismos pesos editables que ObraCivilTorre (#61). Para cerramiento
        usa el booleano `cerr_finalizado_ok` como 1.0 / 0.0; el resto son
        `*_pct` decimales 0–1.
        """
        suma = Decimal('0')
        total_peso = 0
        for campo, atributo_peso, es_bool in self.SECCIONES_PESO:
            peso = getattr(self.proyecto, atributo_peso, 0) or 0
            total_peso += peso
            valor = getattr(self, campo)
            if es_bool:
                avance = Decimal('1') if valor else Decimal('0')
            else:
                avance = Decimal(valor or 0)
            suma += avance * Decimal(peso)
        if total_peso == 0:
            return Decimal('0')
        return suma / Decimal(total_peso)

    @property
    def avance_ponderado_pct(self):
        """avance_ponderado expresado como float 0–100 con 1 decimal."""
        return round(float(self.avance_ponderado) * 100, 1)

    # ----- Desviaciones sub-bloques Solado (calc vs real) -----

    @staticmethod
    def _desv(real, calc):
        """Diferencia real - calc; None si falta alguno."""
        if real is None or calc is None:
            return None
        return Decimal(real) - Decimal(calc)

    @property
    def sol_agua_desv(self):
        return self._desv(self.sol_agua_real, self.sol_agua_calc)

    @property
    def sol_arena_desv(self):
        return self._desv(self.sol_arena_real, self.sol_arena_calc)

    @property
    def sol_grava_desv(self):
        return self._desv(self.sol_grava_real, self.sol_grava_calc)

    @property
    def sol_cemento_desv(self):
        return self._desv(self.sol_cemento_real, self.sol_cemento_calc)

    # ----- Desviaciones sub-bloques Vaciado (calc vs real) -----

    @property
    def vac_agua_desv(self):
        return self._desv(self.vac_agua_real, self.vac_agua_calc)

    @property
    def vac_arena_desv(self):
        return self._desv(self.vac_arena_real, self.vac_arena_calc)

    @property
    def vac_grava_desv(self):
        return self._desv(self.vac_grava_real, self.vac_grava_calc)

    @property
    def vac_cemento_desv(self):
        return self._desv(self.vac_cemento_real, self.vac_cemento_calc)

    # ----- Desviación Acero -----

    @property
    def ace_desviacion_kg(self):
        """Acero instalado - solicitado (kg). None si falta alguno."""
        return self._desv(self.ace_instalado_kg, self.ace_solicitado_kg)
