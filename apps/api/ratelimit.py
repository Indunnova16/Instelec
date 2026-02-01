"""
Rate limiting decorators for Django Ninja API.

This module provides rate limiting functionality compatible with Django Ninja,
using Redis as the backend for distributed rate limiting.

Usage:
    from apps.api.ratelimit import ratelimit_login, ratelimit_api, ratelimit_upload

    @router.post('/login', auth=None)
    @ratelimit_login
    def login(request, data: LoginIn):
        ...

    @router.get('/items')
    @ratelimit_api
    def list_items(request):
        ...

    @router.post('/upload')
    @ratelimit_upload
    def upload_file(request, file: UploadedFile):
        ...
"""
import functools
import hashlib
import logging
import time
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

logger = logging.getLogger(__name__)


# Rate limit configuration defaults
RATELIMIT_CONFIG: dict[str, dict[str, str]] = getattr(settings, 'RATELIMIT_CONFIG', {
    'login': {
        'rate': '5/m',  # 5 requests per minute
        'key': 'ip',
    },
    'api': {
        'rate': '100/m',  # 100 requests per minute
        'key': 'user',
    },
    'upload': {
        'rate': '20/m',  # 20 requests per minute
        'key': 'user',
    },
})


def parse_rate(rate_string: str) -> tuple[int, int]:
    """
    Parse rate limit string into (count, period_seconds).

    Args:
        rate_string: Rate in format "count/period" where period is:
            s = seconds, m = minutes, h = hours, d = days

    Returns:
        Tuple of (max_requests, period_in_seconds)

    Examples:
        "5/m" -> (5, 60)
        "100/h" -> (100, 3600)
        "1000/d" -> (1000, 86400)
    """
    count_str, period = rate_string.split('/')
    count = int(count_str)

    period_map: dict[str, int] = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
    }

    # Handle full words or abbreviations
    period_lower = period.lower()
    if period_lower.startswith('min'):
        seconds = 60
    elif period_lower.startswith('hour'):
        seconds = 3600
    elif period_lower.startswith('day'):
        seconds = 86400
    elif period_lower.startswith('sec'):
        seconds = 1
    else:
        seconds = period_map.get(period_lower[0], 60)

    return count, seconds


