# Issue #186 (A1): hojas granulares de Mantenimiento.
#
# Cada Role existente conserva exactamente su acceso efectivo: si tenía una
# fila general de Mantenimiento, se crean sus cuatro hojas con ese mismo nivel.
# No se sobreescriben filas granulares que un administrador ya haya ajustado.
from django.db import migrations

from apps.core.rbac_seed_data import SUBMODULOS_MANTENIMIENTO


def seed_submodulos_mantenimiento(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    RoleModuloPermiso = apps.get_model("core", "RoleModuloPermiso")

    for role in Role.objects.all().iterator():
        permiso_modulo = RoleModuloPermiso.objects.filter(
            role=role,
            modulo="MANTENIMIENTO",
            submodulo="",
        ).first()
        if permiso_modulo is None:
            continue

        for submodulo in SUBMODULOS_MANTENIMIENTO:
            RoleModuloPermiso.objects.get_or_create(
                role=role,
                modulo="MANTENIMIENTO",
                submodulo=submodulo,
                defaults={"nivel_acceso": permiso_modulo.nivel_acceso},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_seed_roles_permisos"),
    ]

    operations = [
        migrations.RunPython(seed_submodulos_mantenimiento, migrations.RunPython.noop),
    ]
