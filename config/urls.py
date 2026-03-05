"""
URL configuration for TransMaint project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API (Django Ninja)
    path('api/', include('apps.api.urls')),

    # Web views
    path('', include('apps.core.urls')),
    path('usuarios/', include('apps.usuarios.urls')),
    path('lineas/', include('apps.lineas.urls')),
    path('cuadrillas/', include('apps.cuadrillas.urls')),
    path('actividades/', include('apps.actividades.urls')),
    path('campo/', include('apps.campo.urls')),
    path('ambiental/', include('apps.ambiental.urls')),
    path('contratos/', include('apps.contratos.urls')),
    path('financiero/', include('apps.financiero.urls')),
    path('indicadores/', include('apps.indicadores.urls')),
]

# Debug toolbar (only in development)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

# Admin site configuration
admin.site.site_header = 'TransMaint - Administración'
admin.site.site_title = 'TransMaint Admin'
admin.site.index_title = 'Panel de Administración'
