from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0003_obra_civil_mvp'),
    ]

    operations = [
        # ============ #56 Montaje ============
        migrations.AddField(
            model_name='fasetorre',
            name='funcion_torre',
            field=models.CharField(
                blank=True,
                choices=[('RETENCION', 'Retención'), ('AMARRE', 'Amarre'),
                         ('SUSPENSION', 'Suspensión')],
                max_length=15, verbose_name='Función de la torre'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tipo_torre_montaje',
            field=models.CharField(blank=True, max_length=30,
                                   verbose_name='Tipo de torre (nomenclatura proyecto)'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='cuerpo_torre',
            field=models.CharField(blank=True, max_length=30,
                                   verbose_name='Cuerpo / tramo de cuerpo'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='fecha_recepcion_patio',
            field=models.DateField(blank=True, null=True,
                                   verbose_name='Fecha recepción en patio'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='recibida_satisfaccion_ok',
            field=models.BooleanField(
                default=False, verbose_name='Recibida a satisfacción (sin pendientes)'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='pct_completitud_estructura',
            field=models.PositiveSmallIntegerField(
                default=100, help_text='100 si llegó completa; <100 si faltan piezas',
                verbose_name='% completitud estructura recibida'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='observaciones_recepcion',
            field=models.TextField(blank=True,
                                   verbose_name='Observaciones piezas pendientes'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='prearmado_fecha_inicio',
            field=models.DateField(blank=True, null=True,
                                   verbose_name='Fecha inicio prearmado'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='prearmado_fecha_fin',
            field=models.DateField(blank=True, null=True,
                                   verbose_name='Fecha fin prearmado'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='prearmado_pct',
            field=models.PositiveSmallIntegerField(default=0,
                                                   verbose_name='% avance prearmado'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='entrega_carga_ok',
            field=models.BooleanField(
                default=False,
                help_text='Habilita inicio del módulo Tendido para esta torre',
                verbose_name='Entrega para carga'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='entrega_carga_fecha',
            field=models.DateField(blank=True, null=True,
                                   verbose_name='Fecha entrega para carga'),
        ),
        # ============ #57 SPT ============
        migrations.AddField(
            model_name='fasetorre',
            name='spt_cantidad_excavacion_m',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='SPT — Cantidad excavación (m)'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_cable_planos_m',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='SPT — Cable según planos (m)'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_cable_instalado_m',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='SPT — Cable instalado (m)'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_polvora_tiros_planos',
            field=models.PositiveIntegerField(
                blank=True, help_text='Ej: 145 tiros por torre', null=True,
                verbose_name='SPT — Pólvora: tiros según planos'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_polvora_tiros_por_caja',
            field=models.PositiveSmallIntegerField(
                default=100, help_text='Para calcular cajas teóricas',
                verbose_name='Tiros por caja de pólvora'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_polvora_consumida_cajas',
            field=models.FloatField(
                blank=True, null=True,
                verbose_name='SPT — Pólvora real consumida (cajas)'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_observaciones',
            field=models.TextField(blank=True, verbose_name='SPT — Observaciones'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_ft068_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='FT-068 Control compensación'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_ft029_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='FT-029 Lectura medición PT'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_informe_mediciones_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Informe mediciones entregado'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='spt_pct',
            field=models.PositiveSmallIntegerField(default=0,
                                                   verbose_name='% Avance SPT'),
        ),
        # ============ #57 Pintura ============
        migrations.AddField(
            model_name='fasetorre',
            name='pintura_ft912_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='FT-912 Control espesor pintura patas'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='pintura_observaciones',
            field=models.TextField(blank=True, verbose_name='Pintura — Observaciones'),
        ),
        # ============ #58 Tendido ============
        migrations.AddField(
            model_name='fasetorre',
            name='riega_manila_ok',
            field=models.BooleanField(default=False, verbose_name='Riega de manila'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='riega_guaya_ok',
            field=models.BooleanField(default=False, verbose_name='Riega de guaya'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='ft046_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='FT-046 Control riega y tendido'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='ft047_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='FT-047 Control empalmes y terminales'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='ft932_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='FT-932 Control regulación conductor'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='regulacion_flechado_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Regulación y flechado conductor'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='ft918_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='FT-918 Tabla cruces post-tendido'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='grapado_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Grapado / amarre final'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='accesorios_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Accesorios instalados (puentes, palizas)'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='placas_senalizacion_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Placas de señalización'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='distancia_vano_adelante_m',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='Distancia vano adelante (m)'),
        ),
        # Circuito 2 — 3 fases
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_conductor_c2_a_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Tendido conductor Circuito 2 Fase A'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_conductor_c2_a_fecha',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_conductor_c2_b_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Tendido conductor Circuito 2 Fase B'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_conductor_c2_b_fecha',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_conductor_c2_c_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Tendido conductor Circuito 2 Fase C'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_conductor_c2_c_fecha',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_guarda_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Tendido cable de guarda'),
        ),
        migrations.AddField(
            model_name='fasetorre',
            name='tendido_guarda_fecha',
            field=models.DateField(blank=True, null=True),
        ),
    ]
