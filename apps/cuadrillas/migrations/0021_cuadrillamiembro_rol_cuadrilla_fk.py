# Issue #176 (A3): CuadrillaMiembro.rol_cuadrilla de CharField+choices
# (TextChoices RolCuadrilla, eliminado — unificado con el mismo catalogo
# Cargo que usa PersonalCuadrilla.rol_cuadrilla) a FK(Cargo,
# to_field='codigo').
#
# db_column='rol_cuadrilla' preserva el nombre y tipo fisico de la columna
# (varchar(20)) — es un AlterField (NO RemoveField+AddField), aditivo a
# nivel de constraint. Verificado contra prod (2026-07-10, solo lectura):
# 0 filas huerfanas en cuadrilla_miembros (1,108 filas totales, todas con
# codigo valido dentro del catalogo Cargo sembrado en 0019). Registro
# legacy de referencia: cuadrilla_miembros.id=89d24a85-55da-47dc-ae60-
# 77e9c367fe2e (rol_cuadrilla=SUPERVISOR, cargo=JT_CTA) debe conservar su
# codigo exacto tras esta migracion.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cuadrillas", "0020_personalcuadrilla_rol_cuadrilla_fk"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cuadrillamiembro",
            name="rol_cuadrilla",
            field=models.ForeignKey(
                db_column="rol_cuadrilla",
                default="LINIERO_I",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cuadrilla_miembros",
                to="cuadrillas.cargo",
                to_field="codigo",
                verbose_name="Rol en cuadrilla",
            ),
        ),
    ]
