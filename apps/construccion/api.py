"""
API endpoints — Presupuesto de Construcción (Django Ninja).

Instelec#267 A9 — expone el presupuesto PLANEADO de un proyecto/período
puntual para que **#246 (Indicadores Financieros)** lo consuma sin acoplarse
a la vista HTML. Mismo patrón que el resto del portafolio de rutas ya
registradas (``apps/usuarios/api.py``, ``apps/actividades/api.py``,
``apps/cuadrillas/api.py``, ``apps/lineas/api.py``, ``apps/campo/api.py``):
``Router(auth=...)`` explícito a nivel de router — **nunca** implícito, ver
``apps/api/router.py`` (``NinjaAPI(auth=JWTAuth())`` a nivel de instancia NO
alcanza si el router hijo no declara su propio ``auth``: el patrón vigente en
este repo es que CADA router declare el suyo).

Response shape EXACTO del ejemplo del issue (Fase 6.2):

    GET /api/presupuesto/{proyecto_id}/periodo/{mes}/{año}
    {
      "periodo": "09/2026",
      "proyecto": "QA-#49",
      "costos_fijos": 4243284093,
      "costos_variables": 2813662061,
      "ingresos": -23511292673,
      "total_año": 1058633482
    }

Reusa ``_kpi_cards_finv2_bd`` (A5, ``views_fin.py``) para la agrupación por
Clasificación real — mismo criterio que las KPI cards de la UI (Fase 4) —
restringido al MES/AÑO pedidos: A5 agrega el AÑO completo sobre
``filas_detalle``, acá se filtra esa misma lista por ``mes``/``anio`` ANTES
de agrupar, para no mezclar otros meses en la respuesta de un período
puntual. ``total_año`` (Fase 3, "Total Año" del % de la tabla Rubros) es la
suma CRUDA de ``valor`` de todas las filas del período, sin filtrar por
Clasificación — coherente con cómo ``_construir_finv2_bd_desde_filas_planas``
calcula ``finv2_bd['total']`` (suma de TODOS los rubros, no solo unos).
"""
from decimal import Decimal
from uuid import UUID

from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router

from apps.api.auth import JWTAuth

from .models import ProyectoConstruccion
from . import gastos_real
from .models_fin import GastoRealConstruccion, PresupuestoDetalladoConstruccion
from .views_fin import _kpi_cards_finv2_bd, _to_decimal

router = Router(auth=JWTAuth())


@router.get('/presupuesto/{proyecto_id}/periodo/{mes}/{anio}')
def presupuesto_periodo(
    request: HttpRequest, proyecto_id: UUID, mes: int, anio: int,
) -> dict:
    """Presupuesto PLANEADO de un proyecto para un mes/año puntual.

    404 (nunca un 200 con ceros — un consumidor automatizado como #246 no
    puede distinguir "presupuesto en cero" de "sin dato") cuando:
    - el ``mes`` está fuera de ``1..12``,
    - el proyecto no existe,
    - no hay ``PresupuestoDetalladoConstruccion`` PLANEADO para ese ``anio``,
    - o ninguna fila de ``filas_detalle`` cae exactamente en ese mes/año
      (presupuesto legacy sin formato plano A2, o simplemente el período
      pedido no fue cargado todavía).
    """
    if not 1 <= mes <= 12:
        raise Http404('Mes fuera de rango (1..12)')

    proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

    presupuesto = PresupuestoDetalladoConstruccion.objects.filter(
        proyecto=proyecto, anio=anio,
        tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
    ).first()
    if presupuesto is None:
        raise Http404('No hay presupuesto planeado cargado para ese año')

    datos = presupuesto.datos or {}
    filas = ((datos.get('finv2_bd') or {}).get('filas_detalle')) or []
    filas_periodo = [
        f for f in filas
        if isinstance(f, dict) and f.get('mes') == mes and f.get('anio') == anio
    ]
    if not filas_periodo:
        raise Http404('No hay datos de presupuesto para ese mes/año')

    kpi = _kpi_cards_finv2_bd({'finv2_bd': {'filas_detalle': filas_periodo}})
    total_periodo = sum(
        (_to_decimal(f.get('valor')) for f in filas_periodo), Decimal('0'),
    )

    return {
        'periodo': f'{mes:02d}/{anio}',
        'proyecto': proyecto.nombre,
        'costos_fijos': float(kpi['costos_fijos']),
        'costos_variables': float(kpi['costos_variables']),
        'ingresos': float(kpi['ingreso']),
        'total_año': float(total_periodo),
    }


@router.get('/presupuesto-real/{proyecto_id}/periodo/{mes}/{anio}')
def presupuesto_real_periodo(
    request: HttpRequest, proyecto_id: UUID, mes: int, anio: int,
) -> dict:
    """Instelec#268 — gasto REAL vs presupuesto planeado de un mes puntual,
    para #246 (Indicadores Financieros). Shape del ejemplo del issue.

    ``por_rubro`` lista cada Cuenta Equiv (Prestaciones Sociales, Seguridad
    Social…) con su rubro presupuestal. 404 si el mes está fuera de rango, el
    proyecto no existe o no hay gastos reales cargados para ese período.
    """
    if not 1 <= mes <= 12:
        raise Http404('Mes fuera de rango (1..12)')
    proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
    periodo = f'{anio}{mes:02d}'
    if not GastoRealConstruccion.objects.filter(proyecto=proyecto, periodo=periodo).exists():
        raise Http404('No hay gastos reales cargados para ese mes/año')

    comp = gastos_real.construir_comparativo(proyecto, anio, {'periodo': periodo})
    kpi = comp['kpi']

    def _f(valor):
        return None if valor is None else float(valor)

    return {
        'periodo': f'{mes:02d}/{anio}',
        'proyecto': proyecto.nombre,
        'gasto_real_total': float(kpi['real']),
        'presupuesto_total': float(kpi['planeado']),
        'variacion_pesos': float(kpi['variacion']),
        'variacion_porcentaje': _f(kpi['variacion_pct']),
        'cumplimiento_porcentaje': _f(kpi['cumplimiento_pct']),
        'por_rubro': [
            {
                'rubro': f['nombre'],
                'rubro_presupuestal': f['rubro'],
                'gasto_real': float(f['total_real']),
                'presupuesto': _f(f['presupuesto']),
                'variacion_porcentaje': _f(f['variacion_pct']),
                'semaforo': f['semaforo'],
            }
            for f in comp['filas'] if not f['es_subtotal']
        ],
    }
