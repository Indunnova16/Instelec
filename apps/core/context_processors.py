"""
Global context processors for all templates.
"""
from apps.contratos.models import Contrato


def modulo_context(request):
    """Inject construction and maintenance contracts into all templates."""
    return {
        'contratos_mantenimiento': Contrato.objects.filter(
            unidad_negocio='MANTENIMIENTO',
            estado='ACTIVO',
        ).order_by('codigo'),
        'contratos_construccion': Contrato.objects.filter(
            unidad_negocio='CONSTRUCCION',
            estado='ACTIVO',
        ).order_by('codigo'),
    }
