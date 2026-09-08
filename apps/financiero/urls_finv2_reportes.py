from django.urls import path

from .views_finv2_reportes import (
    ClienteCrudView,
    ClienteFormView,
    MaestrosPagoView,
    ProveedorCrudView,
    ProveedorFormView,
    ReporteFacturacionView,
)

urlpatterns = [
    path("maestros/proveedores/", ProveedorCrudView.as_view(), name="proveedores_lista"),
    path("maestros/proveedores/nuevo/", ProveedorFormView.as_view(), name="proveedor_nuevo"),
    path("maestros/proveedores/<uuid:pk>/", ProveedorFormView.as_view(), name="proveedor_editar"),
    path("maestros/clientes/", ClienteCrudView.as_view(), name="clientes_lista"),
    path("maestros/clientes/nuevo/", ClienteFormView.as_view(), name="cliente_nuevo"),
    path("maestros/clientes/<uuid:pk>/", ClienteFormView.as_view(), name="cliente_editar"),
    path("maestros/pagos/", MaestrosPagoView.as_view(), name="maestros_pago"),
    path("reportes/facturacion/", ReporteFacturacionView.as_view(), name="reporte_facturacion"),
]
