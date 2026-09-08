from django.urls import path

from .views_finv2_gastos import GastoCreateView, GastoDetailView, GastosListView

urlpatterns = [
    path("facturas-gastos/", GastosListView.as_view(), name="facturas_gastos_lista"),
    path("facturas-gastos/nueva/", GastoCreateView.as_view(), name="factura_gasto_nueva"),
    path("facturas-gastos/<uuid:pk>/", GastoDetailView.as_view(), name="factura_gasto_detalle"),
]
