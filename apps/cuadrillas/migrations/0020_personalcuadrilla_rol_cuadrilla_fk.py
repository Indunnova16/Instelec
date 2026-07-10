# Issue #176 (A3): PersonalCuadrilla.rol_cuadrilla de CharField+choices
# (TextChoices RolCuadrilla, eliminado) a FK(Cargo, to_field='codigo').
#
# db_column='rol_cuadrilla' preserva el nombre y tipo fisico de la columna
# (varchar(20)) — es un AlterField (NO RemoveField+AddField), aditivo a
# nivel de constraint. Verificado contra prod (2026-07-10, solo lectura):
# 0 filas huerfanas en personal_cuadrilla (2 filas totales, ambas con
# codigo valido dentro del catalogo Cargo sembrado en 0019).
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cuadrillas", "0019_seed_cargos"),
    ]

    operations = [
        migrations.AlterField(
            model_name="personalcuadrilla",
            name="rol_cuadrilla",
            field=models.ForeignKey(
                db_column="rol_cuadrilla",
                default="LINIERO_I",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="personal_cuadrilla",
                to="cuadrillas.cargo",
                to_field="codigo",
                verbose_name="Cargo / Rol",
            ),
        ),
    ]
