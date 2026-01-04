"""
Django settings for local development.
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# CORS - Allow all in development
CORS_ALLOW_ALL_ORIGINS = True

# Debug toolbar
INSTALLED_APPS += ['debug_toolbar', 'django_extensions']
MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
INTERNAL_IPS = ['127.0.0.1', 'localhost']

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable password validation in development
AUTH_PASSWORD_VALIDATORS = []

# Logging
LOGGING['loggers']['apps']['level'] = 'DEBUG'
LOGGING['loggers']['django.db.backends'] = {
    'handlers': ['console'],
    'level': 'DEBUG' if config('SQL_DEBUG', default=False, cast=bool) else 'INFO',
}

# Try to use Redis, fallback to database sessions if unavailable
import redis

try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.ping()
    # Redis available, use cache sessions (already configured in base.py)
except (redis.ConnectionError, redis.exceptions.ConnectionError):
    # Redis not available, use database sessions
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }
