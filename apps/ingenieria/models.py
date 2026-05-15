from django.db import models
from apps.core.models import BaseModel
from apps.contratos.models import Contrato


DOCUMENTOS_CIVIL = [
    ('civil_suelos_estudio', 'Suelos', 'Diseño de estudio de suelos'),
    ('civil_suelos_informe', 'Suelos', 'Informe Geotécnico sitios de torre'),
    ('civil_rep_cartera', 'Replanteo Topográfico', 'Cartera de campo'),
    ('civil_rep_croquis', 'Replanteo Topográfico', 'Croquis de acceso'),
    ('civil_rep_diagonales', 'Replanteo Topográfico', 'Diagonales de patas'),
    ('civil_rep_cruces', 'Replanteo Topográfico', 'Formato de cruces de líneas'),
    ('civil_rep_fotos', 'Replanteo Topográfico', 'Fotografías'),
    ('civil_rep_informe', 'Replanteo Topográfico', 'Informe'),
    ('civil_rep_kmz', 'Replanteo Topográfico', 'KMZ'),
    ('civil_rep_planta', 'Replanteo Topográfico', 'Planta general'),
    ('civil_rep_tabla', 'Replanteo Topográfico', 'Tabla de torres'),
    ('civil_rep_curvas', 'Replanteo Topográfico', 'Curvas de nivel'),
    ('civil_rep_informe2', 'Replanteo Topográfico', 'Informe de replanteo'),
    ('civil_cim_criterios', 'Cimentaciones', 'Criterios de diseño de obra civil'),
    ('civil_cim_memoria', 'Cimentaciones', 'Memoria de cálculo de cimentaciones'),
    ('civil_cim_plano_loc', 'Cimentaciones', 'Plano de localización general'),
    ('civil_cim_plano_cim', 'Cimentaciones', 'Plano de cimentaciones'),
    ('civil_cim_plano_acc', 'Cimentaciones', 'Plano de localización de accesos'),
    ('civil_cim_plano_prot', 'Cimentaciones', 'Plano de obras de protecciones'),
    ('civil_spt_diseno', 'SPT', 'Diseño de SPT'),
    ('civil_spt_planos', 'SPT', 'Planos SPT'),
]

DOCUMENTOS_MONTAJE = [
    ('mont_tipo_a', 'Memorias estructurales', 'Memorias de diseño estructural tipo A'),
    ('mont_tipo_b', 'Memorias estructurales', 'Memorias de diseño estructural tipo B'),
    ('mont_tipo_c', 'Memorias estructurales', 'Memorias de diseño estructural tipo C'),
    ('mont_tipo_d', 'Memorias estructurales', 'Memorias de diseño estructural tipo D'),
    ('mont_tipo_esp', 'Memorias estructurales', 'Memorias de diseño estructural tipo especial'),
    ('mont_planos', 'Memorias estructurales', 'Planos según el tipo de torre'),
]

