"""Settings de test rápido para el gate F3 self-verify (/multiagente, /modulo).

SQLite en memoria + hashers rápidos: la suite corre en segundos en vez de
minutos (sin esto, el gate cae al settings de producción — Postgres vía
Cloud SQL — y la creación de la BD de test viaja por red; medido en el
portafolio: 668 migraciones = >30 min vs 28 s). Las migraciones SIGUEN
corriendo (no usar MIGRATION_MODULES=None: CI sin migraciones dejó
data-migrations sin cobertura — gotcha documentado tersaSoft/KOMSA/carnes).

Rollout portafolio 2026-08-08. Este módulo NUNCA se usa en runtime de prod.

Override Instelec (2026-08-20, id:instelec-tests-prefix-invisible-pytest-collection
y id:selfverify-gis-deps-red-ambiental): este repo es GeoDjango/PostGIS
(apps/construccion, apps/lineas usan gis_models.PointField). El SQLite plano del
template portafolio no soporta esos campos (`AttributeError: DatabaseOperations
object has no attribute geo_db_type`) y tumbaba el gate F3/F4 en CUALQUIER issue,
tocara o no esas apps (bloqueó #186, #223, #224 el mismo día). Fix: usar el
backend spatialite de Django (SQLite + extensión geoespacial cargable) en vez de
sqlite3 plano — sigue siendo en-memoria y rápido, pero soporta GIS. Requiere el
paquete de sistema `libsqlite3-mod-spatialite` instalado en el runner/VM
(Debian/Ubuntu: `apt-get install libsqlite3-mod-spatialite`).
"""
import os

os.environ.setdefault('SECRET_KEY', 'ci-only-secret-key-no-prod')
os.environ.setdefault('DJANGO_SECRET_KEY', 'ci-only-secret-key-no-prod')
os.environ.setdefault('DEBUG', 'False')
os.environ.setdefault('ALLOWED_HOSTS', '*')

from .base import *  # noqa: F401,F403,E402

DEBUG = False
ALLOWED_HOSTS = ['*']

# Debian/Ubuntu instalan el módulo en una ruta versionada que
# ctypes.util.find_library("spatialite") no resuelve solo.
SPATIALITE_LIBRARY_PATH = os.environ.get(
    'SPATIALITE_LIBRARY_PATH',
    '/usr/lib/x86_64-linux-gnu/mod_spatialite.so',
)

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.spatialite',
        'NAME': ':memory:',
    }
}

# Django >=4.2 usa STORAGES; en repos más viejos el dict extra es inofensivo.
try:
    del STATICFILES_STORAGE
except NameError:
    pass

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    # NIVEL WARNING, no CRITICAL: el NullHandler ya silencia la salida, pero el
    # nivel debe DEJAR PASAR los records o caplog/assertLogs no capturan nada y
    # un test legitimo que verifica logger.warning() falla en falso (claude-skills#456).
    'root': {'handlers': ['null'], 'level': 'WARNING'},
}
