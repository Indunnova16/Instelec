"""B6 — re-export de urlpatterns.

`apps/campo/urls.py` (post-F2) hace ``from . import views_b6`` y agrega
``views_b6.urlpatterns``. Este módulo existe por conformidad con el BLUEPRINT
y como punto de entrada alternativo si en el futuro se quieren incluir las
rutas vía ``include('apps.campo.urls_b6')``.
"""

from .views_b6 import urlpatterns  # noqa: F401

__all__ = ['urlpatterns']
