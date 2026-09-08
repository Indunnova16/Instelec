"""
Models for financial management and billing.

This module is an importer that aggregates the financiero models split across
several files so that ``apps.financiero.models`` keeps exposing every model
(Django app loading, migrations, admin, etc. resolve them from here).

- ``models_base``: monolito legacy (CostoRecurso, Presupuesto, ...).
- ``models_finv2_mapeo``: mapeo contable v2 (B1 / #120 lo llena).
- ``models_finv2_carga``: carga financiera y homologación contable (S1 / #246, #247).
- ``models_finv2_facturas``: maestros y facturación de gastos/ingresos (S1 / #248, #249).
- ``models_finv2_tesoreria_base``: conciliación y caja proyectada (S1 / #250, #251).
"""

from .models_base import *  # noqa
from .models_finv2_mapeo import *  # noqa
from .models_finv2_carga import *  # noqa
from .models_finv2_facturas import *  # noqa
from .models_finv2_tesoreria_base import *  # noqa
