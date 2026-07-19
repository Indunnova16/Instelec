"""Snapshot congelado de la matriz RBAC legacy (issue #186, Gate de Paridad §3).

Copia VERBATIM de `ROL_MODULOS` / `ROL_NIVEL` / `ROL_SUBMODULOS` de
`apps/core/permissions.py` (líneas 15-33, 36-53, 124-145), tomada el
2026-07-18 — ANTES de que A3 reescriba `permissions.py` para leer de BD y
elimine esos dicts. Es la fuente ÚNICA de verdad, reusada por:

  1. `apps/core/migrations/0002_seed_roles_permisos.py` — puebla
     `Role`/`RoleModuloPermiso` en BD (prod).
  2. `apps/core/tests_issue_186_paridad_rbac.py` — snapshot "VIEJO" del Gate
     de Paridad (comparado 1:1 contra el sistema "NUEVO" BD-backed post A3).

Nota de diseño: en vez de transcribir estos dicts dos veces (una en la
migración, otra en el test), se centralizan en un único módulo de datos
puros (sin dependencias de Django) para que NO exista riesgo de que
migración y test diverjan por un error de transcripción — justo el tipo de
bug que el Gate de Paridad existe para atrapar. NO modificar estos valores
aunque cambie el catálogo BD en el futuro — son el ancla histórica del gate.

Nota sobre el conteo de roles: el plan de F2 (SPRINTS/PLAN_2026-07-18_issue186_*)
habla de "14 roles". El conteo REAL de `Usuario.Rol.choices`
(apps/usuarios/models.py) es **15** (7 RBAC v2 + 8 legacy, no 7+7). Se migran
los 15 — dejar 1 rol legacy sin fila en `Role` sería exactamente el tipo de
bug de paridad silenciosa que este gate busca prevenir.
"""

MODULO_MANTENIMIENTO = "MANTENIMIENTO"
MODULO_CONSTRUCCION = "CONSTRUCCION"
MODULO_CONFIG = "CONFIG"

NIVEL_ADMIN = "admin"
NIVEL_OPERARIO = "operario"

SUBMODULO_INGENIERIA = "INGENIERIA"
SUBMODULO_PRELIMINARES = "PRELIMINARES"
SUBMODULO_OBRA_CIVIL = "OBRA_CIVIL"
SUBMODULO_MONTAJE = "MONTAJE"
SUBMODULO_SPT = "SPT"
SUBMODULO_TENDIDO = "TENDIDO"
SUBMODULO_PROTECCIONES = "PROTECCIONES"
SUBMODULO_PRUEBAS = "PRUEBAS"
SUBMODULO_FINANCIERO = "FINANCIERO"
SUBMODULO_PROGRAMACION = "PROGRAMACION"
SUBMODULO_DASHBOARDS = "DASHBOARDS"
SUBMODULO_ACTIVIDADES_FINALES = "ACTIVIDADES_FINALES"
SUBMODULO_INDICADORES_CONSTRUCCION = "INDICADORES_CONSTRUCCION"
SUBMODULO_INDICADORES_MANTENIMIENTO_V2 = "INDICADORES_MANTENIMIENTO_V2"

TODOS_SUBMODULOS = {
    SUBMODULO_INGENIERIA,
    SUBMODULO_PRELIMINARES,
    SUBMODULO_OBRA_CIVIL,
    SUBMODULO_MONTAJE,
    SUBMODULO_SPT,
    SUBMODULO_TENDIDO,
    SUBMODULO_PROTECCIONES,
    SUBMODULO_PRUEBAS,
    SUBMODULO_FINANCIERO,
    SUBMODULO_PROGRAMACION,
    SUBMODULO_DASHBOARDS,
    SUBMODULO_ACTIVIDADES_FINALES,
    SUBMODULO_INDICADORES_CONSTRUCCION,
    SUBMODULO_INDICADORES_MANTENIMIENTO_V2,
}

# (codigo, nombre — verbatim de Usuario.Rol.choices, legacy)
ROLES = [
    ("admin_general", "Administrador General", False),
    ("coordinador_general", "Coordinador General", False),
    ("admin_mantenimiento", "Administrador de Mantenimiento", False),
    ("admin_construccion", "Administrador de Construcción", False),
    ("operario_mantenimiento", "Operario de Mantenimiento", False),
    ("operario_construccion", "Operario de Construcción", False),
    ("operario_general", "Operario General", False),
    ("admin", "Administrador (legacy)", True),
    ("director", "Director de Proyecto (legacy)", True),
    ("coordinador", "Coordinador (legacy)", True),
    ("ing_residente", "Ingeniero Residente (legacy)", True),
    ("ing_ambiental", "Ingeniero Ambiental (legacy)", True),
    ("supervisor", "Supervisor de Cuadrilla (legacy)", True),
    ("liniero", "Liniero (legacy)", True),
    ("auxiliar", "Auxiliar (legacy)", True),
]

TODOS_LOS_CODIGOS = [codigo for codigo, _nombre, _legacy in ROLES]

