import uuid
from django.db import migrations, models
import django.db.models.deletion


CATEGORIAS_PDEO = [
    # (codigo, nombre, tipo, orden)
    ('INGRESOS_OPERACIONALES', 'Ingresos Operacionales', 'INGRESO', 10),
    ('SERVICIOS_PUBLICOS', 'Servicios Públicos', 'GASTO', 20),
    ('HIDRATACION', 'Hidratación', 'GASTO', 30),
    ('DOTACION', 'Dotación', 'GASTO', 40),
    ('ARRENDAMIENTO', 'Arrendamiento', 'GASTO', 50),
    ('GASTOS_VIAJE', 'Gastos de Viaje', 'GASTO', 60),
    ('FINANCIEROS', 'Financieros', 'GASTO', 70),
    ('VIGILANCIA', 'Vigilancia', 'GASTO', 80),
    ('PRESTACIONES_SOCIALES', 'Prestaciones Sociales', 'GASTO', 90),
    ('APORTES_PARAFISCALES', 'Aportes Parafiscales', 'GASTO', 100),
    ('SUBCONTRATISTAS', 'Subcontratistas', 'GASTO', 110),
    ('ALIMENTACION', 'Alimentación', 'GASTO', 120),
    ('CIF', 'CIF (Costos Indirectos de Fabricación)', 'GASTO', 130),
    ('MATERIALES', 'Materiales', 'GASTO', 140),
    ('ADMINISTRATIVOS', 'Administrativos', 'GASTO', 150),
    ('TRANSPORTE', 'Transporte', 'GASTO', 160),
    ('GASTOS_PERSONAL', 'Gastos de Personal', 'GASTO', 170),
    ('INTERESES', 'Intereses', 'GASTO', 180),
    ('LEASING', 'Leasing', 'GASTO', 190),
    ('OTROS_INGRESOS', 'Otros Ingresos', 'INGRESO', 200),
]


def seed_categorias(apps, schema_editor):
    Categoria = apps.get_model('construccion', 'CategoriaFinanciera')
    import uuid as uuid_module
    for codigo, nombre, tipo, orden in CATEGORIAS_PDEO:
        Categoria.objects.update_or_create(
            codigo=codigo,
            defaults={
                'id': uuid_module.uuid4(),
                'nombre': nombre,
                'tipo': tipo,
                'orden': orden,
                'activa': True,
            }
        )


def reverse_seed(apps, schema_editor):
    Categoria = apps.get_model('construccion', 'CategoriaFinanciera')
    Categoria.objects.filter(
        codigo__in=[c[0] for c in CATEGORIAS_PDEO]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0003_rbac_roles'),
        ('construccion', '0006_programacion_fase'),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoriaFinanciera',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('codigo', models.CharField(help_text='Slug interno, ej: SUBCONTRATISTAS, GASTOS_VIAJE', max_length=30, unique=True, verbose_name='Código')),
                ('nombre', models.CharField(max_length=100, verbose_name='Nombre')),
                ('tipo', models.CharField(choices=[('INGRESO', 'Ingreso'), ('GASTO', 'Gasto'), ('CALCULADO', 'Calculado (totales)')], default='GASTO', max_length=15, verbose_name='Tipo')),
                ('orden', models.PositiveSmallIntegerField(default=0, verbose_name='Orden')),
                ('activa', models.BooleanField(default=True, verbose_name='Activa')),
            ],
            options={
                'verbose_name': 'Categoría Financiera',
                'verbose_name_plural': 'Categorías Financieras',
                'db_table': 'construccion_categoria_financiera',
                'ordering': ['orden', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='PeriodoFinanciero',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('anio', models.PositiveSmallIntegerField(verbose_name='Año')),
                ('mes', models.PositiveSmallIntegerField(verbose_name='Mes')),
                ('cerrado', models.BooleanField(default=False, help_text='Si está cerrado, no se aceptan nuevos movimientos REAL', verbose_name='Período cerrado')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='periodos_financieros', to='construccion.proyectoconstruccion')),
            ],
            options={
                'verbose_name': 'Período Financiero',
                'verbose_name_plural': 'Períodos Financieros',
                'db_table': 'construccion_periodo_financiero',
                'ordering': ['proyecto', 'anio', 'mes'],
                'unique_together': {('proyecto', 'anio', 'mes')},
            },
        ),
        migrations.CreateModel(
            name='MovimientoFinanciero',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[('PRESUPUESTO', 'Presupuesto'), ('REAL', 'Real')], max_length=15, verbose_name='Tipo')),
                ('valor', models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name='Valor (COP)')),
                ('fecha_registro', models.DateTimeField(auto_now_add=True, verbose_name='Fecha registro')),
                ('notas', models.TextField(blank=True, verbose_name='Notas')),
                ('categoria', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='movimientos', to='construccion.categoriafinanciera')),
                ('periodo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='movimientos', to='construccion.periodofinanciero')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movimientos_financieros', to='usuarios.usuario')),
            ],
            options={
                'verbose_name': 'Movimiento Financiero',
                'verbose_name_plural': 'Movimientos Financieros',
                'db_table': 'construccion_movimiento_financiero',
                'ordering': ['periodo', 'categoria__orden'],
                'unique_together': {('periodo', 'categoria', 'tipo')},
            },
        ),
        migrations.RunPython(seed_categorias, reverse_seed),
    ]
