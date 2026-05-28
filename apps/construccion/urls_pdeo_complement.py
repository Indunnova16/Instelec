"""URLs del complemento PDEO (#103).

URLs globales (sin proyecto_id) van bajo /construccion/financiero/:
  - lista de transacciones
  - upload PDEO Excel
  - reportes

URL por proyecto:
  - PyG drill-down
"""
from django.urls import path

from . import views_pdeo_complement as v

urlpatterns = [
    # Globales bajo /construccion/financiero/
    path('financiero/transacciones/',
         v.TransaccionesListView.as_view(), name='transacciones_list'),
    path('financiero/transacciones/upload/',
         v.TransaccionesUploadView.as_view(), name='transacciones_upload'),
    path('financiero/reportes/',
         v.ReportesFinancierosView.as_view(), name='reportes_financieros'),

    # Por proyecto
    path('<uuid:proyecto_id>/pyg/',
         v.PyGDrillDownView.as_view(), name='pyg_drilldown'),
]
