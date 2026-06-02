"""
Rutas financiero v2 (carga BD contable / mapeo cuenta→rubro) — B1 (#120).

Se incluye desde apps/financiero/urls.py via
``urlpatterns += urls_finv2.urlpatterns`` (mismo app_name='financiero').
NO declara app_name propio.
"""
from django.urls import path

from . import views_finv2_presupuesto as v2

urlpatterns = [
    path(
        'cargar-bd-contable/',
        v2.PresupuestoPlaneadoViewV2.as_view(),
        name='cargar_bd_contable',
    ),
    path(
        'editar-mapeo/',
        v2.MapeoCtaRubroCrudView.as_view(),
        name='editar_mapeo',
    ),
]
