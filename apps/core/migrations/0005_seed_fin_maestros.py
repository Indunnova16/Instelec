"""Semilla RBAC de la hoja Financiero/Maestros (#261, #262)."""

from django.db import migrations


FILAS = [
    ("admin", "ver_editar"),
    ("admin_general", "ver_editar"),
    ("coordinador", "ver"),
    ("coordinador_general", "ver"),
    ("supervisor", "ver"),
    ("director", "ver"),
]


def seed_fin_maestros(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    RoleModuloPermiso = apps.get_model("core", "RoleModuloPermiso")
    for codigo, nivel in FILAS:
        if not Role.objects.filter(codigo=codigo).exists():
            continue
        RoleModuloPermiso.objects.update_or_create(
            role_id=codigo,
            modulo="MANTENIMIENTO",
            submodulo="FIN_MAESTROS",
            defaults={"nivel_acceso": nivel},
        )


def unseed_fin_maestros(apps, schema_editor):
    RoleModuloPermiso = apps.get_model("core", "RoleModuloPermiso")
    RoleModuloPermiso.objects.filter(
        modulo="MANTENIMIENTO", submodulo="FIN_MAESTROS"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_seed_financiero_legacy"),
        ("financiero", "0015_maestros_clientes_proveedores"),
    ]

    operations = [migrations.RunPython(seed_fin_maestros, unseed_fin_maestros)]
