"""
User URL patterns.
"""
from django.urls import path
from . import views

app_name = 'usuarios'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('perfil/', views.PerfilView.as_view(), name='perfil'),
    path('perfil/editar/', views.PerfilEditView.as_view(), name='perfil_edit'),
    path('gestion/', views.GestionUsuariosView.as_view(), name='gestion'),
    path('gestion/crear/', views.CrearUsuarioAdminView.as_view(), name='crear_admin'),
    path('gestion/reset-password/', views.ResetPasswordView.as_view(), name='reset_password'),
    path('campo/upload/', views.CargaMasivaUsuariosCampoView.as_view(), name='campo_upload'),
]
