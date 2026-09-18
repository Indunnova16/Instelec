"""Hoja granular de Facturas de Gastos (#248) + roles nuevos Contador /
Gerente Financiero.

Dos cosas en una migración porque son parte del mismo gap RBAC de #248:

1. Siembra el permiso `FIN_FACTURAS_GASTOS` para los roles legacy que hoy
   entran por el `allowed_roles=["admin", "director", "coordinador"]`
   hardcodeado de `views_finv2_gastos.py` (mismo criterio EXACTO de
   `0007_seed_fin_facturas_ingresos_249.py` -- preserva acceso previo, no
   quita nada a nadie).
2. Crea 2 roles NUEVOS (`contador`, `gerente_financiero`, RBAC v2 --
   `legacy=False`) con `nivel='operario'` a propósito: `RoleRequiredMixin`
   hace bypass automático de `allowed_roles` para CUALQUIER rol
   `nivel='admin'` (ver docstring de `0004_seed_financiero_legacy.py`) --
   si estos roles fueran `nivel='admin'` obtendrían acceso a TODO lo
   gateado por ese mixin sin pasar por la matriz granular, contradiciendo
   el requisito de B4 (#246 Sprint D) de que Contador solo vea
   costos/Excel y NO el resto de reportes ejecutivos. Con `nivel='operario'`
   el acceso real lo decide exclusivamente `RoleModuloPermiso` (o el check
   de `role.codigo` que B4 agregue para el tipo de reporte).

Se les siembra `ver_editar` sobre TODOS los submódulos de Financiero
(`SUBMODULOS_FINANCIERO`, incluye `FIN_FACTURAS_GASTOS` recién agregado)
como línea base -- la restricción MÁS FINA de qué reporte puede descargar
cada uno (Contador: costos/Excel, Gerente Financiero: todos) es una regla
de negocio de B4, no de esta hoja RBAC genérica por submódulo.

La asignación real de usuarios Instelec a estos 2 roles nuevos es decisión
de negocio de Andrea/Indunnova, pendiente -- no bloquea este seed (ver
BLUEPRINT §decisiones_pendientes).
"""

from django.db import migrations

from apps.core.permissions import SUBMODULOS_FINANCIERO

MODULO_MANTENIMIENTO = "MANTENIMIENTO"

# Idéntico criterio de 0007_seed_fin_facturas_ingresos_249.py: preserva el
# acceso legacy de allowed_roles=["admin", "director", "coordinador"]
# (views_finv2_gastos.py) + sus equivalentes RBAC v2.
FILAS_LEGACY_FACTURAS_GASTOS = [
    ("admin", "ver_editar"),
    ("admin_general", "ver_editar"),
    ("director", "ver_editar"),
    ("coordinador", "ver_editar"),
    ("coordinador_general", "ver_editar"),
]

# (codigo, nombre) de los 2 roles nuevos sembrados por esta migración.
ROLES_NUEVOS = [
    ("contador", "Contador"),
    ("gerente_financiero", "Gerente Financiero"),
]

NIVEL_OPERARIO = "operario"
VER_EDITAR = "ver_editar"


def seed_fin_facturas_gastos_y_roles(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    Permiso = apps.get_model("core", "RoleModuloPermiso")

    # 1. Hoja FIN_FACTURAS_GASTOS para roles legacy existentes.
    for codigo, nivel in FILAS_LEGACY_FACTURAS_GASTOS:
        if Role.objects.filter(codigo=codigo).exists():
            Permiso.objects.update_or_create(
                role_id=codigo,
                modulo=MODULO_MANTENIMIENTO,
                submodulo="FIN_FACTURAS_GASTOS",
                defaults={"nivel_acceso": nivel},
            )

    # 2. Roles nuevos + su RBAC inicial sobre TODOS los submódulos Financiero.
    for codigo, nombre in ROLES_NUEVOS:
        role, _created = Role.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "nivel": NIVEL_OPERARIO,
                "legacy": False,
                "activo": True,
            },
        )
        for submodulo in SUBMODULOS_FINANCIERO:
            Permiso.objects.update_or_create(
                role=role,
                modulo=MODULO_MANTENIMIENTO,
                submodulo=submodulo,
                defaults={"nivel_acceso": VER_EDITAR},
            )


def unseed_fin_facturas_gastos_y_roles(apps, schema_editor):
    """Reversa: borra la hoja FIN_FACTURAS_GASTOS legacy y los 2 roles
    nuevos (CASCADE se lleva sus RoleModuloPermiso)."""
    Role = apps.get_model("core", "Role")
    Permiso = apps.get_model("core", "RoleModuloPermiso")
    Permiso.objects.filter(
        modulo=MODULO_MANTENIMIENTO, submodulo="FIN_FACTURAS_GASTOS"
    ).delete()
    Role.objects.filter(
        codigo__in=[codigo for codigo, _nombre in ROLES_NUEVOS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0007_seed_fin_facturas_ingresos_249")]
    operations = [
        migrations.RunPython(
            seed_fin_facturas_gastos_y_roles, unseed_fin_facturas_gastos_y_roles
        )
    ]
