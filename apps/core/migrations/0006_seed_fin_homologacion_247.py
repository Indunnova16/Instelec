"""Hoja granular de la Tabla Maestra (#247)."""
from django.db import migrations


FILAS = [
    ('admin', 'ver_editar'), ('admin_general', 'ver_editar'),
    ('coordinador', 'ver'), ('coordinador_general', 'ver'),
    ('supervisor', 'ver'), ('director', 'ver'),
]


def seed_fin_homologacion(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Permiso = apps.get_model('core', 'RoleModuloPermiso')
    for codigo, nivel in FILAS:
        if Role.objects.filter(codigo=codigo).exists():
            Permiso.objects.update_or_create(role_id=codigo, modulo='MANTENIMIENTO', submodulo='FIN_HOMOLOGACION', defaults={'nivel_acceso': nivel})


class Migration(migrations.Migration):
    dependencies = [('core', '0005_seed_fin_maestros')]
    operations = [migrations.RunPython(seed_fin_homologacion, migrations.RunPython.noop)]
