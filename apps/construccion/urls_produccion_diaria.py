"""Agregador de rutas de Producción Diaria (#252).

Cada sub-feature declara sus rutas y vistas en un módulo propio. Los imports
protegidos permiten que la rama base sea importable antes de integrar B1--B3.
"""

urlpatterns = []

for _module_name in (
    "urls_produccion_diaria_registro",
    "urls_produccion_diaria_analisis",
    "urls_produccion_diaria_alertas",
):
    try:
        _module = __import__(f"{__package__}.{_module_name}", fromlist=["urlpatterns"])
        urlpatterns += _module.urlpatterns
    except ImportError:
        pass
