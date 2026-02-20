"""
Campo URL patterns.
"""
from django.urls import path
from . import views

app_name = 'campo'

urlpatterns = [
    path('', views.RegistroListView.as_view(), name='lista'),
    path('registros/', views.RegistroListView.as_view(), name='registros'),
    path('crear/', views.RegistroCreateView.as_view(), name='crear'),
    path('<uuid:pk>/', views.RegistroDetailView.as_view(), name='detalle'),
    path('<uuid:pk>/evidencias/', views.EvidenciasView.as_view(), name='evidencias'),
    path('reportar-dano/', views.ReportarDanoCreateView.as_view(), name='reportar_dano'),
    path('reportes-dano/', views.ReportesDanoListView.as_view(), name='reportes_dano'),
    path('reportes-dano/<uuid:pk>/', views.ReporteDanoDetailView.as_view(), name='detalle_dano'),
]
