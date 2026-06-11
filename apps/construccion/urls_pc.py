"""B1 — URLs de la subsección "Programación de Cuadrillas" (#155).

Estos `urlpatterns` se concatenan al `urlpatterns` global de
`apps/construccion/urls.py` (que ya define `app_name='construccion'` y, vía el
bloque importer del scaffolding S1, hace `urlpatterns += urls_pc.urlpatterns`).
Por eso van sin `app_name` aquí y los `name=` quedan bajo el namespace
`construccion:`.

Rutas del contrato del módulo (BLUEPRINT.contracts.urls):
- programacion-cuadrillas/                         construccion:programacion_cuadrillas_index   (B1)
- programacion-cuadrillas/crear/                   construccion:programacion_cuadrilla_crear      (B2)
- programacion-cuadrillas/<uuid:pk>/               construccion:programacion_cuadrilla_detalle    (B2)
- programacion-cuadrillas/<uuid:pk>/editar/        construccion:programacion_cuadrilla_editar     (B2)
- programacion-cuadrillas/<uuid:pk>/ejecucion/     construccion:programacion_cuadrilla_ejecucion_save  (B3, POST)
- programacion-cuadrillas/dashboard/               construccion:programacion_cuadrillas_dashboard (B4)

B1 registra SOLO el índice; B2/B3/B4 agregan sus rutas a ESTE mismo archivo
(el orquestador coordina el merge). Importar solo las vistas que ya existen
para no romper el import en la rama base.
"""
from django.urls import path

from apps.cuadrillas.views_pc_index import ProgramacionCuadrillaIndexView


urlpatterns = [
    # --- B1: entry point / índice ---
    path(
        'programacion-cuadrillas/',
        ProgramacionCuadrillaIndexView.as_view(),
        name='programacion_cuadrillas_index',
    ),
    # B2/B3/B4 agregan sus rutas aquí (crear/, <uuid:pk>/, editar/,
    # ejecucion/ POST, dashboard/). No importar sus vistas hasta que existan.
]
