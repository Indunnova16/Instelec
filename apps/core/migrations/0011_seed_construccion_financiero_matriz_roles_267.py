# Instelec#267 A7 — Matriz de roles del Módulo Financiero de Construcción.
#
# CAUSA RAÍZ encontrada al auditar la BD prod (previa a este seed):
#   role_codigo         | modulo       | submodulo  | nivel_acceso
#   admin_construccion  | CONSTRUCCION | FINANCIERO | ver          <- sin cargar
#   director            | CONSTRUCCION | FINANCIERO | ver_editar   <- ok
#   (gerente_financiero, contador, supervisor: SIN FILA -> sin_acceso total,
#    ni siquiera pueden VER el módulo hoy)
#
# `ProyectoFinMixin` (apps/construccion/views_fin.py) declara
# `required_submodulo = 'FINANCIERO'`, y `RoleRequiredMixin.test_func`
# (apps/core/mixins.py) resuelve ESE branch ANTES de llegar al bypass
# `admin_bypass`/`user_es_admin` -- es decir, para estas vistas el acceso lo
# decide EXCLUSIVAMENTE `RoleModuloPermiso` (ver/ver_editar), sin importar si
# el rol tiene `nivel='admin'` en BD. El docstring de `ProyectoFinMixin`
# ("los roles admin pasan vía RoleRequiredMixin de todos modos") es
# INEXACTO para este caso -- corregido en el mismo commit de código.
#
# Fuente de la matriz objetivo: respuesta del cliente en el issue #267
# (comentario @Indunnova, tabla Rol×Cargar×Ver×Reportes) + roles reales
# verificados en BD prod (tabla `roles`, RBAC #186):
#
#   Rol cliente        | Rol BD (codigo)              | Cargar | Ver
#   Admin Instelec       admin* (nivel=admin, bypass)    ✅      ✅   (sin fila -- ver nota abajo)
#   Gerente Financiero   gerente_financiero               ✅      ✅
#   Contador (Claudia)   contador                          ❌      ✅
#   Gerente Proyecto     director                          ✅      ✅   (ya sembrado, sin cambio)
#                         admin_construccion                ✅      ✅   (upgrade ver -> ver_editar)
#   Supervisor            supervisor                        ❌      ✅
#
# NOTA -- "Admin Instelec" (nivel=admin genérico: admin/admin_general/
# coordinador_general/admin_mantenimiento) NO se siembra acá: esos roles
# tampoco tienen fila FINANCIERO/CONSTRUCCION hoy, así que HEREDAN el mismo
# gap que gerente_financiero/contador/supervisor para ESTE submódulo
# puntual (bug pre-existente, fuera del blast radius mínimo de #267 A7 --
# reportado aparte si Miguel confirma que también afecta a un admin real en
# prod; #267 solo pidió la matriz para los 5 roles de la tabla del cliente).
#
# 'Gerente Proyecto' NO existe como rol literal en BD -- mapeado por F2 a
# `director` + `admin_construccion` (decisión documentada, PENDIENTE de
# confirmación explícita del cliente -- ver comentario de cierre del issue).
#
# Se agrega también la fila de "módulo completo" (`submodulo=''`) para
# CONSTRUCCION en los 3 roles nuevos -- mismo gap ya documentado y corregido
# para MANTENIMIENTO en `0009_seed_modulo_completo_contador_gerente_
# financiero.py`: `user_modulos()` solo cuenta filas sin submódulo, y
# `templates/components/sidebar.html` envuelve TODO el bloque "CONSTRUCCION
# MENU" en `{% if ok_cons %}` antes de evaluar `{% if ok_fin_construccion %}`
# -- sin la fila de módulo completo, el usuario pasa el RBAC de vista
# (entra por URL directa) pero no ve el ítem en el menú.
from django.db import migrations

MODULO_CONSTRUCCION = "CONSTRUCCION"
SUBMODULO_FINANCIERO = "FINANCIERO"
VER = "ver"
VER_EDITAR = "ver_editar"

# (codigo, nivel_acceso módulo-completo, nivel_acceso submódulo FINANCIERO)
FILAS_ROLES_NUEVOS = [
    ("gerente_financiero", VER_EDITAR, VER_EDITAR),
    ("contador", VER, VER),
    ("supervisor", VER, VER),
]

# admin_construccion YA tenía fila FINANCIERO ('ver') -- se actualiza a
# ver_editar (cargar). No toca su fila de módulo completo (ya la tenía, o
# el gap es pre-existente y fuera de alcance de #267 -- ver nota arriba).
ROL_UPGRADE_CARGAR = "admin_construccion"

ROLES_AFECTADOS = ["gerente_financiero", "contador", "supervisor", "admin_construccion"]


def seed_matriz_roles(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    Permiso = apps.get_model("core", "RoleModuloPermiso")

    for codigo, nivel_modulo, nivel_fin in FILAS_ROLES_NUEVOS:
        if not Role.objects.filter(codigo=codigo).exists():
            continue
        # Módulo completo (visibilidad de sidebar, #267 espejo de 0009).
        Permiso.objects.update_or_create(
            role_id=codigo,
            modulo=MODULO_CONSTRUCCION,
            submodulo="",
            defaults={"nivel_acceso": nivel_modulo},
        )
        # Submódulo FINANCIERO (gate real de ProyectoFinMixin).
        Permiso.objects.update_or_create(
            role_id=codigo,
            modulo=MODULO_CONSTRUCCION,
            submodulo=SUBMODULO_FINANCIERO,
            defaults={"nivel_acceso": nivel_fin},
        )

    if Role.objects.filter(codigo=ROL_UPGRADE_CARGAR).exists():
        Permiso.objects.update_or_create(
            role_id=ROL_UPGRADE_CARGAR,
            modulo=MODULO_CONSTRUCCION,
            submodulo=SUBMODULO_FINANCIERO,
            defaults={"nivel_acceso": VER_EDITAR},
        )

    # #248/0010: `RunPython` usa modelos HISTÓRICOS -- el `post_save` real
    # (sender=RoleModuloPermiso concreto) nunca dispara, así que la caché de
    # 1h de `_get_role_permisos` queda stale hasta su TTL. Invalidar acá,
    # explícito, mismo fix que 0010.
    from apps.core.permissions import invalidate_role_cache

    for codigo in ROLES_AFECTADOS:
        invalidate_role_cache(codigo)


def unseed_matriz_roles(apps, schema_editor):
    Permiso = apps.get_model("core", "RoleModuloPermiso")

    # Revierte SOLO lo que esta migración creó/cambió.
    codigos_nuevos = [codigo for codigo, _m, _f in FILAS_ROLES_NUEVOS]
    Permiso.objects.filter(
        role_id__in=codigos_nuevos,
        modulo=MODULO_CONSTRUCCION,
        submodulo__in=["", SUBMODULO_FINANCIERO],
    ).delete()
    Permiso.objects.update_or_create(
        role_id=ROL_UPGRADE_CARGAR,
        modulo=MODULO_CONSTRUCCION,
        submodulo=SUBMODULO_FINANCIERO,
        defaults={"nivel_acceso": VER},
    )

    from apps.core.permissions import invalidate_role_cache

    for codigo in ROLES_AFECTADOS:
        invalidate_role_cache(codigo)


class Migration(migrations.Migration):
    dependencies = [("core", "0010_invalidate_role_cache_248")]
    operations = [
        migrations.RunPython(seed_matriz_roles, unseed_matriz_roles),
    ]
