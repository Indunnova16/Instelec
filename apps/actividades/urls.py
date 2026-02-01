"""
Actividades URL patterns.
"""
from django.urls import path
from . import views

app_name = 'actividades'

urlpatterns = [
    path('', views.ActividadListView.as_view(), name='lista'),
    path('crear/', views.ActividadCreateView.as_view(), name='crear'),
    path('calendario/', views.CalendarioView.as_view(), name='calendario'),
    path('api/eventos/', views.EventosAPIView.as_view(), name='api_eventos'),
    path('<uuid:pk>/', views.ActividadDetailView.as_view(), name='detalle'),
    path('<uuid:pk>/partial/', views.ActividadDetailPartialView.as_view(), name='detalle_partial'),
    path('<uuid:pk>/detalle-modal/', views.ActividadDetalleModalView.as_view(), name='detalle_modal'),
    path('<uuid:pk>/editar/', views.ActividadEditView.as_view(), name='editar'),
    path('<uuid:pk>/cambiar-estado/', views.CambiarEstadoView.as_view(), name='cambiar_estado'),
    path('programacion/', views.ProgramacionListView.as_view(), name='programacion'),
    path('programacion/importar/', views.ImportarProgramacionView.as_view(), name='importar'),
    path('programacion/exportar/', views.ExportarProgramacionView.as_view(), name='exportar_programacion'),
    path('reportes/avance/', views.ExportarAvanceView.as_view(), name='exportar_avance'),
]
