"""Agregador aislado de rutas de Programación Semanal de Construcción (#225)."""

urlpatterns = []

# Cada sub-feature aporta sus rutas en un archivo propio. Los imports protegidos
# mantienen la branch base importable mientras dichas ramas aún no se integran.
for _module_name in (
    'urls_psc_aprobaciones',
    'urls_psc_programacion',
    'urls_psc_personal',
    'urls_psc_excel',
    'urls_psc_lifecycle',
):
    try:
        _module = __import__(f'{__package__}.{_module_name}', fromlist=['urlpatterns'])
        urlpatterns += _module.urlpatterns
    except ImportError:
        pass
