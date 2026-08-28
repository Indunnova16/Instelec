"""Middleware RBAC (#44, extendido #186 A3).

Filtra acceso por path-prefix según el rol del usuario, en dos niveles:

1. **Granular** (`SUBMODULO_PREFIXES`, #186 A3): un path que cae bajo un
   prefijo mapeado a un submódulo se gatea por
   `user_can_access_submodulo()` -- y si el método es mutante (POST/PUT/
   PATCH/DELETE), además exige nivel `Ver y editar` (no alcanza `Ver`).
   Se evalúa PRIMERO y por orden de especificidad (el prefijo más largo /
   más específico va primero en la tupla) para que un sub-path como
   `/campo/procedimientos/` no caiga en la regla más genérica `/campo/`.
2. **Coarse** (`CONSTRUCCION_PREFIXES` / `MANTENIMIENTO_PREFIXES`, #44
   original): fallback a nivel de MÓDULO completo para las superficies que
   #186 A3 todavía no desglosó en hojas (Contratos, Ambiental, Indicadores,
   mapa de Cuadrillas -- quedan para una A3b).

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
    SUBMODULO_FIN_CHECKLIST_FACTURACION,
    SUBMODULO_FIN_COSTOS_CUADRILLA,
    SUBMODULO_FIN_DASHBOARD,
    SUBMODULO_FIN_NOMINA,
    SUBMODULO_FIN_PRESUPUESTO_PLANEADO,
    SUBMODULO_FIN_PRESUPUESTO_REAL,
    SUBMODULO_MANTENIMIENTO_ACTIVIDADES,
    SUBMODULO_MANTENIMIENTO_CAMPO,
    SUBMODULO_MANTENIMIENTO_LINEAS_TORRES,
    SUBMODULO_MANTENIMIENTO_PROCEDIMIENTOS,
    user_can_access_modulo,
    user_can_access_submodulo,
    user_nivel_acceso_submodulo,
)
from apps.core.models_roles import RoleModuloPermiso


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
    # Mantenimiento y que #186 A3 todavía NO desglosó por submódulo (queda
    # para A3b). Las que sí se desglosaron (actividades/lineas/campo/
    # financiero) se sacaron de acá -- las gatea SUBMODULO_PREFIXES abajo.
    '/contratos/',
    '/ambiental/',
    '/indicadores/',
    # `cuadrillas/` también aloja maestros de Configuración; sólo el mapa
    # operativo mostrado en el bloque Mantenimiento se clasifica acá.
    '/cuadrillas/mapa/',
)

MUTATING_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# #186 A3 -- mapa único de rutas → submódulo. ORDEN IMPORTA: el prefijo más
# específico va primero (ej. '/campo/procedimientos/' antes que '/campo/'),
# porque se usa el PRIMER match de un recorrido secuencial.
SUBMODULO_PREFIXES = (
    ('/campo/procedimientos/', SUBMODULO_MANTENIMIENTO_PROCEDIMIENTOS),
    ('/campo/', SUBMODULO_MANTENIMIENTO_CAMPO),
    ('/actividades/', SUBMODULO_MANTENIMIENTO_ACTIVIDADES),
    ('/lineas/', SUBMODULO_MANTENIMIENTO_LINEAS_TORRES),

    # Financiero (apps/financiero/, colgado de MANTENIMIENTO -- ver decisión
    # de diseño en rbac_seed_data.SUBMODULOS_FINANCIERO_APP). Reemplaza el
    # gate coarse anterior (exigía sólo MODULO_MANTENIMIENTO para todo el
    # prefix) por 6 hojas independientes -- decisión Miguel 2026-08-27.
    # Migración 0004 preserva el acceso legacy de los 6 roles admin que hoy
    # entran vía RoleRequiredMixin antes de que este gate exista.
    ('/financiero/nomina/', SUBMODULO_FIN_NOMINA),
    ('/financiero/checklist-facturacion/', SUBMODULO_FIN_CHECKLIST_FACTURACION),
    ('/financiero/facturacion/', SUBMODULO_FIN_CHECKLIST_FACTURACION),
    ('/financiero/costos-cuadrilla/', SUBMODULO_FIN_COSTOS_CUADRILLA),
    ('/financiero/cargar-costos-cuadrilla/', SUBMODULO_FIN_COSTOS_CUADRILLA),
    ('/financiero/cuadro-costos/', SUBMODULO_FIN_COSTOS_CUADRILLA),
    ('/financiero/presupuesto-real/', SUBMODULO_FIN_PRESUPUESTO_REAL),
    ('/financiero/presupuesto-planeado/', SUBMODULO_FIN_PRESUPUESTO_PLANEADO),
    ('/financiero/cargar-bd-contable/', SUBMODULO_FIN_PRESUPUESTO_PLANEADO),
    ('/financiero/editar-mapeo/', SUBMODULO_FIN_PRESUPUESTO_PLANEADO),
    ('/financiero/plantilla-excel/', SUBMODULO_FIN_PRESUPUESTO_PLANEADO),
    ('/financiero/exportar-excel/', SUBMODULO_FIN_DASHBOARD),
    ('/financiero/', SUBMODULO_FIN_DASHBOARD),
)


def _denegar(request, mensaje):
    messages.error(request, mensaje)
    # #186: un redirect() plano (302 + Location) NO es HTMX-aware. htmx sigue
    # ese 302 con un GET normal y swapea la respuesta completa (la página
    # home.html entera) como innerHTML del div chico que originó el hx-get --
    # si esa página contiene el mismo widget hx-trigger="load" que disparó la
    # request original (caso típico: "Mis Actividades de Hoy" en home.html
    # para roles sin acceso a Mantenimiento), el widget se re-dispara y el
    # ciclo se repite indefinidamente (recursión real, no solo un mal UX).
    # HX-Redirect fuerza a htmx a hacer una navegación TOP-LEVEL del browser
    # en vez de un swap anidado, rompiendo la recursión.
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse()
        response['HX-Redirect'] = reverse('core:home')
        return response
    return redirect(reverse('core:home'))


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

        # -- Nivel 1: granular por submódulo (#186 A3) --------------------
        for prefix, submodulo in SUBMODULO_PREFIXES:
            if not path.startswith(prefix):
                continue
            if not user_can_access_submodulo(request.user, submodulo):
                return _denegar(
                    request,
                    f"Acceso denegado: su rol ({getattr(request.user, 'rol', 'sin rol')}) "
                    f"no tiene permisos para {submodulo}."
                )
            if request.method in MUTATING_METHODS:
                nivel = user_nivel_acceso_submodulo(request.user, submodulo)
                if nivel != RoleModuloPermiso.VER_EDITAR:
                    return _denegar(
                        request,
                        f"Acceso denegado: su rol ({getattr(request.user, 'rol', 'sin rol')}) "
                        f"solo tiene acceso de consulta (Ver) a {submodulo}, no puede modificar."
                    )
            return self.get_response(request)

        # -- Nivel 2: coarse por módulo completo (#44 original, A3b pendiente) --
        modulo_requerido = None
        if any(path.startswith(p) for p in CONSTRUCCION_PREFIXES):
            modulo_requerido = MODULO_CONSTRUCCION
        elif any(path.startswith(p) for p in MANTENIMIENTO_PREFIXES):
            modulo_requerido = MODULO_MANTENIMIENTO

        if modulo_requerido and not user_can_access_modulo(request.user, modulo_requerido):
            return _denegar(
                request,
                f"Acceso denegado: su rol ({getattr(request.user, 'rol', 'sin rol')}) "
                f"no tiene permisos para el módulo {modulo_requerido}."
            )

        return self.get_response(request)