def get_client_ip(request: HttpRequest) -> str:
    """
    Get the client's IP address from the request.
    Handles X-Forwarded-For header for reverse proxies.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP in the chain (original client)
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip


def get_rate_limit_key(request: HttpRequest, key_type: str, group: str) -> str:
    """
    Generate a unique cache key for rate limiting.

    Args:
        request: The HTTP request
        key_type: 'ip' or 'user'
        group: The rate limit group name (e.g., 'login', 'api', 'upload')

    Returns:
        A unique cache key string
    """
    if key_type == 'ip':
        identifier = get_client_ip(request)
    elif key_type == 'user':
        # For authenticated endpoints, use user ID if available
        user = getattr(request, 'auth', None)
        if user and hasattr(user, 'id'):
            identifier = str(user.id)
        else:
            # Fallback to IP for unauthenticated requests
            identifier = get_client_ip(request)
    else:
        identifier = get_client_ip(request)

    # Create a hash for the key to ensure it's a valid cache key
    # MD5 is used only for key generation, not security purposes
    key_data = f"ratelimit:{group}:{identifier}"
    return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()


def check_rate_limit(request: HttpRequest, group: str) -> tuple[bool, dict[str, Any]]:
    """
    Check if the request exceeds the rate limit.

    Args:
        request: The HTTP request
        group: The rate limit group name

    Returns:
        Tuple of (is_allowed, info_dict)
        info_dict contains: limit, remaining, reset_time
    """
    config = RATELIMIT_CONFIG.get(group, RATELIMIT_CONFIG['api'])
    max_requests, period = parse_rate(config['rate'])
    key_type = config.get('key', 'user')

    cache_key = get_rate_limit_key(request, key_type, group)

    # Get current window data
    now = time.time()
    window_start = int(now // period) * period
    window_key = f"{cache_key}:{int(window_start)}"

    try:
        # Get current count
        current_count = cache.get(window_key, 0)

        # Calculate remaining time in window
        reset_time = int(window_start + period)
        remaining = max(0, max_requests - current_count - 1)

        info: dict[str, Any] = {
            'limit': max_requests,
            'remaining': remaining,
            'reset': reset_time,
            'period': period,
        }

        if current_count >= max_requests:
            logger.warning(
                f"Rate limit exceeded for {group}: key={cache_key}, "
                f"count={current_count}, limit={max_requests}"
            )
            return False, info

        # Increment counter with TTL
        cache.set(window_key, current_count + 1, timeout=period + 1)

        return True, info

    except Exception as e:
        # If cache fails, allow the request but log the error
        logger.error(f"Rate limit check failed: {e}")
        return True, {'limit': max_requests, 'remaining': max_requests, 'reset': 0, 'period': period}


def ratelimit(group: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Rate limiting decorator for Django Ninja endpoints.

    Args:
        group: The rate limit group name ('login', 'api', 'upload')

    Returns:
        Decorated function that checks rate limits
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            is_allowed, info = check_rate_limit(request, group)

            # Add rate limit headers to response
            def add_headers(response: HttpResponse) -> HttpResponse:
                response['X-RateLimit-Limit'] = str(info['limit'])
                response['X-RateLimit-Remaining'] = str(info['remaining'])
                response['X-RateLimit-Reset'] = str(info['reset'])
                return response

            if not is_allowed:
                response = JsonResponse(
                    {
                        'detail': 'Demasiadas solicitudes. Por favor, intente de nuevo mas tarde.',
                        'retry_after': info['period'],
                    },
                    status=429
                )
                response['Retry-After'] = str(info['period'])
                return add_headers(response)

            # Call the original function
            result = func(request, *args, **kwargs)

            # If result is a Response object, add headers
            if hasattr(result, '__setitem__'):
                add_headers(result)

            return result

        return wrapper
    return decorator


# Pre-configured decorators for common use cases

def ratelimit_login(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Rate limit decorator for login endpoints.
    Default: 5 requests per minute per IP.
    """
    return ratelimit('login')(func)


def ratelimit_api(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Rate limit decorator for general API endpoints.
    Default: 100 requests per minute per user.
    """
    return ratelimit('api')(func)


def ratelimit_upload(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Rate limit decorator for upload endpoints.
    Default: 20 requests per minute per user.
    """
    return ratelimit('upload')(func)


class RateLimitMiddleware:
    """
    Middleware for global rate limiting.

    This middleware can be used to apply a global rate limit to all API requests.
    It's more efficient than per-endpoint decorators for global limits.

    Add to MIDDLEWARE in settings.py:
        'apps.api.ratelimit.RateLimitMiddleware',
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.enabled: bool = getattr(settings, 'RATELIMIT_ENABLE', True)
        self.api_prefix: str = getattr(settings, 'RATELIMIT_API_PREFIX', '/api/')

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Only apply to API endpoints
        if self.enabled and request.path.startswith(self.api_prefix):
            # Skip rate limiting for certain paths
            skip_paths: list[str] = getattr(settings, 'RATELIMIT_SKIP_PATHS', ['/api/health'])
            if any(request.path.startswith(path) for path in skip_paths):
                return self.get_response(request)

            is_allowed, info = check_rate_limit(request, 'api')

            if not is_allowed:
                response = JsonResponse(
                    {
                        'detail': 'Demasiadas solicitudes. Por favor, intente de nuevo mas tarde.',
                        'retry_after': info['period'],
                    },
                    status=429
                )
                response['Retry-After'] = str(info['period'])
                response['X-RateLimit-Limit'] = str(info['limit'])
                response['X-RateLimit-Remaining'] = str(info['remaining'])
                response['X-RateLimit-Reset'] = str(info['reset'])
                return response

        response = self.get_response(request)
        return response
