from django.urls import path

from .views_finv2_ingresos import (
    IngresoCreateView,
    IngresoDetailView,
    IngresoListView,
    IngresoPdfView,
)

urlpatterns = [
    path("facturas-ingresos/", IngresoListView.as_view(), name="facturas_ingresos"),
    path("facturas-ingresos/nueva/", IngresoCreateView.as_view(), name="factura_ingreso_nueva"),
    path(
        "facturas-ingresos/<uuid:pk>/", IngresoDetailView.as_view(), name="factura_ingreso_detalle"
    ),
    path("facturas-ingresos/<uuid:pk>/pdf/", IngresoPdfView.as_view(), name="factura_ingreso_pdf"),
]
