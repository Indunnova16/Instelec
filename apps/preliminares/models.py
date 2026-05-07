from django.db import models

from apps.core.models import BaseModel
from apps.ingenieria.models import TorreContrato


# ── Socio-Predial ────────────────────────────────────────────────────────────

class PredialTorre(BaseModel):
    """Datos socio-prediales por torre. Un registro por torre."""

    torre = models.OneToOneField(
        TorreContrato,
        on_delete=models.CASCADE,
        related_name='predial',
        verbose_name='Torre',
    )

    # Info básica (texto libre)
    departamento        = models.CharField('Departamento',        max_length=100, blank=True)
    municipio           = models.CharField('Municipio',           max_length=100, blank=True)
    unidad_territorial  = models.CharField('Unidad Territorial',  max_length=200, blank=True)
    predio              = models.CharField('Predio',              max_length=200, blank=True)
    propietario         = models.CharField('Propietario',         max_length=200, blank=True)
    telefono            = models.CharField('Teléfono',            max_length=50,  blank=True)

    # Fechas de gestión
    socializacion       = models.DateField('Socialización del proyecto', null=True, blank=True)
    acta_vecindad       = models.DateField('Actas de vecindad',          null=True, blank=True)
    acta_acceso_com     = models.DateField('Acta acceso comunitario',     null=True, blank=True)
    autorizacion_prop   = models.DateField('Autorización propietario',    null=True, blank=True)
    acta_acceso_priv    = models.DateField('Acta acceso privado',         null=True, blank=True)

    # Liberación (Sí / No)
    liberacion_predial  = models.BooleanField('Liberación predial', null=True, blank=True)

    # Semáforo — calculado (pendiente implementar lógica)
    # semaforo_social se derivará de los campos anteriores

    # Observaciones
    observaciones       = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'preliminares_predial'

    def __str__(self):
        return f"{self.torre} — Predial"


# ── Socio-Ambiental ──────────────────────────────────────────────────────────

class AmbientalTorre(BaseModel):
    """Datos socio-ambientales por torre. Un registro por torre."""

    torre = models.OneToOneField(
        TorreContrato,
        on_delete=models.CASCADE,
        related_name='ambiental',
        verbose_name='Torre',
    )

    # Campos de fecha (guardar "YYYY-MM-DD" o "NA" o vacío "")
    ahuyentamiento       = models.CharField('Ahuyentamiento de especies',        max_length=10, blank=True)
    conteo_epifitas      = models.CharField('Conteo de plantas epifitas',        max_length=10, blank=True)
    traslado_vivero      = models.CharField('Traslado a vivero de plantas',      max_length=10, blank=True)
    reubicacion_epifitas = models.CharField('Reubicación de plantas epifitas',  max_length=10, blank=True)
    aprov_sitio          = models.CharField('Aprov. forestal sitio de torre',    max_length=10, blank=True)

    # Ok / No Ok / N/A (CharField con choices)
    arqueologia_poligonos = models.CharField(
        'Arqueología polígonos/ICANH',
        max_length=10,
        choices=[('', '—'), ('OK', 'Ok'), ('NO_OK', 'No Ok'), ('NA', 'N/A')],
        blank=True
    )

    # Números: kilómetros y porcentaje
    adecuacion_accesos   = models.DecimalField('Adecuación de accesos (km)',   max_digits=8, decimal_places=2, null=True, blank=True)
    accesos_intervenidos = models.DecimalField('Accesos intervenidos (km)',    max_digits=8, decimal_places=2, null=True, blank=True)
    avance_rescate       = models.DecimalField('Avance del rescate (%)',       max_digits=5, decimal_places=1, null=True, blank=True)

    # Booleanos: Sí / No (null=True para 3 estados)
    liberacion_pdo        = models.BooleanField('Liberación predial PDO',       null=True, blank=True)
    aprov_vano            = models.BooleanField('Aprov. forestal vano',         null=True, blank=True)
    rescate_arqueologico  = models.BooleanField('Rescate arqueológico',         null=True, blank=True)

    # Observaciones
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'preliminares_ambiental'

    def __str__(self):
        return f"{self.torre} — Ambiental"


# Legacy — solo referencia, no usado en las nuevas vistas
DOCUMENTOS_AMBIENTAL_LEGACY = [
    ('amb_ahuyentamiento',       'Flora y Fauna',            'Ahuyentamiento de especies'),
    ('amb_conteo_epifitas',      'Flora y Fauna',            'Conteo de plantas epifitas a reubicar'),
    ('amb_traslado_vivero',      'Flora y Fauna',            'Traslado a vivero de plantas epifitas'),
    ('amb_reubicacion_epifitas', 'Flora y Fauna',            'Reubicación de plantas epifitas'),
    ('amb_aprov_sitio',          'Aprovechamiento Forestal', 'Aprov. forestal sitio de torre'),
    ('amb_aprov_vano',           'Aprovechamiento Forestal', 'Aprov. forestal vano'),
    ('amb_arqueologia_polig',    'Arqueología',              'Arqueología polígonos/ICANH'),
    ('amb_arqueologia_torre',    'Arqueología',              'Arqueología torre'),
    ('amb_rescate',              'Arqueología',              'Rescate arqueológico'),
    ('amb_avance_rescate',       'Arqueología',              'Avance del rescate'),
    ('amb_cambio_menor',         'Licencias',                'Cambio menor L.A.'),
    ('amb_adecuacion_accesos',   'Accesos',                  'Adecuación de accesos'),
    ('amb_accesos_intervenidos', 'Accesos',                  'Accesos intervenidos'),
    ('amb_liberacion_pdo',       'Liberación',               'Liberación predial PDO'),
    ('amb_semaforo',             'Semáforo',                 'Semáforo liberación ambiental'),
]


class ActividadEstado(BaseModel):
    """Estado CUMPLE/NC/NA por torre y actividad ambiental."""

    class Estado(models.TextChoices):
        CUMPLE    = 'CUMPLE',    'Cumple'
        NO_CUMPLE = 'NO_CUMPLE', 'No Cumple'
        NO_APLICA = 'NO_APLICA', 'No Aplica'

    torre            = models.ForeignKey(
        TorreContrato,
        on_delete=models.CASCADE,
        related_name='act_estados',
        verbose_name='Torre',
    )
    documento_codigo = models.CharField('Código documento', max_length=50)
    estado           = models.CharField(
        'Estado', max_length=10,
        choices=Estado.choices,
        null=True, blank=True,
    )
    observacion      = models.TextField('Observación', blank=True, default='')

    class Meta:
        db_table        = 'preliminares_estados'
        unique_together = ('torre', 'documento_codigo')

    def __str__(self):
        return f"{self.torre} | {self.documento_codigo} | {self.estado}"
