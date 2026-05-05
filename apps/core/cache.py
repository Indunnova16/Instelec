"""
Caching utilities for frequently accessed data.
"""
from django.core.cache import cache
from django.db.models import QuerySet
from typing import List, Type, TypeVar

T = TypeVar('T')

CACHE_TIMEOUT = 3600  # 1 hour
CACHE_KEYS = {
    'lineas_activas': 'instelec:lineas:activas',
    'cuadrillas_activas': 'instelec:cuadrillas:activas',
    'tipos_actividad_activos': 'instelec:tipos_actividad:activos',
    'contratos_mantenimiento': 'instelec:contratos:mantenimiento',
    'contratos_construccion': 'instelec:contratos:construccion',
}


def get_cached_queryset(key: str, model_class: Type[T], query_kwargs: dict) -> List[T]:
    """
    Get queryset from cache or execute and cache it.

    Args:
        key: Cache key identifier
        model_class: Django model class
        query_kwargs: Keyword arguments for filter()

    Returns:
        List of model instances
    """
    cached = cache.get(key)
    if cached is not None:
        return cached

    result = list(model_class.objects.filter(**query_kwargs))
    cache.set(key, result, CACHE_TIMEOUT)
    return result


def get_lineas_activas():
    """Get all active lines (cached)."""
    from apps.lineas.models import Linea
    return get_cached_queryset(
        CACHE_KEYS['lineas_activas'],
        Linea,
        {'activa': True}
    )


def get_cuadrillas_activas():
    """Get all active crews (cached)."""
    from apps.cuadrillas.models import Cuadrilla
    return get_cached_queryset(
        CACHE_KEYS['cuadrillas_activas'],
        Cuadrilla,
        {'activa': True}
    )


def get_tipos_actividad_activos():
    """Get all active activity types (cached)."""
    from apps.actividades.models import TipoActividad
    return get_cached_queryset(
        CACHE_KEYS['tipos_actividad_activos'],
        TipoActividad,
        {'activo': True}
    )


def get_contratos_por_unidad(unidad_negocio: str):
    """Get contracts by business unit (cached)."""
    from apps.contratos.models import Contrato
    key = f'instelec:contratos:{unidad_negocio.lower()}'
    return get_cached_queryset(key, Contrato, {'unidad_negocio': unidad_negocio})


def invalidate_lineas_cache():
    """Invalidate lines cache."""
    cache.delete(CACHE_KEYS['lineas_activas'])


def invalidate_cuadrillas_cache():
    """Invalidate crews cache."""
    cache.delete(CACHE_KEYS['cuadrillas_activas'])


def invalidate_tipos_cache():
    """Invalidate activity types cache."""
    cache.delete(CACHE_KEYS['tipos_actividad_activos'])


def invalidate_contratos_cache():
    """Invalidate all contract caches."""
    cache.delete(CACHE_KEYS['contratos_mantenimiento'])
    cache.delete(CACHE_KEYS['contratos_construccion'])


def invalidate_all_cache():
    """Invalidate all application caches."""
    invalidate_lineas_cache()
    invalidate_cuadrillas_cache()
    invalidate_tipos_cache()
    invalidate_contratos_cache()
