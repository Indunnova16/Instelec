"""RBAC permissions (#44).

Matriz rol → módulos y nivel de acceso. Mantiene retro-compatibilidad
con los roles legacy del modelo `Usuario.Rol`.
"""

MODULO_MANTENIMIENTO = 'MANTENIMIENTO'
MODULO_CONSTRUCCION = 'CONSTRUCCION'
MODULO_CONFIG = 'CONFIG'  # gestión de usuarios, parametrización, sistema

NIVEL_ADMIN = 'admin'
NIVEL_OPERARIO = 'operario'

# rol → set de módulos accesibles
ROL_MODULOS = {
    # RBAC v2 (#44)
    'admin_general':          {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION, MODULO_CONFIG},
    'coordinador_general':    {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    'admin_mantenimiento':    {MODULO_MANTENIMIENTO},
    'admin_construccion':     {MODULO_CONSTRUCCION},
    'operario_mantenimiento': {MODULO_MANTENIMIENTO},
    'operario_construccion':  {MODULO_CONSTRUCCION},
    'operario_general':       {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    # Legacy — heredan acceso amplio para no romper datos existentes
    'admin':         {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION, MODULO_CONFIG},
    'director':      {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    'coordinador':   {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    'ing_residente': {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    'ing_ambiental': {MODULO_MANTENIMIENTO},
    'supervisor':    {MODULO_MANTENIMIENTO},
    'liniero':       {MODULO_MANTENIMIENTO},
    'auxiliar':      {MODULO_MANTENIMIENTO},
}

# rol → nivel (admin = puede crear/editar/borrar; operario = ops solo)
ROL_NIVEL = {
    'admin_general':          NIVEL_ADMIN,
    'coordinador_general':    NIVEL_ADMIN,
    'admin_mantenimiento':    NIVEL_ADMIN,
    'admin_construccion':     NIVEL_ADMIN,
    'operario_mantenimiento': NIVEL_OPERARIO,
    'operario_construccion':  NIVEL_OPERARIO,
    'operario_general':       NIVEL_OPERARIO,
    # Legacy
    'admin':         NIVEL_ADMIN,
    'director':      NIVEL_ADMIN,
    'coordinador':   NIVEL_ADMIN,
    'ing_residente': NIVEL_ADMIN,
    'ing_ambiental': NIVEL_ADMIN,
    'supervisor':    NIVEL_OPERARIO,
    'liniero':       NIVEL_OPERARIO,
    'auxiliar':      NIVEL_OPERARIO,
}


def user_rol(user):
    return getattr(user, 'rol', '') or ''


def user_modulos(user):
    """Conjunto de módulos accesibles para el usuario. Superuser = todos."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION, MODULO_CONFIG}
    return ROL_MODULOS.get(user_rol(user), set())


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
    return ROL_NIVEL.get(user_rol(user)) == NIVEL_ADMIN


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

# Mapeo rol → sub-módulos CONSTRUCCION accesibles
ROL_SUBMODULOS = {
    'admin_general':          TODOS_SUBMODULOS,
    'coordinador_general':    TODOS_SUBMODULOS,
    'admin_construccion':     TODOS_SUBMODULOS,
    'operario_construccion':  {
        SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE, SUBMODULO_SPT,
        SUBMODULO_TENDIDO, SUBMODULO_PROTECCIONES,
    },  # campo ops, sin finanzas / preliminares / pruebas / dashboards
    'operario_general':       {
        SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE, SUBMODULO_SPT,
        SUBMODULO_TENDIDO, SUBMODULO_PROTECCIONES,
    },
    # Legacy
    'admin':         TODOS_SUBMODULOS,
    'director':      TODOS_SUBMODULOS,
    'coordinador':   TODOS_SUBMODULOS,
    'ing_residente': TODOS_SUBMODULOS - {SUBMODULO_FINANCIERO},
    'ing_ambiental': {SUBMODULO_PRELIMINARES, SUBMODULO_INGENIERIA},
    'supervisor':    {SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE, SUBMODULO_TENDIDO},
    'liniero':       {SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE, SUBMODULO_TENDIDO},
    'auxiliar':      {SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE},
}


def user_submodulos(user):
    """Conjunto de sub-módulos CONSTRUCCION accesibles. Superuser = todos."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return TODOS_SUBMODULOS
    return ROL_SUBMODULOS.get(user_rol(user), set())


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
