"""Agregador de rutas de facturas v2 (S1 / #248, #249).

Cada módulo B es dueño de sus vistas y rutas concretas. El agregador tolera
su ausencia temporal para que la rama de scaffolding siga siendo importable;
al integrar B1/B2/B3 los contratos se publican automáticamente.
"""
from importlib import import_module


urlpatterns = []

for _module in ('urls_finv2_gastos', 'urls_finv2_ingresos', 'urls_finv2_reportes'):
    try:
        urlpatterns += import_module(f'{__package__}.{_module}').urlpatterns
    except ModuleNotFoundError as error:
        if error.name != f'{__package__}.{_module}':
            raise
