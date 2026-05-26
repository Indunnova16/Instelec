"""
B2.1 — Re-export thin de urlpatterns que viven en views_b21.py.

El aggregator `apps/lineas/urls.py` ya hace `from . import views_b21` y suma
`views_b21.urlpatterns`. Este módulo existe para que tooling/grep encuentre el
mapeo "B2.1 → urls" en su lugar natural y para que un futuro split pueda mover
los path() acá sin tocar el aggregator.
"""
from .views_b21 import urlpatterns  # noqa: F401

__all__ = ['urlpatterns']
