"""
Core views.
"""
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin


class HomeView(LoginRequiredMixin, TemplateView):
    """Home page / Dashboard."""
    template_name = 'core/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Add dashboard data based on user role
        if user.rol in ['admin', 'director', 'coordinador']:
            context['show_full_dashboard'] = True
        else:
            context['show_full_dashboard'] = False

        return context


def health_check(request):
    """
    Health check endpoint for Cloud Run.

    Returns status of:
    - Database connection
    - Cache connection (Redis)
    - Storage connection (GCS)
    """
    import os
    from django.db import connection
    from django.core.cache import cache

    checks = {
        'database': 'unknown',
        'cache': 'unknown',
        'storage': 'unknown',
    }
    healthy = True

    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        checks['database'] = 'healthy'
    except Exception as e:
        checks['database'] = f'unhealthy: {str(e)[:50]}'
        healthy = False

    # Check cache (Redis)
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            checks['cache'] = 'healthy'
        else:
            checks['cache'] = 'unhealthy: cache read failed'
            healthy = False
    except Exception as e:
        checks['cache'] = f'unhealthy: {str(e)[:50]}'
        # Cache failure is not critical
        checks['cache'] = 'unavailable'

    # Check storage (basic check for GCS config)
    from django.conf import settings
    if getattr(settings, 'GS_BUCKET_NAME', None):
        checks['storage'] = 'configured'
    else:
        checks['storage'] = 'local'

    # Build response
    response_data = {
        'status': 'healthy' if healthy else 'unhealthy',
        'service': 'transmaint',
        'version': os.environ.get('K_REVISION', 'local'),
        'checks': checks,
    }

    status_code = 200 if healthy else 503
    return JsonResponse(response_data, status=status_code)


def health_check_simple(request):
    """Simple health check for load balancer (fast)."""
    return JsonResponse({'status': 'ok'})
