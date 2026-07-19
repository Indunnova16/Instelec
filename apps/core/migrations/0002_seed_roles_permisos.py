# Issue #186 (A2): sembrar Role/RoleModuloPermiso replicando EXACTAMENTE
# ROL_MODULOS/ROL_NIVEL/ROL_SUBMODULOS de apps/core/permissions.py (a punto
# de eliminarse en A3). Puramente aditivo — no toca Usuario ni ninguna otra
# tabla. La corrección de este mapeo es lo que el Gate de Paridad
# (tests/unit/test_issue_186_paridad_rbac.py) verifica exhaustivamente.
#
# Fuente de datos: apps/core/rbac_seed_data.py — snapshot congelado, ÚNICA
# fuente de verdad compartida con el test de paridad (ver docstring de ese
# módulo para la justificación de diseño). NO editar rbac_seed_data.py
# después de este sprint sin volver a correr el Gate de Paridad completo:
# esta migración solo corre una vez por entorno (prod ya migrado; un
# entorno nuevo que corra `migrate` desde cero debe reproducir el mismo
# resultado byte-a-byte).
#
# NOTA sobre el conteo: el plan (F2) dice "14 roles". El conteo real de
# Usuario.Rol.choices es 15 (7 RBAC v2 + 8 legacy). Se siembran los 15 —
# ver rbac_seed_data.py para el detalle.
from django.db import migrations

from apps.core import rbac_seed_data as data


def seed_roles_permisos(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    RoleModuloPermiso = apps.get_model("core", "RoleModuloPermiso")

    for codigo, nombre, legacy in data.ROLES:
        nivel = data.ROL_NIVEL.get(codigo)
        role, _created = Role.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "nivel": nivel,
                "legacy": legacy,
                "activo": True,
            },
        )

        nivel_acceso = data.nivel_acceso_modulo(codigo)

        # Permisos de MÓDULO completo (submodulo=None)
        for modulo in data.ROL_MODULOS.get(codigo, set()):
            RoleModuloPermiso.objects.get_or_create(
                role=role,
                modulo=modulo,
                submodulo=None,
                defaults={"nivel_acceso": nivel_acceso},
            )

        # Permisos de SUB-MÓDULO (siempre dentro de CONSTRUCCION)
        for submodulo in data.ROL_SUBMODULOS.get(codigo, set()):
            RoleModuloPermiso.objects.get_or_create(
                role=role,
                modulo=data.MODULO_CONSTRUCCION,
                submodulo=submodulo,
                defaults={"nivel_acceso": nivel_acceso},
            )


def unseed_roles_permisos(apps, schema_editor):
    """Reversa: borra los 15 roles sembrados (CASCADE se lleva sus permisos)."""
    Role = apps.get_model("core", "Role")
    Role.objects.filter(codigo__in=data.TODOS_LOS_CODIGOS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_role_rolemodulopermiso"),
    ]

    operations = [
        migrations.RunPython(seed_roles_permisos, reverse_code=unseed_roles_permisos),
    ]
