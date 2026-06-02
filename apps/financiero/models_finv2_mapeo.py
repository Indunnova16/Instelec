"""
Mapeo contable v2 (financiero) — B1 (#120).

Relaciona cada "Cuenta equivalente" (columna O de la BD contable) con un
rubro presupuestal de la estructura de Presupuesto Planeado. El importador
``ContableCompleteImporter`` usa estos mapeos para agrupar las transacciones
(suma de la columna C, "Neto") en rubros. Las cuentas equivalentes sin mapeo
caen en el rubro fijo "Otros / No Clasificado".
"""
from django.db import models

from apps.core.models import BaseModel


# Rubro destino para cuentas equivalentes sin mapeo explícito.
RUBRO_NO_CLASIFICADO = 'Otros / No Clasificado'


# Mapeo por defecto (semilla) usado cuando aún no existen registros
# MapeoCtaRubro en la BD. Las llaves son la "Cta equivalente" (columna O)
# tal como aparece en el Excel real; el match se hace normalizando a
# minúsculas/espacios/sin acentos (ver ContableCompleteImporter._norm).
#
# Derivado de las 31 cuentas equivalentes reales presentes en
# 'BASE DE DATOS.xlsx' (hoja BD). Las no listadas caen en
# RUBRO_NO_CLASIFICADO y se reclasifican via el CRUD de MapeoCtaRubro.
MAPEO_CTA_RUBRO_DEFAULT = {
    # ── Ingresos ──
    'ingresos operacionales': 'Ingresos Operacionales',
    'otros ingresos': 'Otros Ingresos',
    'lineas de transmision': 'Líneas de Transmisión',
    # ── Personal ──
    'salarios': 'Personal',
    'administrativos': 'Personal',
    'prestaciones sociales': 'Personal',
    'aportes parafiscales': 'Personal',
    'seguridad social': 'Personal',
    'gastos de personal': 'Personal',
    'auxilio de transporte': 'Personal',
    'gastos de viaje': 'Personal',
    'viaticos reembolsable': 'Personal',
    'alimentacion': 'Personal',
    'hidratacion': 'Personal',
    'dotacion': 'Personal',
    # ── Transporte ──
    'conductores': 'Transporte',
    'combustible': 'Transporte',
    'transporte': 'Transporte',
    'mantenimiento transporte': 'Transporte',
    # ── Materiales y Herramientas ──
    'materiales': 'Materiales y Herramientas',
    'equipos y herramientas': 'Materiales y Herramientas',
    # ── Subcontratos ──
    'subcontratistas': 'Subcontratos',
    # ── Servicios e Infraestructura ──
    'arrendamiento': 'Servicios e Infraestructura',
    'leasing': 'Servicios e Infraestructura',
    'servicios publicos': 'Servicios e Infraestructura',
    'vigilancia': 'Servicios e Infraestructura',
    'sst': 'Servicios e Infraestructura',
    'cif': 'Servicios e Infraestructura',
    # ── Gastos financieros y otros ──
    'intereses': 'Intereses',
    'financieros': 'Intereses',
    'depreciacion': 'Otros Gastos',
    'seguros': 'Otros Gastos',
}


class MapeoCtaRubro(BaseModel):
    """
    Mapea una cuenta equivalente contable a un rubro presupuestal.

    Modelo de catálogo editable (CRUD inline en la pestaña "Presupuesto
    Planeado") que sobreescribe / extiende ``MAPEO_CTA_RUBRO_DEFAULT``.
    """

    cta_equivalente = models.CharField(
        'Cuenta equivalente',
        max_length=255,
        help_text='Valor de la columna O ("Cta equivalente") de la BD contable.',
    )
    rubro_presupuestal = models.CharField(
        'Rubro presupuestal',
        max_length=255,
        help_text='Rubro de la estructura de presupuesto al que se agrupa.',
    )
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'financiero_mapeo_cta_rubro'
        verbose_name = 'Mapeo cuenta → rubro'
        verbose_name_plural = 'Mapeos cuenta → rubro'
        ordering = ['rubro_presupuestal', 'cta_equivalente']

    def __str__(self):
        estado = '' if self.activo else ' (inactivo)'
        return f'{self.cta_equivalente} → {self.rubro_presupuestal}{estado}'
