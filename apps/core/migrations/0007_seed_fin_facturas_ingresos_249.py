"""Hoja granular de Facturas de Ingresos (#249 v2).

Reemplaza `allowed_roles=["admin","director","coordinador"]` en
`views_finv2_ingresos.py` por el submódulo RBAC granular
`FIN_FACTURAS_INGRESOS`. Preserva el acceso previo de esos 3 roles legacy
(y sus equivalentes RBAC v2 admin_general/coordinador_general) con
`ver_editar` -- mismo criterio de `0006_seed_fin_homologacion_247.py` -- para
no dejar a nadie afuera de lo que ya usaba en producción.
"""

from django.db import migrations


FILAS = [
    ("admin", "ver_editar"),
    ("admin_general", "ver_editar"),
    ("director", "ver_editar"),
    ("coordinador", "ver_editar"),
    ("coordinador_general", "ver_editar"),
]


def seed_fin_facturas_ingresos(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    Permiso = apps.get_model("core", "RoleModuloPermiso")
    for codigo, nivel in FILAS:
        if Role.objects.filter(codigo=codigo).exists():
            Permiso.objects.update_or_create(
                role_id=codigo,
                modulo="MANTENIMIENTO",
                submodulo="FIN_FACTURAS_INGRESOS",
                defaults={"nivel_acceso": nivel},
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0006_seed_fin_homologacion_247")]
    operations = [migrations.RunPython(seed_fin_facturas_ingresos, migrations.RunPython.noop)]
