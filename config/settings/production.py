"""
Django settings for production (Google Cloud Run).

Environment Variables Required:
- SECRET_KEY: Django secret key (from Secret Manager)
- DATABASE_URL: Database connection string (from Secret Manager)
- REDIS_URL: Redis connection string (from Secret Manager)
- GS_BUCKET_NAME: Google Cloud Storage bucket name
- GS_PROJECT_ID: Google Cloud project ID
- SENTRY_DSN: Sentry DSN for error tracking (optional)
"""
import os
from .base import *

DEBUG = False

# =============================================================================
# Security Settings
# =============================================================================
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
CSRF_TRUSTED_ORIGINS = [
    'https://*.run.app',
    'https://transmaint.instelec.com.co',
]

# =============================================================================
# Cloud Run Configuration
# =============================================================================
PORT = os.environ.get('PORT', '8080')

# Detect Cloud Run environment
IS_CLOUD_RUN = 'K_SERVICE' in os.environ
if IS_CLOUD_RUN:
    # Trust Cloud Run's load balancer
    USE_X_FORWARDED_HOST = True
    USE_X_FORWARDED_PORT = True

# =============================================================================
# Database - Cloud SQL
# =============================================================================
if os.environ.get('CLOUD_SQL_CONNECTION_NAME'):
    DATABASES['default']['HOST'] = f"/cloudsql/{os.environ['CLOUD_SQL_CONNECTION_NAME']}"

# Connection pooling for Cloud Run
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

# =============================================================================
# Google Cloud Storage
# =============================================================================
DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
GS_DEFAULT_ACL = 'publicRead'
GS_QUERYSTRING_AUTH = False
GS_FILE_OVERWRITE = False

# Static files served by WhiteNoise
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# =============================================================================
# Cache - Redis (Memorystore)
# =============================================================================
REDIS_URL = config('REDIS_URL', default='')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }
    # Session backend using Redis
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'

# =============================================================================
# Celery Configuration
# =============================================================================
if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

# =============================================================================
# CORS Configuration
# =============================================================================
CORS_ALLOWED_ORIGINS = [
    'https://transmaint.instelec.com.co',
]
CORS_ALLOW_CREDENTIALS = True

# =============================================================================
# Sentry Error Tracking
# =============================================================================
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=False,
        environment='production',
        release=os.environ.get('K_REVISION', 'unknown'),
    )

# =============================================================================
# Logging for Google Cloud Logging
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json' if IS_CLOUD_RUN else 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# =============================================================================
# Performance Settings
# =============================================================================
# Data upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Template caching
TEMPLATES[0]['OPTIONS']['loaders'] = [
    ('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    ]),
]
