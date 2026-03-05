"""
Contratos URL patterns.
"""
from django.urls import path
from . import views

app_name = 'contratos'

urlpatterns = [
    path('', views.ContratoListView.as_view(), name='lista'),
    path('crear/', views.ContratoCreateView.as_view(), name='crear'),
    path('<uuid:pk>/editar/', views.ContratoUpdateView.as_view(), name='editar'),
    path('<uuid:pk>/eliminar/', views.ContratoDeleteView.as_view(), name='eliminar'),
]
