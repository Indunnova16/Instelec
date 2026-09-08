"""
Rutas financiero v2 (carga BD contable / mapeo cuenta→rubro) — B1 (#120).

Se incluye desde apps/financiero/urls.py via
``urlpatterns += urls_finv2.urlpatterns`` (mismo app_name='financiero').
NO declara app_name propio.
"""

from django.urls import path

from . import views_finv2_presupuesto as v2
from . import urls_finv2_carga
from . import urls_finv2_facturas

urlpatterns = [
    path(
        "cargar-bd-contable/",
        v2.PresupuestoPlaneadoViewV2.as_view(),
        name="cargar_bd_contable",
    ),
    path(
        "editar-mapeo/",
        v2.MapeoCtaRubroCrudView.as_view(),
        name="editar_mapeo",
    ),
]

# B2 (#246, #247): workflow trazable de carga, homologación y plano CSV.
urlpatterns += urls_finv2_carga.urlpatterns
urlpatterns += urls_finv2_facturas.urlpatterns