# rol → set de módulos accesibles (copia verbatim de permissions.ROL_MODULOS)
ROL_MODULOS = {
    "admin_general": {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION, MODULO_CONFIG},
    "coordinador_general": {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    "admin_mantenimiento": {MODULO_MANTENIMIENTO},
    "admin_construccion": {MODULO_CONSTRUCCION},
    "operario_mantenimiento": {MODULO_MANTENIMIENTO},
    "operario_construccion": {MODULO_CONSTRUCCION},
    "operario_general": {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    "admin": {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION, MODULO_CONFIG},
    "director": {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    "coordinador": {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    "ing_residente": {MODULO_MANTENIMIENTO, MODULO_CONSTRUCCION},
    "ing_ambiental": {MODULO_MANTENIMIENTO},
    "supervisor": {MODULO_MANTENIMIENTO},
    "liniero": {MODULO_MANTENIMIENTO},
    "auxiliar": {MODULO_MANTENIMIENTO},
}

# rol → nivel (copia verbatim de permissions.ROL_NIVEL)
ROL_NIVEL = {
    "admin_general": NIVEL_ADMIN,
    "coordinador_general": NIVEL_ADMIN,
    "admin_mantenimiento": NIVEL_ADMIN,
    "admin_construccion": NIVEL_ADMIN,
    "operario_mantenimiento": NIVEL_OPERARIO,
    "operario_construccion": NIVEL_OPERARIO,
    "operario_general": NIVEL_OPERARIO,
    "admin": NIVEL_ADMIN,
    "director": NIVEL_ADMIN,
    "coordinador": NIVEL_ADMIN,
    "ing_residente": NIVEL_ADMIN,
    "ing_ambiental": NIVEL_ADMIN,
    "supervisor": NIVEL_OPERARIO,
    "liniero": NIVEL_OPERARIO,
    "auxiliar": NIVEL_OPERARIO,
}

# rol → sub-módulos CONSTRUCCION accesibles (copia verbatim de permissions.ROL_SUBMODULOS)
# admin_mantenimiento / operario_mantenimiento NO tienen entrada — ausencia = set() (correcto:
# esos roles no tienen MODULO_CONSTRUCCION en absoluto).
ROL_SUBMODULOS = {
    "admin_general": TODOS_SUBMODULOS,
    "coordinador_general": TODOS_SUBMODULOS,
    "admin_construccion": TODOS_SUBMODULOS,
    "operario_construccion": {
        SUBMODULO_OBRA_CIVIL,
        SUBMODULO_MONTAJE,
        SUBMODULO_SPT,
        SUBMODULO_TENDIDO,
        SUBMODULO_PROTECCIONES,
    },
    "operario_general": {
        SUBMODULO_OBRA_CIVIL,
        SUBMODULO_MONTAJE,
        SUBMODULO_SPT,
        SUBMODULO_TENDIDO,
        SUBMODULO_PROTECCIONES,
    },
    "admin": TODOS_SUBMODULOS,
    "director": TODOS_SUBMODULOS,
    "coordinador": TODOS_SUBMODULOS,
    "ing_residente": TODOS_SUBMODULOS - {SUBMODULO_FINANCIERO},
    "ing_ambiental": {SUBMODULO_PRELIMINARES, SUBMODULO_INGENIERIA},
    "supervisor": {SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE, SUBMODULO_TENDIDO},
    "liniero": {SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE, SUBMODULO_TENDIDO},
    "auxiliar": {SUBMODULO_OBRA_CIVIL, SUBMODULO_MONTAJE},
}


def nivel_acceso_modulo(codigo_rol):
    """`ver_editar` para nivel admin, `ver` para nivel operario (mapeo binario
    legacy → 3 estados, ver PLAN §2/§3 — este sprint solo puebla estos 2)."""
    return "ver_editar" if ROL_NIVEL.get(codigo_rol) == NIVEL_ADMIN else "ver"


def seed_roles_permisos_bd():
    """Puebla `Role`/`RoleModuloPermiso` vía ORM real (modelos reales, NO
    `apps.get_model` histórico) reproduciendo EXACTAMENTE la migración
    `0002_seed_roles_permisos.py`.

    Existe porque `pytest` corre con `--nomigrations` (ver `pyproject.toml`)
    — la migración de datos real NUNCA se ejecuta en la suite de tests, así
    que CUALQUIER test que dependa de acceso por rol (RBAC,
    `RoleRequiredMixin`, `RBACModuloMiddleware`, que ahora leen de BD post
    A3) necesita este seed. Usado por:
      - `conftest.py` (`django_db_setup`) — una vez por sesión de pytest,
        para TODA la suite (issue #186, A3 — blast radius global).
      - `apps/core/tests_issue_186_paridad_rbac.py` — el Gate de Paridad.

    Import de los modelos diferido (dentro de la función) para que este
    módulo siga siendo importable sin apps Django cargadas (p.ej. desde la
    migración 0002, que usa `apps.get_model` en vez de este helper).
    """
    from apps.core.models import Role, RoleModuloPermiso

    for codigo, nombre, legacy in ROLES:
        role, _created = Role.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "nivel": ROL_NIVEL.get(codigo),
                "legacy": legacy,
                "activo": True,
            },
        )
        nivel_acceso = nivel_acceso_modulo(codigo)

        for modulo in ROL_MODULOS.get(codigo, set()):
            RoleModuloPermiso.objects.get_or_create(
                role=role,
                modulo=modulo,
                submodulo=None,
                defaults={"nivel_acceso": nivel_acceso},
            )

        for submodulo in ROL_SUBMODULOS.get(codigo, set()):
            RoleModuloPermiso.objects.get_or_create(
                role=role,
                modulo=MODULO_CONSTRUCCION,
                submodulo=submodulo,
                defaults={"nivel_acceso": nivel_acceso},
            )
