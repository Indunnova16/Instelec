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

# === Área de la persona (issue #186, 186-M4) ==============================
# Catálogo compartido por `Usuario` (apps/usuarios/models.py) y
# `PersonalCuadrilla` (apps/cuadrillas/models_base.py) -- decisión de diseño
# del revisor: el Área vive en la PERSONA, NO en el Cargo (cargos como
# "Liniero I"/"Conductor"/"Supervisor" existen en ambas áreas; ponerlo en el
# Cargo hubiera obligado a duplicarlo por área). Es un filtro DE VISTA sobre
# el listado de Usuarios (Parametrización) -- el listado completo sigue
# existiendo sin filtrar, no segmenta la BD en tablas separadas. Centralizado
# acá (no un TextChoices por-app) para que ambos modelos usen exactamente
# los mismos 3 valores sin riesgo de divergencia.
AREA_CONSTRUCCION = 'CONSTRUCCION'
AREA_MANTENIMIENTO = 'MANTENIMIENTO'
AREA_FINANCIERO = 'FINANCIERO'
AREA_CHOICES = [
    (AREA_CONSTRUCCION, 'Construcción'),
    (AREA_MANTENIMIENTO, 'Mantenimiento'),
    (AREA_FINANCIERO, 'Financiero'),
]

# Debe coincidir con RoleModuloPermiso.SIN_ACCESO (apps/core/models_roles.py).
# Literal (no import) para evitar un ciclo de import a nivel de módulo entre
# permissions.py y models_roles.py -- _get_role_permisos() abajo sí importa
# Role, pero de forma diferida (dentro de la función, no al tope del módulo).
_SIN_ACCESO = 'sin_acceso'

CACHE_TTL_ROLE_PERMISOS = 3600  # 1h -- con invalidación explícita por señal, ver arriba
CACHE_KEY_ROLE_PERMISOS = 'instelec:rbac:role:{codigo}'


def _cache_key_role(codigo):
    return CACHE_KEY_ROLE_PERMISOS.format(codigo=codigo)


_DICT_VACIO = {
    'modulos': set(), 'submodulos': set(),
    'submodulos_por_modulo': {}, 'modulos_denegados': set(), 'nivel': None,
}