DOCUMENTOS_TENDIDO = [
    ('tend_criterio_elec', 'Diseño Eléctrico', 'Criterio de diseños electromecánicos'),
    ('tend_param_met', 'Diseño Eléctrico', 'Informe de parámetros meteorológicos'),
    ('tend_cantidades', 'Diseño Eléctrico', 'Listado de cantidades electromecánicas'),
    ('tend_resistividad', 'Diseño Eléctrico', 'Informe de medida resistividad'),
    ('tend_spt_memoria', 'Diseño Eléctrico', 'Memoria de cálculo de SPT'),
    ('tend_aislamiento', 'Diseño Eléctrico', 'Selección de aislamiento'),
    ('tend_arboles_carga', 'Diseño Eléctrico', 'Árboles de carga'),
    ('tend_herrajes', 'Diseño Eléctrico', 'Memoria de cálculo de herrajes y aisladores'),
    ('tend_plantillado', 'Diseño Eléctrico', 'Informe plantillado'),
    ('tend_tabla_tendido', 'Diseño Eléctrico', 'Tabla de tendido y regulación'),
    ('tend_amortiguamiento', 'Diseño Eléctrico', 'Sistema de amortiguamiento'),
    ('tend_desviadores', 'Diseño Eléctrico', 'Plano de ubicación de desviadores de vuelo'),
    ('tend_tabla_est', 'Diseño Eléctrico', 'Tabla de estructuras'),
    ('tend_riesgos', 'Diseño Eléctrico', 'Análisis de riesgos de origen'),
    ('tend_interferencia', 'Diseño Eléctrico', 'Estudio de interferencia electromagnética'),
    ('tend_puesta_tierra', 'Diseño Eléctrico', 'Sistema de puesta a tierra de estructuras'),
    ('tend_secuencias', 'Diseño Eléctrico', 'Secuencias de fases de la línea'),
    ('tend_pl_distancias', 'Planos', 'Planos de distancias eléctricas'),
    ('tend_pl_porticos', 'Planos', 'Planos de llegada a pórticos'),
    ('tend_pl_silueta', 'Planos', 'Planos de silueta'),
    ('tend_pl_arboles', 'Planos', 'Planos de árboles de carga'),
    ('tend_pl_cruces', 'Planos', 'Planos de cruce con infraestructura existente'),
    ('tend_pl_plantillado', 'Planos', 'Planos de plantillado final de la línea'),
    ('tend_pl_perfil', 'Planos', 'Planos de perfil definitivo'),
    ('tend_pl_extension', 'Planos', 'Planos de extensión de patas'),
    ('tend_pl_marcacion', 'Planos', 'Planos de marcación de estructura'),
    ('tend_pl_senalizacion', 'Planos', 'Planos de señalización'),
    ('tend_pl_conjunto', 'Planos', 'Planos de conjunto'),
]

DOCUMENTOS_POR_CATEGORIA = {
    'CIVIL': DOCUMENTOS_CIVIL,
    'MONTAJE': DOCUMENTOS_MONTAJE,
    'TENDIDO': DOCUMENTOS_TENDIDO,
}


class TorreContrato(BaseModel):
    contrato = models.ForeignKey(
        Contrato,
        on_delete=models.CASCADE,
        related_name='torres',
        verbose_name='Contrato',
    )
    nombre = models.CharField('Nombre de torre', max_length=20)
    orden = models.PositiveIntegerField('Orden', default=0)
    # Soft-delete: al reducir `numero_torres` en el contrato, las torres
    # sobrantes se marcan `archivada=True` para preservar histórico de
    # IngenieriaEstado / PredialTorre / AmbientalTorre / ActividadEstado.
    archivada = models.BooleanField('Archivada', default=False, db_index=True)

    class Meta:
        db_table = 'ingenieria_torres'
        ordering = ['orden', 'nombre']
        unique_together = ('contrato', 'nombre')

    def __str__(self):
        return f"{self.contrato.codigo} - {self.nombre}"


class IngenieriaEstado(BaseModel):
    class Estado(models.TextChoices):
        CUMPLE = 'CUMPLE', 'Cumple'
        NO_CUMPLE = 'NO_CUMPLE', 'No Cumple'
        NO_APLICA = 'NO_APLICA', 'No Aplica'

    class Categoria(models.TextChoices):
        CIVIL = 'CIVIL', 'Civil'
        MONTAJE = 'MONTAJE', 'Montaje'
        TENDIDO = 'TENDIDO', 'Tendido'

    torre = models.ForeignKey(
        TorreContrato,
        on_delete=models.CASCADE,
        related_name='estados',
        verbose_name='Torre',
    )
    categoria = models.CharField('Categoría', max_length=10, choices=Categoria.choices)
    documento_codigo = models.CharField('Código documento', max_length=50)
    estado = models.CharField(
        'Estado',
        max_length=10,
        choices=Estado.choices,
        null=True,
        blank=True,
    )
    observacion = models.TextField('Observación', blank=True, default='')

    class Meta:
        db_table = 'ingenieria_estados'
        unique_together = ('torre', 'categoria', 'documento_codigo')

    def __str__(self):
        return f"{self.torre} | {self.documento_codigo} | {self.estado}"
