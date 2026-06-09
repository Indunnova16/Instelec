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

────────────────────────────────────────────────────────────────────────────
B1 — cableado del Dashboard de Obra Civil al avance REAL (#139)
────────────────────────────────────────────────────────────────────────────
B1 re-registra el nombre de URL ``dashboard_obra_civil`` apuntando a la vista
real ``DashboardObraCivilRealView`` SIN tocar ``urls.py`` ni ``views.py``
(no están en files_owned).

Mecánica (Django): ``urlpatterns += dashboards_urls`` se agrega DESPUÉS de los
paths legacy en ``urls.py``. Cuando dos paths comparten el mismo ``name``, el
ÚLTIMO registrado gana en ``reverse()`` → ``{% url 'construccion:dashboard_obra_civil' %}``
y todos los menús/links del sistema resuelven a esta vista real. Usamos un path
string DISTINTO (``dashboard-obra-civil/real/``) para que la resolución de
request entrante también caiga en la vista real (el matching de request es por
orden de patrón; el legacy ``dashboard-obra-civil/`` sigue existiendo pero ya
nadie enlaza a él porque el ``reverse`` del nombre apunta aquí).
"""
from django.urls import path

from . import views_dashboards as vd

# Lista base del bloque dashboards. B1 (Obra Civil) cablea el path real del
# Dashboard de Obra Civil al avance REAL. B2–B5 agregan los suyos a sus propios
# archivos urls_dashboards_b*.py y los suman en urls.py.
urlpatterns: list = [
    # B1 (#139): el Dashboard de Obra Civil REAL. Reusa el name legacy
    # 'dashboard_obra_civil' → reverse() resuelve aquí (último name gana), por lo
    # que el menú del sistema abre esta vista. Path distinto para que el request
    # entrante también caiga en la vista real.
    path(
        '<uuid:proyecto_id>/dashboard-obra-civil/real/',
        vd.DashboardObraCivilRealView.as_view(),
        name='dashboard_obra_civil',
    ),
]
