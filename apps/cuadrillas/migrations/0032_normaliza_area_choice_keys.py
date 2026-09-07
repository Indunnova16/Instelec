"""Normaliza PersonalCuadrilla.area a las choice-keys canónicas [issue #225].

La migración 0031 (issue #237, reemplazo del catálogo) escribió las etiquetas
de display ("Construcción", "Mantenimiento") en vez de las choice-keys de
apps.core.permissions.AREA_CHOICES ("CONSTRUCCION", "MANTENIMIENTO"). Todo
código que filtra por la choice-key (services_psc_disponibilidad.py de #225,
views_psc_asignacion.py, views_psc_programacion.py) no encontraba ningún
colaborador real: 161 filas "Construcción" + 59 "Mantenimiento" quedaban
fuera de cualquier query `area='CONSTRUCCION'`.
"""
from django.db import migrations


MAPEO = {
    'Construcción': 'CONSTRUCCION',
    'Mantenimiento': 'MANTENIMIENTO',
    'Financiero': 'FINANCIERO',
}


def normalizar_hacia_adelante(apps, schema_editor):
    PersonalCuadrilla = apps.get_model('cuadrillas', 'PersonalCuadrilla')
    for etiqueta, clave in MAPEO.items():
        PersonalCuadrilla.objects.filter(area=etiqueta).update(area=clave)


def normalizar_hacia_atras(apps, schema_editor):
    PersonalCuadrilla = apps.get_model('cuadrillas', 'PersonalCuadrilla')
    for etiqueta, clave in MAPEO.items():
        PersonalCuadrilla.objects.filter(area=clave).update(area=etiqueta)


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0031_issue_237_reemplazo_catalogo_colaboradores'),
    ]

    operations = [
        migrations.RunPython(normalizar_hacia_adelante, normalizar_hacia_atras),
    ]
