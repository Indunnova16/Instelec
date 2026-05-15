"""
Global context processors for all templates.
"""
from apps.contratos.models import Contrato

from .utils import get_unidad_negocio


def modulo_context(request):
    """Inject construction and maintenance contracts + active business unit."""
    return {
        'contratos_mantenimiento': Contrato.objects.filter(
            unidad_negocio='MANTENIMIENTO',
            estado='ACTIVO',
        ).order_by('codigo'),
        'contratos_construccion': Contrato.objects.filter(
            unidad_negocio='CONSTRUCCION',
            estado='ACTIVO',
        ).order_by('codigo'),
        'unidad_negocio_actual': get_unidad_negocio(request),
    }
