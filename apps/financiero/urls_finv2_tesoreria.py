"""Agregador de rutas de tesorería (S1 / #250, #251).

Las sub-features son dueñas de sus rutas concretas. Se tolera su ausencia mientras
se integran en paralelo, igual que el agregador de facturas de RUN B.
"""

from importlib import import_module

urlpatterns = []

for _module in (
    "urls_finv2_conciliacion",
    "urls_finv2_conciliacion_reportes",
    "urls_finv2_flujo_caja",
):
    try:
        urlpatterns += import_module(f"{__package__}.{_module}").urlpatterns
    except ModuleNotFoundError as error:
        if error.name != f"{__package__}.{_module}":
            raise
