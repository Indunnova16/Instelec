"""B3b - URL patterns para UX Montaje paridad Excel (#76).

Estos patterns se mergean con `urls.urlpatterns` (ver `apps/construccion/urls.py`
linea 226-229) - se appendean al final, asi que los nombres legacy
(`montaje_lista`, `montaje_pesos_update`, `montaje_torre_fase`) siguen
resolviendo a la vista legacy correspondiente. Los nuevos nombres son:

  - `montaje_detalle` -> MontajeDetalleView (GET, 7 secciones)
  - `montaje_detalle_save` -> MontajeDetalleSaveView (POST AJAX por seccion)
  - `montaje_avance_update_gone` -> MontajeAvanceUpdateGoneView (410 Gone)
"""
from django.urls import path

from . import views_b3_mont_detalle as v


urlpatterns = [
    # Detalle por torre (7 secciones)
    path(
        '<uuid:proyecto_id>/montaje/<uuid:torre_id>/detalle/',
        v.MontajeDetalleView.as_view(),
        name='montaje_detalle',
    ),

    # POST AJAX por seccion - <seccion> = general|recepcion|prearmado|montaje|
    #                                    controles|pesos|facturacion
    path(
        '<uuid:proyecto_id>/montaje/<uuid:torre_id>/detalle/<str:seccion>/save/',
        v.MontajeDetalleSaveView.as_view(),
        name='montaje_detalle_save',
    ),

    # Reemplazo del endpoint legacy `montaje_avance_update`. La edicion inline
    # de la matriz ya no se usa; se redirige al detalle. Devuelve 410 Gone.
    path(
        '<uuid:proyecto_id>/montaje/<uuid:torre_id>/avance-legacy/',
        v.MontajeAvanceUpdateGoneView.as_view(),
        name='montaje_avance_update_gone',
    ),
]
