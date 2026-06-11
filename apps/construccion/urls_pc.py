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
from apps.cuadrillas.views_pc_programacion import (
    ProgramacionCuadrillaCreateView,
    ProgramacionCuadrillaDetailView,
    ProgramacionCuadrillaUpdateView,
)
from apps.cuadrillas.views_pc_ejecucion import EjecucionSemanalUpdateView
from apps.cuadrillas.views_pc_dashboard import ProgramacionCuadrillaDashboardView


urlpatterns = [
    # --- B1: entry point / índice ---
    path(
        'programacion-cuadrillas/',
        ProgramacionCuadrillaIndexView.as_view(),
        name='programacion_cuadrillas_index',
    ),
    # --- B4: dashboard (path estático ANTES del <uuid:pk> para no ser capturado) ---
    path(
        'programacion-cuadrillas/dashboard/',
        ProgramacionCuadrillaDashboardView.as_view(),
        name='programacion_cuadrillas_dashboard',
    ),
    # --- B2: crear (path estático ANTES del <uuid:pk>) ---
    path(
        'programacion-cuadrillas/crear/',
        ProgramacionCuadrillaCreateView.as_view(),
        name='programacion_cuadrilla_crear',
    ),
    # --- B2: detalle ---
    path(
        'programacion-cuadrillas/<uuid:pk>/',
        ProgramacionCuadrillaDetailView.as_view(),
        name='programacion_cuadrilla_detalle',
    ),
    # --- B2: editar ---
    path(
        'programacion-cuadrillas/<uuid:pk>/editar/',
        ProgramacionCuadrillaUpdateView.as_view(),
        name='programacion_cuadrilla_editar',
    ),
    # --- B3: ejecución (POST AJAX inline-save) ---
    path(
        'programacion-cuadrillas/<uuid:pk>/ejecucion/',
        EjecucionSemanalUpdateView.as_view(),
        name='programacion_cuadrilla_ejecucion_save',
    ),
]
