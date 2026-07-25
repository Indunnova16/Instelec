"""B2b (#74) — URLs paridad Obra Civil CANT OOCC (detalle por pata × sección).

Agrega:
  - `obra_civil_detalle`: GET vista detalle por torre (tabs patas × secciones).
  - `obra_civil_detalle_seccion`: POST AJAX por sección.

Endpoint legacy (`obra_civil_avance_update`) reemplazado:
  - Registra `OCAvanceLegacy410View` con el MISMO path original
    (`<proyecto_id>/obra-civil/torres/<torre_id>/avance/`). Como F2 ya
    incluye estos urlpatterns al final del archivo urls.py global, el path
    legacy queda registrado primero — la entrada de B2b queda como
    backup explícito y testable por reverse via name único
    `obra_civil_avance_legacy_410`. F4 puede remover el path legacy
    quirúrgicamente al integrar; este path nuestro toma el relevo
    devolviendo 410 Gone automáticamente.

NO toca el path original `obra_civil_lista` (queda con la vista legacy
`ObraCivilMatrizView` que ya sirve la matriz, ahora con el template
re-propositado como resumen read-only por B2b).
"""
from django.urls import path

from . import views_b3_oc_detalle as v


urlpatterns = [
    # NUEVOS — detalle por pata × sección
    path(
        '<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/detalle/',
        v.ObraCivilDetalleView.as_view(),
        name='obra_civil_detalle',
    ),
    path(
        '<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/detalle/<str:pata>/<str:seccion>/',
        v.ObraCivilDetalleSeccionView.as_view(),
        name='obra_civil_detalle_seccion',
    ),

    # #190 (reopen 2026-07-25, bounce=1) — pestaña "Torre": único lugar
    # editable de los 17 formatos técnicos únicos por torre. Persiste
    # siempre sobre la pata canónica 'A'; el signal de A1 propaga a B/C/D.
    path(
        '<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/torre/',
        v.ObraCivilTorreFormatosView.as_view(),
        name='obra_civil_torre_formatos',
    ),
    path(
        '<uuid:proyecto_id>/obra-civil/<uuid:torre_id>/torre/guardar/',
        v.ObraCivilTorreFormatosGuardarView.as_view(),
        name='obra_civil_torre_formatos_guardar',
    ),

    # RETIRO: misma path que la legacy `obra_civil_avance_update` —
    # se mantiene aquí para tests + futuro F4 que remueva la legacy.
    path(
        '<uuid:proyecto_id>/obra-civil/torres/<uuid:torre_id>/avance/',
        v.OCAvanceLegacy410View.as_view(),
        name='obra_civil_avance_legacy_410',
    ),
]
