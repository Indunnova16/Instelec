"""URLs de los Dashboards de fase (#139) — partición física de ``urls.py``.

Registrado en ``urls.py`` vía::

    from .urls_dashboards import urlpatterns as dashboards_urls
    urlpatterns += dashboards_urls

F2 (scaffolding) deja esta lista vacía + registrada. Las sub-features
B1–B5 escriben sus paths a archivos dedicados
(``urls_dashboards_b*.py``) e importan/extienden ``urlpatterns`` de allí
o lo agregan aquí, según ``files_owned``. NO duplicar el registro: el
``urlpatterns += dashboards_urls`` en ``urls.py`` es el único punto de enganche
del bloque de dashboards.
"""
from django.urls import path  # noqa: F401  (lo usan B1–B5)

# Lista base del bloque dashboards. B1 (Obra Civil) cablea los paths reales
# (dashboard-obra-civil/, datos-graficas/, chart/). B2–B5 agregan los suyos a
# sus propios archivos urls_dashboards_b*.py y los suman en urls.py.
urlpatterns: list = []
