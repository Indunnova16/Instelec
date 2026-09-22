# Issue #271 (A1): split de PersonalCuadrilla.fecha_ingreso en 2 campos
# operativos distintos -- fecha_firma_contrato (RRHH/legal) y
# fecha_ingreso_proyecto (disponibilidad para ser programado).
#
# Backfill: fecha_firma_contrato = fecha_ingreso legacy, SOLO para las filas
# que ya tenían dato (163/224 en prod, verificado por F2 2026-09-22 vía
# db_query.sh broker). fecha_ingreso_proyecto queda NULL -- es un dato nuevo,
# no hay fuente legacy de la que derivarlo.
#
# DESVIACIÓN DEL PLAN F2 (documentada, ver notas_para_orquestador de A1):
# el plan original pedía sacar fecha_ingreso del MODEL STATE en esta MISMA
# migración vía SeparateDatabaseAndState (state_operations=[RemoveField],
# database_operations=[]). Verificado empíricamente que hacerlo ACÁ, antes de
# que A2-A7 actualicen sus consumidores (forms_personal.py,
# services_psc_disponibilidad.py, views_psc_aprobaciones.py, excel_psc.py,
# import/export de views.py y 5 archivos de test), rompe 'manage.py check'
# completo (ModelForm.Meta.fields se valida en import-time) -- no solo tests,
# la app entera. Se DEFIERE la remoción del model state a un sub-item de
# cierre posterior a A2-A7 (una vez que ningún consumidor activo referencie
# fecha_ingreso), pero el MECANISMO que pidió el plan (SeparateDatabaseAndState,
# sin dropear la columna física, mitigación del gotcha portafolio-wide
# "RemoveField en canary rompe la revisión viva") sigue siendo el que se debe
# usar en ESE sub-item de cierre. fecha_ingreso queda deprecado pero presente
# y sin uso nuevo desde A1 en adelante.
from django.db import migrations, models


def backfill_fecha_firma_contrato(apps, schema_editor):
    PersonalCuadrilla = apps.get_model('cuadrillas', 'PersonalCuadrilla')
    PersonalCuadrilla.objects.filter(fecha_ingreso__isnull=False).update(
        fecha_firma_contrato=models.F('fecha_ingreso')
    )


def revertir_backfill(apps, schema_editor):
    # No-op deliberado: revertir escribiría sobre fecha_ingreso (la columna
    # física sigue existiendo) con datos que pudieron cambiar desde el forward
    # (ej. alguien edito fecha_firma_contrato manualmente tras el split). El
    # legacy fecha_ingreso no se toca en ningún momento por esta migración, así
    # que no hay nada que reconciliar hacia atrás.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0040_ejecucion_semanal_torre'),
    ]

    operations = [
        migrations.AddField(
            model_name='personalcuadrilla',
            name='fecha_firma_contrato',
            field=models.DateField(
                blank=True,
                help_text=(
                    'Issue #271 (A1): split de la antigua "Fecha de ingreso" en 2 conceptos '
                    'operativos distintos -- ésta es la fecha de firma de contrato (RRHH/legal). '
                    'Backfill: poblada con el valor legacy de fecha_ingreso para los colaboradores '
                    'que ya la tenían (163/224 filas en prod, verificado 2026-09-22).'
                ),
                null=True,
                verbose_name='Fecha de Firma de Contrato',
            ),
        ),
        migrations.AddField(
            model_name='personalcuadrilla',
            name='fecha_ingreso_proyecto',
            field=models.DateField(
                blank=True,
                help_text=(
                    'Issue #271 (A1): split de la antigua "Fecha de ingreso" -- ésta es la fecha '
                    'operativa de disponibilidad para SER PROGRAMADO en el proyecto (usada por '
                    'personal_elegible() y por la validación de aprobaciones). NO se backfillea '
                    'automáticamente desde el legacy fecha_ingreso: es un dato nuevo que el '
                    'cliente diligencia colaborador por colaborador.'
                ),
                null=True,
                verbose_name='Fecha de Ingreso a Proyecto',
            ),
        ),
        migrations.RunPython(
            backfill_fecha_firma_contrato,
            revertir_backfill,
        ),
        migrations.AlterField(
            model_name='personalcuadrilla',
            name='fecha_ingreso',
            field=models.DateField(
                blank=True,
                help_text=(
                    'DEPRECADO (issue #271, A1): reemplazado por fecha_firma_contrato + '
                    'fecha_ingreso_proyecto. Se mantiene en el model state (NO se remueve '
                    'todavía vía SeparateDatabaseAndState) porque los consumidores de este '
                    'campo (forms_personal.py, services_psc_disponibilidad.py, '
                    'views_psc_aprobaciones.py, excel_psc.py, import/export de views.py y su '
                    'cobertura de tests) migran a los campos nuevos en A2-A7, despachados '
                    'DESPUÉS de A1 en el mismo worktree -- remover el campo ahora rompe '
                    "'manage.py check' completo (ModelForm.Meta.fields se valida en import) "
                    'y toda esa suite de tests, que es exactamente el trabajo que A2-A7 '
                    'todavía no hicieron. Cleanup real (RemoveField del model state, sin '
                    'dropear la columna física) queda para un sub-item de cierre una vez '
                    'que ningún consumidor activo referencie ya fecha_ingreso -- ver '
                    'notas_para_orquestador de A1.'
                ),
                null=True,
                verbose_name='Fecha de ingreso',
            ),
        ),
    ]
