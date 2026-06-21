from django.urls import path
from . import views

app_name = 'pagos'

urlpatterns = [
    path('', views.PagoPortalView.as_view(), name='portal'),
    path('historial/', views.HistorialPagosView.as_view(), name='historial'),
    path('facturacion/', views.DatosFacturacionView.as_view(), name='facturacion'),
    path('webhook/', views.WompiWebhookView.as_view(), name='webhook'),
]
