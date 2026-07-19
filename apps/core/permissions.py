"""RBAC permissions (#44) — BD-backed desde issue #186.

Matriz rol → módulos/nivel/sub-módulos, leída desde `Role`/
`RoleModuloPermiso` (BD) en vez de los dicts hardcodeados `ROL_MODULOS`/
`ROL_NIVEL`/`ROL_SUBMODULOS` que vivían acá (ELIMINADOS en A3 — snapshot
congelado verbatim para el Gate de Paridad en `apps/core/rbac_seed_data.py`
+ `tests/unit/test_issue_186_paridad_rbac.py`, que compara este archivo
contra ese snapshot exhaustivamente).

Cacheado por `Role.codigo` (NO por sesión/usuario — catálogo pequeño,
14-20 filas, compartido por TODOS los usuarios de ese rol; cachear por
sesión multiplicaría el tamaño y quedaría stale ante una edición en la
matriz, ver PLAN §4) usando el cache framework de Django (Redis, ya
configurado en `config/settings/base.py`). Invalidación EXPLÍCITA por
señal `post_save`/`post_delete` sobre `Role`/`RoleModuloPermiso`
(`apps/core/models_roles.py`) — no depende solo del TTL de 1h, así una
edición en la matriz (A5) tiene efecto inmediato en el próximo request.

`RBACModuloMiddleware` (`apps/core/middleware.py`) corre en CADA request de
la aplicación — de ahí la importancia del caching (sin él, cada request
dispararía una query a `RoleModuloPermiso`).
"""
from django.core.cache import cache

MODULO_MANTENIMIENTO = 'MANTENIMIENTO'
MODULO_CONSTRUCCION = 'CONSTRUCCION'
MODULO_CONFIG = 'CONFIG'  # gestión de usuarios, parametrización, sistema

NIVEL_ADMIN = 'admin'
NIVEL_OPERARIO = 'operario'

# Debe coincidir con RoleModuloPermiso.SIN_ACCESO (apps/core/models_roles.py).
# Literal (no import) para evitar un ciclo de import a nivel de módulo entre
# permissions.py y models_roles.py -- _get_role_permisos() abajo sí importa
# Role, pero de forma diferida (dentro de la función, no al tope del módulo).
_SIN_ACCESO = 'sin_acceso'

CACHE_TTL_ROLE_PERMISOS = 3600  # 1h -- con invalidación explícita por señal, ver arriba
CACHE_KEY_ROLE_PERMISOS = 'instelec:rbac:role:{codigo}'


def _cache_key_role(codigo):
    return CACHE_KEY_ROLE_PERMISOS.format(codigo=codigo)


def _get_role_permisos(codigo):
    """dict `{'modulos': set, 'submodulos': set, 'nivel': str|None}` para un
    código de rol -- cacheado por `codigo`, ver docstring del módulo.

    Rol inexistente/inactivo o `codigo` vacío → dict "vacío" (sin acceso a
    nada), consistente con el comportamiento legacy de `dict.get(rol, set())`.
    """
    if not codigo:
        return {'modulos': set(), 'submodulos': set(), 'nivel': None}

    key = _cache_key_role(codigo)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from .models_roles import Role  # import diferido -- evita ciclo con models.py

    try:
        role = Role.objects.prefetch_related('permisos').get(codigo=codigo, activo=True)
    except Role.DoesNotExist:
        result = {'modulos': set(), 'submodulos': set(), 'nivel': None}
        cache.set(key, result, CACHE_TTL_ROLE_PERMISOS)
        return result

    permisos_con_acceso = [p for p in role.permisos.all() if p.nivel_acceso != _SIN_ACCESO]
    result = {
        'modulos': {p.modulo for p in permisos_con_acceso if not p.submodulo},
        'submodulos': {p.submodulo for p in permisos_con_acceso if p.submodulo},
        'nivel': role.nivel,
    }
    cache.set(key, result, CACHE_TTL_ROLE_PERMISOS)
    return result


def invalidate_role_cache(codigo):
    """Invalida el cache de permisos de un rol. Llamado por las señales
    `post_save`/`post_delete` de `Role`/`RoleModuloPermiso`
    (`apps/core/models_roles.py`) tras editar la matriz (A5) -- así el
    efecto es inmediato, no espera el TTL de 1h."""
    if codigo:
        cache.delete(_cache_key_role(codigo))


def user_rol(user):
    return getattr(user, 'rol', '') or ''


