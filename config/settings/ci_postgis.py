"""Settings para CI Fase 0 — PostGIS real (blindaje DEV-25).

instelec es una app GIS (django.contrib.gis + PostGIS): los tests necesitan
geometría real (srid) y funciones Postgres (regexp_replace) que el backend
sqlite de dev_lite no emula. CI corre contra un service container postgis.
Hereda base (postgis + DB_* desde env) y neutraliza Redis (LocMem) y hosts.
"""
from .base import *  # noqa: F401,F403

ALLOWED_HOSTS = ['*']
DEBUG = False

# Sin Redis en CI → cache en memoria.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
