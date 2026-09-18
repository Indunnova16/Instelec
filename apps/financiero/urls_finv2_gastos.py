from django.urls import path

from .views_finv2_gastos import (
    GastoCargaCsvView,
    GastoCargasHistorialView,
    GastoCreateView,
    GastoDetailView,
    GastoImportarPreviewView,
    GastoImportarView,
    GastosListView,
)

urlpatterns = [
    path("facturas-gastos/", GastosListView.as_view(), name="facturas_gastos_lista"),
    path("facturas-gastos/nueva/", GastoCreateView.as_view(), name="factura_gasto_nueva"),
    path("facturas-gastos/importar/", GastoImportarView.as_view(), name="factura_gasto_importar"),
    path(
        "facturas-gastos/importar/preview/",
        GastoImportarPreviewView.as_view(),
        name="factura_gasto_importar_preview",
    ),
    path(
        "facturas-gastos/cargas/", GastoCargasHistorialView.as_view(), name="factura_gasto_cargas"
    ),
    path(
        "facturas-gastos/cargas/<uuid:pk>/csv/",
        GastoCargaCsvView.as_view(),
        name="factura_gasto_carga_csv",
    ),
    path("facturas-gastos/<uuid:pk>/", GastoDetailView.as_view(), name="factura_gasto_detalle"),
]
