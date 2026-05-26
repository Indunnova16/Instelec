"""B1 — URLs para Actividades Finales.

Patrones registrados:
- /construccion/<uuid:proyecto_id>/actividades-finales/                          name=actividades_finales
- /construccion/<uuid:proyecto_id>/actividades-finales/<uuid:torre_id>/toggle/   name=actividades_finales_toggle
- /construccion/<uuid:proyecto_id>/actividades-finales/<uuid:torre_id>/obs/      name=actividades_finales_obs

Estos urlpatterns se concatenan al `urlpatterns` global de `urls.py` (con
`app_name='construccion'`), por eso van sin `app_name` aquí.
"""
from django.urls import path

from .views_b1_actividades_finales import (
    ActividadesFinalesMatrizView,
    ActividadFinalToggleView,
    ActividadFinalObservacionesView,
)


urlpatterns = [
    path(
        '<uuid:proyecto_id>/actividades-finales/',
        ActividadesFinalesMatrizView.as_view(),
        name='actividades_finales',
    ),
    path(
        '<uuid:proyecto_id>/actividades-finales/<uuid:torre_id>/toggle/',
        ActividadFinalToggleView.as_view(),
        name='actividades_finales_toggle',
    ),
    path(
        '<uuid:proyecto_id>/actividades-finales/<uuid:torre_id>/obs/',
        ActividadFinalObservacionesView.as_view(),
        name='actividades_finales_obs',
    ),
]
