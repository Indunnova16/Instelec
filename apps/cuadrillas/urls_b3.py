"""
B3 — URL patterns (espejo de views_b3.urlpatterns).

El aggregator `apps/cuadrillas/urls.py` ya hace
`urlpatterns += views_b3.urlpatterns` cuando importa views_b3. Este módulo
expone el mismo set para usos alternativos (tests, importación explícita en
testing isolation).
"""
from .views_b3 import urlpatterns  # noqa: F401

__all__ = ['urlpatterns']
