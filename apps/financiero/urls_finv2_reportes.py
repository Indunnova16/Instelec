from django.urls import path

from .views_finv2_reportes import (
    ClienteCrudView,
    ClienteFormView,
    ImportarClientesView,
    ImportarProveedoresView,
    MaestrosPagoView,
    ProveedorCrudView,
    ProveedorFormView,
    ReporteFacturacionView,
    TerceroAuditoriaView,
)

urlpatterns = [
    path("maestros/proveedores/", ProveedorCrudView.as_view(), name="proveedores_lista"),
    path("maestros/proveedores/nuevo/", ProveedorFormView.as_view(), name="proveedor_nuevo"),
    path("maestros/proveedores/importar/", ImportarProveedoresView.as_view(), name="proveedor_importar"),
    path("maestros/proveedores/<uuid:pk>/", ProveedorFormView.as_view(), name="proveedor_editar"),
    path("maestros/proveedores/<uuid:pk>/auditoria/", TerceroAuditoriaView.as_view(), {"tipo": "PROVEEDOR"}, name="proveedor_auditoria"),
    path("maestros/clientes/", ClienteCrudView.as_view(), name="clientes_lista"),
    path("maestros/clientes/nuevo/", ClienteFormView.as_view(), name="cliente_nuevo"),
    path("maestros/clientes/importar/", ImportarClientesView.as_view(), name="cliente_importar"),
    path("maestros/clientes/<uuid:pk>/", ClienteFormView.as_view(), name="cliente_editar"),
    path("maestros/clientes/<uuid:pk>/auditoria/", TerceroAuditoriaView.as_view(), {"tipo": "CLIENTE"}, name="cliente_auditoria"),
    path("maestros/pagos/", MaestrosPagoView.as_view(), name="maestros_pago"),
    path("reportes/facturacion/", ReporteFacturacionView.as_view(), name="reporte_facturacion"),
]
