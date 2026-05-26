"""Migration de merge — bundle indicadores_construccion_sub_run_a.

B1 (#96, ActividadFinalTorre) y B2 (#98, IndicadoresConstruccion) generaron
migrations independientes con el mismo número 0017 apuntando al mismo padre
(0016_dashboard_curva_s). Cuando se mergean en main, Django ve dos leaf nodes
y aborta con CommandError: 'Conflicting migrations detected; multiple leaf
nodes in the migration graph'.

Este archivo es la merge migration: tiene ambas migrations como dependencies
y operations vacío. Django la usa como nodo único de convergencia.

Refs: #96 #98 (regresión detectada por el job instelec-migrate al deployar #109)
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0017_b1_actividad_final_torre'),
        ('construccion', '0017_b2_indicadores_construccion'),
    ]

    operations = []
