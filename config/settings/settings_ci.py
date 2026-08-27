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

Override Instelec (2026-08-27, id:instelec-media-root-tests-bucle-infinito):
MEDIA_ROOT apunta a un tmpdir por corrida, NO al `media/` del repo. Sin esto los
uploads de la suite quedan como basura en `media/` (204 archivos acumulados) y la
suite pasa a depender del historial de la maquina. Peor: un test que mockea
`FileSystemStorage.exists -> False` (tests/unit/test_procedimientos_118.py, #118)
entra en BUCLE INFINITO si el archivo destino ya existe en disco — Django reintenta
`os.open(O_CREAT|O_EXCL)`, cacha FileExistsError, pide otro nombre a
`get_available_name()`, y esa funcion decide con `not exists(...)` -> con el mock
siempre dice "libre" y devuelve el MISMO nombre. `while True` girando a ~35MB/s:
medido 44GB de RSS y la maquina tumbada. Con MEDIA_ROOT aislado: 8s y 215MB.
"""
import os
import tempfile

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

# Uploads de la suite a un tmpdir aislado por corrida (ver docstring): evita
# ensuciar `media/` del repo y elimina el bucle infinito de #118.
MEDIA_ROOT = tempfile.mkdtemp(prefix='instelec_test_media_')

# Cache en memoria del proceso, NO el Redis real de base.py
# (id:instelec-settings-ci-redis-compartido). Con Redis, el cache de permisos
# RBAC (`apps/core/permissions._get_role_permisos`, TTL 1h) SOBREVIVE a la
# corrida: quedan 4900+ claves que la siguiente suite lee como si fueran suyas.
# Sintoma medido: `test_get_role_permisos_codigo_inexistente` fallaba leyendo un
# dict cacheado por una version ANTERIOR del codigo (con una clave
# `submodulos_por_modulo` que el codigo actual ya no produce) -> rojo que no
# depende del arbol de trabajo sino del historial de la maquina, e imposible de
# reproducir en limpio. Mismo criterio que `ci_postgis.py`.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
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
