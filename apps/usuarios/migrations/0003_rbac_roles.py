from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0002_usuario_salario_mensual'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='rol',
            field=models.CharField(
                choices=[
                    ('admin_general', 'Administrador General'),
                    ('coordinador_general', 'Coordinador General'),
                    ('admin_mantenimiento', 'Administrador de Mantenimiento'),
                    ('admin_construccion', 'Administrador de Construcción'),
                    ('operario_mantenimiento', 'Operario de Mantenimiento'),
                    ('operario_construccion', 'Operario de Construcción'),
                    ('operario_general', 'Operario General'),
                    ('admin', 'Administrador (legacy)'),
                    ('director', 'Director de Proyecto (legacy)'),
                    ('coordinador', 'Coordinador (legacy)'),
                    ('ing_residente', 'Ingeniero Residente (legacy)'),
                    ('ing_ambiental', 'Ingeniero Ambiental (legacy)'),
                    ('supervisor', 'Supervisor de Cuadrilla (legacy)'),
                    ('liniero', 'Liniero (legacy)'),
                    ('auxiliar', 'Auxiliar (legacy)'),
                ],
                default='operario_general',
                max_length=30,
                verbose_name='Rol',
            ),
        ),
    ]
