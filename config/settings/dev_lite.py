"""
Lightweight local development settings.
Uses SQLite with GIS fields stored as TEXT. No GDAL/PostGIS/Redis needed.
"""
import sys
import types

# ── GIS Compatibility Layer ─────────────────────────────────────────────
# Mock the GDAL/GEOS native libraries so django.contrib.gis can load
# without actual GDAL installed. GIS fields will work as TEXT columns.

_has_gdal = False
try:
    from osgeo import gdal  # noqa: F401
    _has_gdal = True
except ImportError:
    pass

if not _has_gdal:

    class _FallbackModule(types.ModuleType):
        """Module that returns sensible defaults for any attribute access."""
        _shared = {}

        def __getattr__(self, name):
            # Let standard module dunder attrs raise normally
            if name.startswith('__') and name.endswith('__'):
                raise AttributeError(name)
            if name in self._shared:
                return self._shared[name]
            # Return a mock class for anything undefined
            return type(name, (Exception,), {}) if 'Exception' in name or 'Error' in name else _noop

    def _noop(*args, **kwargs):
        return None

    class _GDALException(Exception):
        pass

    class _GEOSException(Exception):
        pass

    class _MockGeometry:
        def __init__(self, *args, **kwargs):
            pass
        def __bool__(self):
            return False

    # Shared attributes across all gdal submodules
    _FallbackModule._shared = {
        'HAS_GDAL': False,
        'HAS_GEOS': False,
        'GDALException': _GDALException,
        'GEOSException': _GEOSException,
        'SpatialReference': _MockGeometry,
        'CoordTransform': _MockGeometry,
        'GDALRaster': None,
        'GDAL_VERSION': (3, 8, 5),
        'OGRGeomType': _MockGeometry,
        'GEOSGeometry': _MockGeometry,
        'Point': _MockGeometry,
        'Polygon': _MockGeometry,
        'MultiPoint': _MockGeometry,
        'MultiPolygon': _MockGeometry,
        'LineString': _MockGeometry,
        'MultiLineString': _MockGeometry,
        'GeometryCollection': _MockGeometry,
        'fromstr': _noop,
        'hex_regex': None,
        'wkt_regex': None,
    }

    # Mock all django.contrib.gis.gdal submodules
    _gdal_mods = [
        'django.contrib.gis.gdal',
        'django.contrib.gis.gdal.datasource',
        'django.contrib.gis.gdal.driver',
        'django.contrib.gis.gdal.envelope',
        'django.contrib.gis.gdal.error',
        'django.contrib.gis.gdal.feature',
        'django.contrib.gis.gdal.field',
        'django.contrib.gis.gdal.geometries',
        'django.contrib.gis.gdal.geomtype',
        'django.contrib.gis.gdal.layer',
        'django.contrib.gis.gdal.libgdal',
        'django.contrib.gis.gdal.prototypes',
        'django.contrib.gis.gdal.prototypes.ds',
        'django.contrib.gis.gdal.prototypes.errcheck',
        'django.contrib.gis.gdal.prototypes.generation',
        'django.contrib.gis.gdal.prototypes.geom',
        'django.contrib.gis.gdal.prototypes.raster',
        'django.contrib.gis.gdal.prototypes.srs',
        'django.contrib.gis.gdal.raster',
        'django.contrib.gis.gdal.raster.band',
        'django.contrib.gis.gdal.raster.base',
        'django.contrib.gis.gdal.raster.source',
        'django.contrib.gis.gdal.srs',
    ]
    for mod_name in _gdal_mods:
        sys.modules[mod_name] = _FallbackModule(mod_name)

    # Mock all django.contrib.gis.geos submodules
    _geos_mods = [
        'django.contrib.gis.geos',
        'django.contrib.gis.geos.geometry',
        'django.contrib.gis.geos.point',
        'django.contrib.gis.geos.polygon',
        'django.contrib.gis.geos.linestring',
        'django.contrib.gis.geos.collections',
        'django.contrib.gis.geos.error',
        'django.contrib.gis.geos.libgeos',
        'django.contrib.gis.geos.mutable_list',
        'django.contrib.gis.geos.prepared',
        'django.contrib.gis.geos.prototypes',
        'django.contrib.gis.geos.prototypes.coordseq',
        'django.contrib.gis.geos.prototypes.errcheck',
        'django.contrib.gis.geos.prototypes.geom',
        'django.contrib.gis.geos.prototypes.io',
        'django.contrib.gis.geos.prototypes.misc',
        'django.contrib.gis.geos.prototypes.predicates',
        'django.contrib.gis.geos.prototypes.prepared',
        'django.contrib.gis.geos.prototypes.threadsafe',
        'django.contrib.gis.geos.prototypes.topology',
        'django.contrib.gis.geos.coordseq',
        'django.contrib.gis.geos.io',
    ]
    for mod_name in _geos_mods:
        sys.modules[mod_name] = _FallbackModule(mod_name)

# ── Import base settings ────────────────────────────────────────────────
from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ['*']

# ── Database: Custom SQLite backend with GIS TEXT support ────────────────
# Check if SpatiaLite is actually available (GDAL alone is not enough)
_has_spatialite = False
if _has_gdal:
    try:
        import sqlite3
        conn = sqlite3.connect(':memory:')
        conn.enable_load_extension(True)
        for lib_name in ('mod_spatialite.so', 'mod_spatialite'):
            try:
                conn.load_extension(lib_name)
                _has_spatialite = True
                break
            except Exception:
                continue
        conn.close()
    except Exception:
        pass

if _has_spatialite:
    DATABASES = {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.spatialite',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'config.sqlite_gis_backend',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
    # Remove django.contrib.gis from INSTALLED_APPS
    INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'django.contrib.gis']

# ── Cache: In-memory (no Redis needed) ──────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# ── Sessions: Database-backed ───────────────────────────────────────────
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# ── Celery: Eager mode (tasks run synchronously, no worker needed) ──────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# ── CORS ────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# ── Debug toolbar ───────────────────────────────────────────────────────
try:
    import debug_toolbar  # noqa: F401
    INSTALLED_APPS += ['debug_toolbar', 'django_extensions']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
except ImportError:
    pass

INTERNAL_IPS = ['127.0.0.1', 'localhost']

# ── Email: Console backend ──────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ── Disable password validation in development ──────────────────────────
AUTH_PASSWORD_VALIDATORS = []

# ── Logging ─────────────────────────────────────────────────────────────
LOGGING['loggers']['apps']['level'] = 'DEBUG'
