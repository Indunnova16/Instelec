"""
Global context processors for all templates.
"""
from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion

from .permissions import (
    SUBMODULO_FIN_CHECKLIST_FACTURACION,
    SUBMODULO_FIN_COSTOS_CUADRILLA,
    SUBMODULO_FIN_DASHBOARD,
    SUBMODULO_FIN_MAESTROS,
    SUBMODULO_FIN_NOMINA,
    SUBMODULO_FIN_PRESUPUESTO_PLANEADO,
    SUBMODULO_FIN_PRESUPUESTO_REAL,
    user_can_access_submodulo,
)
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
        'proyectos_construccion': ProyectoConstruccion.objects.filter(
            estado__in=['PLANIFICACION', 'EJECUCION', 'CIERRE', 'FINALIZADO'],
        ).select_related('contrato').order_by('contrato__codigo'),
        'unidad_negocio_actual': get_unidad_negocio(request),
    }


def financiero_menu_context(request):
    """Banderas `ok_fin_*` que gatean el submenu Financiero (Mantenimiento) del
    sidebar (#186 A3). Nunca se habian seteado -- el `{% if ok_fin_dashboard or
    ... %}` del sidebar era codigo muerto para TODOS los usuarios (encontrado
    por el validador-cierre adversarial de #261/#262: el menu Financiero
    completo estaba huerfano, no solo los Maestros nuevos)."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    return {
        'ok_fin_dashboard': user_can_access_submodulo(user, SUBMODULO_FIN_DASHBOARD),
        'ok_fin_presupuesto_planeado': user_can_access_submodulo(
            user, SUBMODULO_FIN_PRESUPUESTO_PLANEADO
        ),
        'ok_fin_presupuesto_real': user_can_access_submodulo(user, SUBMODULO_FIN_PRESUPUESTO_REAL),
        'ok_fin_checklist_facturacion': user_can_access_submodulo(
            user, SUBMODULO_FIN_CHECKLIST_FACTURACION
        ),
        'ok_fin_costos_cuadrilla': user_can_access_submodulo(user, SUBMODULO_FIN_COSTOS_CUADRILLA),
        'ok_fin_nomina': user_can_access_submodulo(user, SUBMODULO_FIN_NOMINA),
        'ok_fin_maestros': user_can_access_submodulo(user, SUBMODULO_FIN_MAESTROS),
    }
