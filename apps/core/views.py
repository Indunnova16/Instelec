"""
Core views.
"""
import logging
from typing import Any

from django.views.generic import TemplateView
from django.http import HttpRequest, JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin

logger = logging.getLogger(__name__)


class HomeView(LoginRequiredMixin, TemplateView):
    """Home page / Dashboard."""
    template_name = 'core/home.html'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Add dashboard data based on user role
        if user.rol in ['admin', 'director', 'coordinador']:
            context['show_full_dashboard'] = True
        else:
            context['show_full_dashboard'] = False

        return context


def health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for Cloud Run.

    Returns status of:
    - Database connection (with timeout)
    - Cache connection (Redis) - critical for Celery
    - Storage connection (GCS) - actual access verification

    All checks have a 5-second timeout to prevent blocking.
    """
    import os
    import signal
    from django.db import connection, OperationalError
    from django.core.cache import cache
    from django.conf import settings

    TIMEOUT_SECONDS = 5

    class HealthCheckTimeoutError(Exception):
        pass

    def timeout_handler(signum: int, frame: Any) -> None:
        raise HealthCheckTimeoutError("Operation timed out")

    checks: dict[str, str] = {
        'database': 'unknown',
        'cache': 'unknown',
        'storage': 'unknown',
    }
    healthy = True

    # Check database with timeout
    try:
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            checks['database'] = 'healthy'
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except HealthCheckTimeoutError:
        logger.error(f"Database health check timed out after {TIMEOUT_SECONDS}s")
        checks['database'] = f'unhealthy: timeout after {TIMEOUT_SECONDS}s'
        healthy = False
    except (OperationalError, Exception) as e:
        logger.error(f"Database health check failed: {e}")
        checks['database'] = f'unhealthy: {str(e)[:50]}'
        healthy = False

    # Check cache (Redis) with timeout - CRITICAL for Celery
    try:
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
        try:
            cache.set('health_check', 'ok', 10)
            if cache.get('health_check') == 'ok':
                checks['cache'] = 'healthy'
            else:
                checks['cache'] = 'unhealthy: cache read failed'
                healthy = False
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except HealthCheckTimeoutError:
        logger.error(f"Cache health check timed out after {TIMEOUT_SECONDS}s")
        checks['cache'] = f'unhealthy: timeout after {TIMEOUT_SECONDS}s'
        healthy = False  # Redis is critical for Celery
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        checks['cache'] = f'unhealthy: {str(e)[:50]}'
        healthy = False  # Redis is critical for Celery

    # Check storage - verify actual access, not just configuration
    bucket_name = getattr(settings, 'GS_BUCKET_NAME', None)
    if bucket_name:
        try:
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(TIMEOUT_SECONDS)
            try:
                from google.cloud import storage as gcs_storage
                client = gcs_storage.Client()
                bucket = client.bucket(bucket_name)
                # Verify bucket exists and is accessible
                bucket.reload()
                checks['storage'] = 'healthy'
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except HealthCheckTimeoutError:
            logger.error(f"Storage health check timed out after {TIMEOUT_SECONDS}s")
            checks['storage'] = f'unhealthy: timeout after {TIMEOUT_SECONDS}s'
            healthy = False
        except ImportError:
            logger.error("google-cloud-storage package not installed")
            checks['storage'] = 'unhealthy: google-cloud-storage not installed'
            healthy = False
        except Exception as e:
            logger.error(f"Storage health check failed: {e}")
            checks['storage'] = f'unhealthy: {str(e)[:50]}'
            healthy = False
    else:
        checks['storage'] = 'local'

    # Build response
    response_data: dict[str, Any] = {
        'status': 'healthy' if healthy else 'unhealthy',
        'service': 'transmaint',
        'version': os.environ.get('K_REVISION', 'local'),
        'checks': checks,
    }

    status_code = 200 if healthy else 503
    return JsonResponse(response_data, status=status_code)


def health_check_simple(request: HttpRequest) -> JsonResponse:
    """Simple health check for load balancer (fast)."""
    return JsonResponse({'status': 'ok'})
