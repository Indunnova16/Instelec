# Gap 2 (integración B, reportado por B1 sobre #248): `0008_seed_fin_facturas_
# gastos_y_roles_248.py` crea los roles nuevos `contador`/`gerente_financiero`
# y les siembra `ver_editar` sobre TODOS los submódulos de
# `SUBMODULOS_FINANCIERO` -- pero nunca la fila de "módulo completo"
# (`RoleModuloPermiso(modulo='MANTENIMIENTO', submodulo='')`, sentinel
# documentado en `0002_seed_roles_permisos.py` NOTA A6).
#
# `user_modulos()` (apps/core/permissions.py) sólo cuenta como "módulo
# accesible" las filas SIN submódulo (`submodulo=''`). Sin esa fila,
# `{% puede_acceder 'MANTENIMIENTO' as ok_mant %}` da False para estos 2
# roles, y `templates/components/sidebar.html` envuelve TODO el bloque
# "Financiero" (líneas 194-385, incluida la sección de Facturas de Gastos)
# dentro de `{% if ok_mant %}` -- aunque `user_can_access_submodulo()` NO
# exige el módulo padre completo (ver docstring de esa función y el test
# `test_rol_nuevo_con_permiso_aparece_en_dropdown_usuarios`), el sidebar SÍ
# lo exige a nivel de bloque contenedor. Resultado observable: contador/
# gerente_financiero pasan el RBAC de vista (pueden entrar a las URLs
# directamente) pero no ven NINGÚN ítem de Financiero en el menú.
#
# Migración NUEVA (no se edita 0008, ya "aplicado conceptualmente" -- se
# trata como inmutable por disciplina de migrations) que agrega esa fila de
# módulo completo a los 2 roles, mismo nivel `ver_editar` que ya tienen en
# cada hoja granular individual (0008).
from django.db import migrations

MODULO_MANTENIMIENTO = "MANTENIMIENTO"
VER_EDITAR = "ver_editar"

ROLES_CODIGOS = ["contador", "gerente_financiero"]


def seed_modulo_completo(apps, schema_editor):
    Role = apps.get_model("core", "Role")
    Permiso = apps.get_model("core", "RoleModuloPermiso")
    for codigo in ROLES_CODIGOS:
        if Role.objects.filter(codigo=codigo).exists():
            Permiso.objects.update_or_create(
                role_id=codigo,
                modulo=MODULO_MANTENIMIENTO,
                submodulo="",
                defaults={"nivel_acceso": VER_EDITAR},
            )


def unseed_modulo_completo(apps, schema_editor):
    Permiso = apps.get_model("core", "RoleModuloPermiso")
    Permiso.objects.filter(
        role_id__in=ROLES_CODIGOS,
        modulo=MODULO_MANTENIMIENTO,
        submodulo="",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0008_seed_fin_facturas_gastos_y_roles_248")]
    operations = [
        migrations.RunPython(seed_modulo_completo, unseed_modulo_completo),
    ]
