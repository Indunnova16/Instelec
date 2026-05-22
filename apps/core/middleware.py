"""Middleware RBAC (#44).

Filtra acceso por path-prefix según el rol del usuario:
- /construccion/* → requiere CONSTRUCCION
- /contratos/, /ambiental/, /indicadores/, /financiero/ → requiere MANTENIMIENTO
- Resto → solo LoginRequired (delegado a vistas)

Paths exentos (login, api pública, static, etc.) pasan sin chequear.
"""
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages

from .permissions import (
    MODULO_CONSTRUCCION,
    MODULO_MANTENIMIENTO,
    user_can_access_modulo,
)


EXEMPT_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/usuarios/login/',
    '/usuarios/logout/',
    '/usuarios/api/',
    '/api/',
    '/__debug__/',
    '/health',
    '/healthz',
    '/favicon.ico',
)

CONSTRUCCION_PREFIXES = ('/construccion/',)

MANTENIMIENTO_PREFIXES = (
    '/contratos/',
    '/ambiental/',
    '/indicadores/',
    '/financiero/',
    '/campo/',
)


class RBACModuloMiddleware:
    """Bloquea acceso por prefix-path según permisos RBAC del usuario."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return self.get_response(request)

        # Usuario no autenticado → dejar pasar (LoginRequired lo manejará)
        if not request.user.is_authenticated:
            return self.get_response(request)

        modulo_requerido = None
        if any(path.startswith(p) for p in CONSTRUCCION_PREFIXES):
            modulo_requerido = MODULO_CONSTRUCCION
        elif any(path.startswith(p) for p in MANTENIMIENTO_PREFIXES):
            modulo_requerido = MODULO_MANTENIMIENTO

        if modulo_requerido and not user_can_access_modulo(request.user, modulo_requerido):
            messages.error(
                request,
                f"Acceso denegado: su rol ({getattr(request.user, 'rol', 'sin rol')}) "
                f"no tiene permisos para el módulo {modulo_requerido}."
            )
            return redirect(reverse('core:home'))

        return self.get_response(request)