def _get_role_permisos(codigo):
    """dict con módulos, submódulos por padre, denegaciones explícitas y nivel
    para un código de rol.

    ``submodulos`` se mantiene como unión compatible para los consumidores
    existentes. ``submodulos_por_modulo`` conserva el padre de cada permiso,
    necesario desde que Mantenimiento también tiene hojas granulares.
    ``modulos_denegados`` distingue "sin fila" (ausencia) de "fila explícita
    SIN_ACCESO" a nivel de módulo -- un deny explícito del padre bloquea
    cualquier hoja del mismo módulo aunque tenga su propio permiso granular
    (edge case de seguridad, ver `user_can_access_submodulo`).

    Rol inexistente/inactivo o `codigo` vacío → dict "vacío" (sin acceso a
    nada), consistente con el comportamiento legacy de `dict.get(rol, set())`.
    """
    if not codigo:
        return dict(_DICT_VACIO)

    key = _cache_key_role(codigo)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from .models_roles import Role  # import diferido -- evita ciclo con models.py

    try:
        role = Role.objects.prefetch_related('permisos').get(codigo=codigo, activo=True)
    except Role.DoesNotExist:
        result = dict(_DICT_VACIO)
        cache.set(key, result, CACHE_TTL_ROLE_PERMISOS)
        return result

    todos_los_permisos = list(role.permisos.all())
    permisos_con_acceso = [p for p in todos_los_permisos if p.nivel_acceso != _SIN_ACCESO]
    submodulos_por_modulo = {}
    for permiso in permisos_con_acceso:
        if permiso.submodulo:
            submodulos_por_modulo.setdefault(permiso.modulo, set()).add(permiso.submodulo)

    result = {
        'modulos': {p.modulo for p in permisos_con_acceso if not p.submodulo},
        'submodulos': {p.submodulo for p in permisos_con_acceso if p.submodulo},
        'submodulos_por_modulo': submodulos_por_modulo,
        'modulos_denegados': {
            p.modulo for p in todos_los_permisos
            if not p.submodulo and p.nivel_acceso == _SIN_ACCESO
        },
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

SUBMODULOS_CONSTRUCCION = {
    SUBMODULO_INGENIERIA, SUBMODULO_PRELIMINARES, SUBMODULO_OBRA_CIVIL,
    SUBMODULO_MONTAJE, SUBMODULO_SPT, SUBMODULO_TENDIDO,
    SUBMODULO_PROTECCIONES, SUBMODULO_PRUEBAS, SUBMODULO_FINANCIERO,
    SUBMODULO_PROGRAMACION, SUBMODULO_DASHBOARDS,
    # /modulo indicadores_construccion_sub_run_a
    SUBMODULO_ACTIVIDADES_FINALES,
    SUBMODULO_INDICADORES_CONSTRUCCION,
    SUBMODULO_INDICADORES_MANTENIMIENTO_V2,
}

# === Sub-módulos del bloque MANTENIMIENTO (issue #186, A1) ==============
# Los códigos llevan el prefijo del módulo para que el catálogo siga siendo
# inequívoco cuando otros módulos (p.ej. Financiero) incorporen hojas con
# nombres similares. La etiqueta visible se resuelve en la matriz/UI.
SUBMODULO_MANTENIMIENTO_ACTIVIDADES = 'MANTENIMIENTO_ACTIVIDADES'
SUBMODULO_MANTENIMIENTO_LINEAS_TORRES = 'MANTENIMIENTO_LINEAS_TORRES'
SUBMODULO_MANTENIMIENTO_CAMPO = 'MANTENIMIENTO_CAMPO'
SUBMODULO_MANTENIMIENTO_PROCEDIMIENTOS = 'MANTENIMIENTO_PROCEDIMIENTOS'

SUBMODULOS_MANTENIMIENTO = {
    SUBMODULO_MANTENIMIENTO_ACTIVIDADES,
    SUBMODULO_MANTENIMIENTO_LINEAS_TORRES,
    SUBMODULO_MANTENIMIENTO_CAMPO,
    SUBMODULO_MANTENIMIENTO_PROCEDIMIENTOS,
}

# === Sub-módulos del bloque CONFIG (issue #186, A2) =====================
# Incluye tanto Configuración/Parametrización propiamente dicha como
# Financiero (`apps/financiero/`) -- decisión de diseño documentada en
# `rbac_seed_data.SUBMODULOS_FINANCIERO_APP`: no existe un MODULO_FINANCIERO
# de nivel superior y el plan de A4 fija la matriz en 3 columnas.
SUBMODULO_FIN_DASHBOARD = 'FIN_DASHBOARD'
SUBMODULO_FIN_PRESUPUESTO_PLANEADO = 'FIN_PRESUPUESTO_PLANEADO'
SUBMODULO_FIN_PRESUPUESTO_REAL = 'FIN_PRESUPUESTO_REAL'
SUBMODULO_FIN_CHECKLIST_FACTURACION = 'FIN_CHECKLIST_FACTURACION'
SUBMODULO_FIN_COSTOS_CUADRILLA = 'FIN_COSTOS_CUADRILLA'
SUBMODULO_FIN_NOMINA = 'FIN_NOMINA'

SUBMODULO_CONFIG_USUARIOS = 'CONFIG_USUARIOS'
SUBMODULO_CONFIG_CARGOS = 'CONFIG_CARGOS'
SUBMODULO_CONFIG_ROLES_PERMISOS = 'CONFIG_ROLES_PERMISOS'
SUBMODULO_CONFIG_VEHICULOS = 'CONFIG_VEHICULOS'
SUBMODULO_CONFIG_COLABORADORES = 'CONFIG_COLABORADORES'

SUBMODULOS_CONFIG = {
    SUBMODULO_FIN_DASHBOARD,
    SUBMODULO_FIN_PRESUPUESTO_PLANEADO,
    SUBMODULO_FIN_PRESUPUESTO_REAL,
    SUBMODULO_FIN_CHECKLIST_FACTURACION,
    SUBMODULO_FIN_COSTOS_CUADRILLA,
    SUBMODULO_FIN_NOMINA,
    SUBMODULO_CONFIG_USUARIOS,
    SUBMODULO_CONFIG_CARGOS,
    SUBMODULO_CONFIG_ROLES_PERMISOS,
    SUBMODULO_CONFIG_VEHICULOS,
    SUBMODULO_CONFIG_COLABORADORES,
}

SUBMODULOS_POR_MODULO = {
    MODULO_CONSTRUCCION: SUBMODULOS_CONSTRUCCION,
    MODULO_MANTENIMIENTO: SUBMODULOS_MANTENIMIENTO,
    MODULO_CONFIG: SUBMODULOS_CONFIG,
}

SUBMODULO_A_MODULO = {
    submodulo: modulo
    for modulo, submodulos in SUBMODULOS_POR_MODULO.items()
    for submodulo in submodulos
}

# Alias histórico: hasta #186 A1 este conjunto solo contenía Construcción.
# Mantenerlo evita romper los consumidores existentes y hace que la matriz
# pueda descubrir el catálogo completo durante la siguiente integración UI.
TODOS_SUBMODULOS = set(SUBMODULO_A_MODULO)

# Alias para sub-features que esperen `ALL_SUBMODULOS` (nombre del prompt F2).
ALL_SUBMODULOS = TODOS_SUBMODULOS


def user_submodulos(user, modulo=None):
    """Sub-módulos accesibles, opcionalmente filtrados por su módulo padre.

    Sin ``modulo`` conserva el contrato legacy y devuelve la unión de todos
    los submódulos. Los nuevos consumidores deben pasar el padre para que un
    código de hoja nunca autorice accidentalmente otro módulo.
    """
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(SUBMODULOS_POR_MODULO.get(modulo, TODOS_SUBMODULOS))
    permisos = _get_role_permisos(user_rol(user))
    if modulo:
        return permisos['submodulos_por_modulo'].get(modulo, set())
    return permisos['submodulos']


def user_can_access_submodulo(user, submodulo, modulo=None):
    """¿El usuario tiene acceso a este submódulo?

    ``modulo`` es opcional para no romper los callers de Construcción; para
    los códigos del catálogo se infiere de forma segura.

    Acceso al submódulo NO requiere acceso al módulo COMPLETO -- ese es
    justamente el punto de la matriz granular (A1): un rol puede tener SOLO
    un submódulo habilitado sin el módulo padre entero (bug detectado por
    test_issue_186_a5_ui_matriz.py::test_rol_nuevo_con_permiso_aparece_en_dropdown_usuarios,
    id:instelec-186-submodulo-exige-modulo-completo).

    PERO un deny EXPLÍCITO del módulo padre (fila SIN_ACCESO a nivel módulo,
    no ausencia de fila) sí bloquea la hoja -- una fila hija no puede saltar
    un permiso padre denegado a propósito (edge case de seguridad, ver
    test_hoja_no_autoriza_si_el_modulo_padre_esta_denegado).
    """
    if not submodulo:
        return True
    modulo = modulo or SUBMODULO_A_MODULO.get(submodulo)
    if modulo and modulo in _get_role_permisos(user_rol(user))['modulos_denegados']:
        return False
    return submodulo in user_submodulos(user, modulo)


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
