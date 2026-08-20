"""Middleware RBAC (#44).

Filtra acceso por path-prefix según el rol del usuario:
- /construccion/* → requiere CONSTRUCCION
- Superficies operativas de Mantenimiento → requieren MANTENIMIENTO
- Resto → solo LoginRequired (delegado a vistas)

Paths exentos (login, api pública, static, etc.) pasan sin chequear.
"""
from django.conf import settings
from django.http import HttpResponse
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
    # Toda ruta web montada en config.urls que pertenece a la operación de
    # Mantenimiento. Mantener el inventario aquí evita que una pantalla nueva
    # quede protegida sólo por el sidebar y siga accesible por URL directa.
    '/actividades/',
    '/lineas/',
    # `cuadrillas/` también aloja maestros de Configuración; sólo el mapa
    # operativo mostrado en el bloque Mantenimiento se clasifica aquí.
    '/cuadrillas/mapa/',
    '/campo/',
    '/contratos/',
    '/ambiental/',
    '/indicadores/',
    '/financiero/',
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
            # #186: un redirect() plano (302 + Location) NO es HTMX-aware. htmx
            # sigue ese 302 con un GET normal y swapea la respuesta completa
            # (la página home.html entera) como innerHTML del div chico que
            # originó el hx-get -- si esa página contiene el mismo widget
            # hx-trigger="load" que disparó la request original (caso típico:
            # "Mis Actividades de Hoy" en home.html para roles sin acceso a
            # Mantenimiento), el widget se re-dispara y el ciclo se repite
            # indefinidamente (recursión real, no solo un mal UX).
            # HX-Redirect fuerza a htmx a hacer una navegación TOP-LEVEL del
            # browser en vez de un swap anidado, rompiendo la recursión.
            if request.headers.get('HX-Request') == 'true':
                response = HttpResponse()
                response['HX-Redirect'] = reverse('core:home')
                return response
            return redirect(reverse('core:home'))

        return self.get_response(request)
