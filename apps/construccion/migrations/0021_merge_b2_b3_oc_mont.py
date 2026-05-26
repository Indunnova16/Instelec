"""Merge migration anti multiple leaf nodes para B2a (0019) y B3a (0020)."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0019_oc_detalle'),
        ('construccion', '0020_mont_detalle'),
    ]

    operations = []
