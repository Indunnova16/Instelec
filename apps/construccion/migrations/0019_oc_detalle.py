"""B2a (#74) — Migration 0019: CreateModel ObraCivilTorreDetalle + seed legacy.

Crea la tabla `construccion_oc_detalle` con ~110 campos en 7 secciones y
siembra 4 detalles (uno por pata A/B/C/D) por cada ObraCivilTorre legacy
existente, propagando:
  - avance_cerramiento → cerr_finalizado_ok (boolean, >= 0.99)
  - avance_excavacion → exc_ejecutada_pct
  - avance_solado → sol_ejecutado_pct
  - avance_acero → ace_instalacion_pct
  - avance_vaciado → vac_ejecutado_pct
  - avance_compactacion → com_finalizada_pct

Adicionalmente, si existe `PataObra(torre, pata)` legacy se sobreescribe el
booleano `_ok` específico por pata con sus flags (`cerramiento_finalizado_ok`,
etc), para no perder la granularidad fine-grained existente del modelo #53.

Reversible: noop (la pérdida de datos es del CreateModel, ya gestionada por
Django).
"""
import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def seed_desde_legacy(apps, schema_editor):
    """Crea 4 ObraCivilTorreDetalle por cada ObraCivilTorre existente.

    Propaga los avances agregados de la torre a cada pata + sobrescribe los
    flags por pata desde PataObra cuando exista.
    """
    ObraCivilTorre = apps.get_model('construccion', 'ObraCivilTorre')
    ObraCivilTorreDetalle = apps.get_model('construccion', 'ObraCivilTorreDetalle')
    PataObra = apps.get_model('construccion', 'PataObra')

    for legacy in ObraCivilTorre.objects.select_related('torre', 'proyecto').all():
        avance_cerr = legacy.avance_cerramiento or Decimal('0')
        avance_exc = legacy.avance_excavacion or Decimal('0')
        avance_sol = legacy.avance_solado or Decimal('0')
        avance_ace = legacy.avance_acero or Decimal('0')
        avance_vac = legacy.avance_vaciado or Decimal('0')
        avance_com = legacy.avance_compactacion or Decimal('0')

        cerr_default = avance_cerr >= Decimal('0.99')

        for pata_letra in ['A', 'B', 'C', 'D']:
            patabra = PataObra.objects.filter(
                torre=legacy.torre, pata=pata_letra,
            ).first()

            # Defaults agregados a partir de ObraCivilTorre (cache)
            defaults = {
                'cerr_finalizado_ok': cerr_default,
                'exc_ejecutada_pct': avance_exc,
                'sol_ejecutado_pct': avance_sol,
                'ace_instalacion_pct': avance_ace,
                'vac_ejecutado_pct': avance_vac,
                'com_finalizada_pct': avance_com,
            }

            # Granularidad fine-grained de PataObra (#53) si existe
            if patabra is not None:
                defaults.update({
                    'cerr_finalizado_ok': bool(patabra.cerramiento_finalizado_ok),
                    'replanteo_topografico_ok': bool(patabra.replanteo_ok),
                    'exc_metros_m3': (
                        Decimal(str(patabra.excavacion_m3))
                        if patabra.excavacion_m3 is not None else None
                    ),
                    'ace_solicitado_kg': (
                        Decimal(str(patabra.acero_solicitado_kg))
                        if patabra.acero_solicitado_kg is not None else None
                    ),
                    'ace_instalado_kg': (
                        Decimal(str(patabra.acero_instalado_kg))
                        if patabra.acero_instalado_kg is not None else None
                    ),
                    'vac_fecha_vaciado': patabra.vaciado_fecha,
                })

            ObraCivilTorreDetalle.objects.create(
                proyecto=legacy.proyecto,
                torre=legacy.torre,
                pata=pata_letra,
                **defaults,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0018_merge_b1_b2_0017'),
    ]

    operations = [
        migrations.CreateModel(
            name='ObraCivilTorreDetalle',
            fields=[
                # BaseModel
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')),

                # Identidad
                ('pata', models.CharField(choices=[('A', 'Pata A'), ('B', 'Pata B'), ('C', 'Pata C'), ('D', 'Pata D')], max_length=1, verbose_name='Pata')),
                ('diseno_construido', models.CharField(blank=True, help_text='Código/tipo del diseño efectivamente construido por pata.', max_length=50, verbose_name='Diseño construido')),
                ('replanteo_topografico_ok', models.BooleanField(default=False, verbose_name='Replanteo topográfico OK')),

                # Cerramiento
                ('cerr_madera_un', models.PositiveIntegerField(blank=True, null=True, verbose_name='Cerramiento — madera (un)')),
                ('cerr_lona_m', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Cerramiento — lona (m)')),
                ('cerr_senalizacion_ok', models.BooleanField(default=False, verbose_name='Cerramiento — señalización OK')),
                ('cerr_notas', models.TextField(blank=True, verbose_name='Cerramiento — notas')),
                ('cerr_finalizado_ok', models.BooleanField(default=False, help_text='Equivalente al ok del bloque secuencial de PataObra (#53).', verbose_name='Cerramiento finalizado')),

                # Excavación
                ('exc_cuadrilla', models.CharField(blank=True, max_length=100, verbose_name='Excavación — cuadrilla')),
                ('exc_ft022_ok', models.BooleanField(default=False, verbose_name='FT-022 OK')),
                ('exc_ft929_ok', models.BooleanField(default=False, verbose_name='FT-929 OK')),
                ('exc_ft923_ok', models.BooleanField(default=False, verbose_name='FT-923 OK')),
                ('exc_ft924_ok', models.BooleanField(default=False, verbose_name='FT-924 OK')),
                ('exc_ft925_ok', models.BooleanField(default=False, verbose_name='FT-925 OK')),
                ('exc_ft926_ok', models.BooleanField(default=False, verbose_name='FT-926 OK')),
                ('exc_ft927_ok', models.BooleanField(default=False, verbose_name='FT-927 OK')),
                ('exc_ft928_ok', models.BooleanField(default=False, verbose_name='FT-928 OK')),
                ('exc_tipo', models.CharField(blank=True, choices=[('MANUAL', 'Manual'), ('MAQUINA', 'Con máquina'), ('HELICOIDAL', 'Helicoidal')], max_length=20, verbose_name='Tipo excavación')),
                ('exc_metros_m3', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Excavación (m3)')),
                ('exc_penetrometro_ok', models.BooleanField(default=False, verbose_name='Penetrómetro OK')),
                ('exc_monitoreo_arq', models.CharField(blank=True, choices=[('EJECUCION', 'En ejecución'), ('LIBERADA', 'Liberada')], max_length=20, verbose_name='Monitoreo arqueológico')),
                ('exc_ejecutada_pct', models.DecimalField(decimal_places=4, default=Decimal('0'), help_text='0–1 (peso 0.30 del avance ponderado por defecto).', max_digits=5, verbose_name='% Excavación ejecutada')),
                ('exc_observaciones', models.TextField(blank=True, verbose_name='Excavación — observaciones')),

                # Solado
                ('sol_ingreso_materiales', models.BooleanField(default=False, verbose_name='Solado — ingreso materiales OK')),
                ('sol_agua_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado agua (calc)')),
                ('sol_agua_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado agua (real)')),
                ('sol_agua_obs', models.CharField(blank=True, max_length=200, verbose_name='Solado agua (obs)')),
                ('sol_arena_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado arena (calc)')),
                ('sol_arena_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado arena (real)')),
                ('sol_arena_obs', models.CharField(blank=True, max_length=200, verbose_name='Solado arena (obs)')),
                ('sol_grava_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado grava (calc)')),
                ('sol_grava_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado grava (real)')),
                ('sol_grava_obs', models.CharField(blank=True, max_length=200, verbose_name='Solado grava (obs)')),
                ('sol_cemento_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado cemento (calc)')),
                ('sol_cemento_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Solado cemento (real)')),
                ('sol_cemento_obs', models.CharField(blank=True, max_length=200, verbose_name='Solado cemento (obs)')),
                ('sol_soldadura_prolongas_ok', models.BooleanField(default=False, verbose_name='Solado — soldadura prolongas OK')),
                ('sol_ejecutado_pct', models.DecimalField(decimal_places=4, default=Decimal('0'), help_text='0–1 (peso 0.05 por defecto).', max_digits=5, verbose_name='% Solado ejecutado')),
                ('sol_observaciones', models.TextField(blank=True, verbose_name='Solado — observaciones')),

                # Acero
                ('ace_ingreso', models.BooleanField(default=False, verbose_name='Acero — ingreso OK')),
                ('ace_ft028_ok', models.BooleanField(default=False, verbose_name='FT-028 OK')),
                ('ace_ft930_ok', models.BooleanField(default=False, verbose_name='FT-930 OK')),
                ('ace_corte_flejado_ok', models.BooleanField(default=False, verbose_name='Acero — corte/flejado OK')),
                ('ace_armado_sitio_ok', models.BooleanField(default=False, verbose_name='Acero — armado en sitio OK')),
                ('ace_spt_herramientas_ok', models.BooleanField(default=False, verbose_name='Acero — SPT herramientas OK')),
                ('ace_solicitado_kg', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Acero solicitado (kg)')),
                ('ace_instalado_kg', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Acero instalado (kg)')),
                ('ace_observaciones', models.TextField(blank=True, verbose_name='Acero — observaciones')),
                ('ace_instalacion_pct', models.DecimalField(decimal_places=4, default=Decimal('0'), help_text='0–1 (peso 0.10 por defecto).', max_digits=5, verbose_name='% Acero instalado')),
                ('ace_instalacion_obs', models.TextField(blank=True, verbose_name='Acero instalación — observaciones')),

                # Vaciado
                ('vac_ft916_ok', models.BooleanField(default=False, verbose_name='FT-916 OK')),
                ('vac_nivelacion_stub_ok', models.BooleanField(default=False, verbose_name='Vaciado — nivelación stub OK')),
                ('vac_encofrado_ok', models.BooleanField(default=False, verbose_name='Vaciado — encofrado OK')),
                ('vac_ingreso_materiales', models.BooleanField(default=False, verbose_name='Vaciado — ingreso materiales OK')),
                ('vac_it380_ok', models.BooleanField(default=False, verbose_name='IT-380 OK')),
                ('vac_ft056_ok', models.BooleanField(default=False, verbose_name='FT-056 OK')),
                ('vac_tipo_concreto', models.CharField(blank=True, choices=[('PREMEZCLADO', 'Premezclado'), ('OBRA', 'Hecho en obra')], max_length=20, verbose_name='Tipo de concreto')),
                ('vac_mpa_teorica', models.PositiveSmallIntegerField(blank=True, help_text='Resistencia esperada (ej. 21, 28).', null=True, verbose_name='MPa teórica')),
                ('vac_agua_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado agua (calc)')),
                ('vac_agua_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado agua (real)')),
                ('vac_agua_obs', models.CharField(blank=True, max_length=200, verbose_name='Vaciado agua (obs)')),
                ('vac_arena_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado arena (calc)')),
                ('vac_arena_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado arena (real)')),
                ('vac_arena_obs', models.CharField(blank=True, max_length=200, verbose_name='Vaciado arena (obs)')),
                ('vac_grava_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado grava (calc)')),
                ('vac_grava_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado grava (real)')),
                ('vac_grava_obs', models.CharField(blank=True, max_length=200, verbose_name='Vaciado grava (obs)')),
                ('vac_cemento_calc', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado cemento (calc)')),
                ('vac_cemento_real', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Vaciado cemento (real)')),
                ('vac_cemento_obs', models.CharField(blank=True, max_length=200, verbose_name='Vaciado cemento (obs)')),
                ('vac_slump_ok', models.BooleanField(default=False, verbose_name='Vaciado — slump OK')),
                ('vac_fecha_vaciado', models.DateField(blank=True, help_text='Trigger alarmas cilindros 7/14/21/51 días (#55).', null=True, verbose_name='Fecha vaciado')),
                ('vac_fecha_cilindros', models.DateField(blank=True, null=True, verbose_name='Fecha toma de cilindros')),
                ('vac_inspeccion_stub_ok', models.BooleanField(default=False, verbose_name='Vaciado — inspección stub OK')),
                ('vac_encargado_puntas', models.CharField(blank=True, max_length=100, verbose_name='Vaciado — encargado de puntas')),
                ('vac_desencofrado_ok', models.BooleanField(default=False, verbose_name='Vaciado — desencofrado OK')),
                ('vac_ejecutado_pct', models.DecimalField(decimal_places=4, default=Decimal('0'), help_text='0–1 (peso 0.30 por defecto).', max_digits=5, verbose_name='% Vaciado ejecutado')),
                ('vac_observaciones', models.TextField(blank=True, verbose_name='Vaciado — observaciones')),

                # Compactación
                ('com_ft914_ok', models.BooleanField(default=False, verbose_name='FT-914 OK')),
                ('com_suelo_natural_ok', models.BooleanField(default=False, verbose_name='Compactación — suelo natural OK')),
                ('com_suelo_cemento_ok', models.BooleanField(default=False, verbose_name='Compactación — suelo cemento OK')),
                ('com_suelo_prestamo_ok', models.BooleanField(default=False, verbose_name='Compactación — suelo préstamo OK')),
                ('com_volumen_m3', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Compactación — volumen (m3)')),
                ('com_finalizada_pct', models.DecimalField(decimal_places=4, default=Decimal('0'), help_text='0–1 (peso 0.15 por defecto).', max_digits=5, verbose_name='% Compactación finalizada')),
                ('com_observaciones', models.TextField(blank=True, verbose_name='Compactación — observaciones')),

                # Trailer
                ('ejecutado_por', models.CharField(blank=True, max_length=100, verbose_name='Ejecutado por')),
                ('comentario_general', models.TextField(blank=True, verbose_name='Comentario general')),

                # FKs
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='obra_civil_detalles', to='construccion.proyectoconstruccion', verbose_name='Proyecto')),
                ('torre', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='obra_civil_detalles', to='construccion.torreconstruccion', verbose_name='Torre')),
            ],
            options={
                'verbose_name': 'Obra Civil — Detalle por pata',
                'verbose_name_plural': 'Obra Civil — Detalle por pata',
                'db_table': 'construccion_oc_detalle',
                'ordering': ['torre__numero', 'pata'],
                'unique_together': {('torre', 'pata')},
            },
        ),
        migrations.RunPython(seed_desde_legacy, reverse_code=migrations.RunPython.noop),
    ]
