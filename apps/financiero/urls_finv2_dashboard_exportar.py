"""Rutas de descarga del dashboard financiero integrado (#246 Sprint D).

Cuelgan del mismo prefijo `carga-financiera/` que el dashboard
(`urls_finv2_carga.py`) a propósito: `RBACModuloMiddleware` gatea por
prefix-path (`SUBMODULO_PREFIXES`, `apps/core/middleware.py`) y
`/financiero/carga-financiera/` ya está mapeado a `SUBMODULO_FIN_HOMOLOGACION`
-- que estas rutas hereden el mismo prefijo evita tener que tocar la tabla
del middleware (fuera de `FILES_OWNED` de esta sub-feature) para que el
nivel 1 (granular) las reconozca.
"""

from django.urls import path

from . import views_finv2_dashboard_exportar as v

urlpatterns = [
    path(
        "carga-financiera/exportar/pdf/",
        v.DashboardExportarPdfView.as_view(),
        name="dashboard_exportar_pdf",
    ),
    path(
        "carga-financiera/exportar/excel/",
        v.DashboardExportarExcelView.as_view(),
        name="dashboard_exportar_excel",
    ),
    path(
        "carga-financiera/exportar/ppt/",
        v.DashboardExportarPptView.as_view(),
        name="dashboard_exportar_ppt",
    ),
]