def user_modulos(user):
    """Conjunto de módulos accesibles para el usuario. Superuser = todos."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION, MODULO_CONFIG}
    return _get_role_permisos(user_rol(user))['modulos']


def user_can_access_modulo(user, modulo):
    """¿El usuario tiene acceso al módulo? (MANTENIMIENTO / CONSTRUCCION / CONFIG)"""
    if not modulo:
        return True
    return modulo in user_modulos(user)


def user_es_admin(user):
    """True si el usuario es nivel admin en cualquiera de sus módulos."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return _get_role_permisos(user_rol(user))['nivel'] == NIVEL_ADMIN


def rol_nivel(codigo):
    """Nivel ('admin'/'operario'/None) de un código de rol -- BD-backed.

    Issue #186 (A4): usado por `Usuario.es_operario_campo`
    (`apps/usuarios/models.py`), que antes importaba `ROL_NIVEL`/
    `NIVEL_OPERARIO` directo del dict eliminado."""
    return _get_role_permisos(codigo)['nivel']


# === Sub-módulos del bloque CONSTRUCCION (#62 iteración 2) ===
# Permite que un especialista sociopredial solo vea Sociopredial,
# o que un capataz de cuadrilla solo vea Obra Civil + Montaje.

SUBMODULO_INGENIERIA = 'INGENIERIA'
SUBMODULO_PRELIMINARES = 'PRELIMINARES'  # sociopredial + socioambiental
SUBMODULO_OBRA_CIVIL = 'OBRA_CIVIL'
SUBMODULO_MONTAJE = 'MONTAJE'
SUBMODULO_SPT = 'SPT'
SUBMODULO_TENDIDO = 'TENDIDO'
SUBMODULO_PROTECCIONES = 'PROTECCIONES'
SUBMODULO_PRUEBAS = 'PRUEBAS'
SUBMODULO_FINANCIERO = 'FINANCIERO'
SUBMODULO_PROGRAMACION = 'PROGRAMACION'
SUBMODULO_DASHBOARDS = 'DASHBOARDS'

# === /modulo indicadores_construccion_sub_run_a — submódulos nuevos ===
# B1: Actividades Finales (matriz 14×N por proyecto, dossier hand-off).
# B3: Indicadores en General (dashboard ejecutivo construcción).
# B4: Indicadores Mantenimiento V2 (financiero+técnico+ANS contractual).
SUBMODULO_ACTIVIDADES_FINALES = 'ACTIVIDADES_FINALES'
SUBMODULO_INDICADORES_CONSTRUCCION = 'INDICADORES_CONSTRUCCION'
SUBMODULO_INDICADORES_MANTENIMIENTO_V2 = 'INDICADORES_MANTENIMIENTO_V2'

TODOS_SUBMODULOS = {
    SUBMODULO_INGENIERIA, SUBMODULO_PRELIMINARES, SUBMODULO_OBRA_CIVIL,
    SUBMODULO_MONTAJE, SUBMODULO_SPT, SUBMODULO_TENDIDO,
    SUBMODULO_PROTECCIONES, SUBMODULO_PRUEBAS, SUBMODULO_FINANCIERO,
    SUBMODULO_PROGRAMACION, SUBMODULO_DASHBOARDS,
    # /modulo indicadores_construccion_sub_run_a
    SUBMODULO_ACTIVIDADES_FINALES,
    SUBMODULO_INDICADORES_CONSTRUCCION,
    SUBMODULO_INDICADORES_MANTENIMIENTO_V2,
}

# Alias para sub-features que esperen `ALL_SUBMODULOS` (nombre del prompt F2).
ALL_SUBMODULOS = TODOS_SUBMODULOS


def user_submodulos(user):
    """Conjunto de sub-módulos CONSTRUCCION accesibles. Superuser = todos."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return TODOS_SUBMODULOS
    return _get_role_permisos(user_rol(user))['submodulos']


def user_can_access_submodulo(user, submodulo):
    """¿El usuario tiene acceso a este sub-módulo de CONSTRUCCION?"""
    if not submodulo:
        return True
    return submodulo in user_submodulos(user)


def url_inicio_para_usuario(user):
    """URL adonde redirigir al usuario tras login según su rol."""
    if not user or not user.is_authenticated:
        return '/usuarios/login/'
    modulos = user_modulos(user)
    if MODULO_CONFIG in modulos:
        return '/'  # admin general → home con todo visible
    if MODULO_MANTENIMIENTO in modulos and MODULO_CONSTRUCCION in modulos:
        return '/'  # operario_general / coordinador → home selector
    if MODULO_CONSTRUCCION in modulos:
        return '/construccion/'
    if MODULO_MANTENIMIENTO in modulos:
        return '/actividades/'
    return '/'
