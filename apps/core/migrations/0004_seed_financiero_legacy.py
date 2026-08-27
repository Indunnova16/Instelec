# Issue #186 (A3): preservar el acceso legacy a Financiero (apps/financiero/)
# antes de reemplazar el gate coarse por el granular en el middleware.
#
# Hoy /financiero/* esta gateado por dos capas independientes: (1)
# RBACModuloMiddleware exige MODULO_MANTENIMIENTO a nivel de path completo, y
# (2) cada vista de apps/financiero/views.py declara
# `allowed_roles = ['admin', 'director', 'coordinador']` via RoleRequiredMixin
# -- pero ese mixin hace bypass automatico para CUALQUIER rol nivel admin,
# independientemente de `allowed_roles` (ver su docstring). El acceso
# EFECTIVO actual es entonces: rol nivel=admin CON acceso al modulo
# Mantenimiento. De los 15 roles del catalogo legacy eso son exactamente:
# admin_general, coordinador_general, admin_mantenimiento, admin, director,
# coordinador (admin_construccion es nivel admin pero NO tiene modulo
# Mantenimiento -> hoy tampoco entra a Financiero, no se le siembra nada).
#
# A3 reemplaza el gate de MODULO por el gate GRANULAR (por submodulo FIN_*) en
# el middleware -- sin este seed, esos 6 roles perderian acceso el dia que el
# nuevo gate entre en vigencia, porque ninguna fila FIN_* existia antes de A2.
from django.db import migrations

from apps.core.rbac_seed_data import (
    NIVEL_ACCESO_VER_EDITAR,
    SUBMODULOS_FINANCIERO_APP,
    _ROLES_CON_ACCESO_LEGACY_A_FINANCIERO,
)


def seed_financiero_legacy(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    RoleModuloPermiso = apps.get_model("core", "RoleModuloPermiso")

    roles = Role.objects.filter(codigo__in=_ROLES_CON_ACCESO_LEGACY_A_FINANCIERO)
    for role in roles.iterator():
        for submodulo in SUBMODULOS_FINANCIERO_APP:
            RoleModuloPermiso.objects.get_or_create(
                role=role,
                modulo="MANTENIMIENTO",
                submodulo=submodulo,
                defaults={"nivel_acceso": NIVEL_ACCESO_VER_EDITAR},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_rbac_submodulos"),
    ]

    operations = [
        migrations.RunPython(seed_financiero_legacy, migrations.RunPython.noop),
    ]
