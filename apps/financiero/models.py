"""
Models for financial management and billing.

This module is an importer that aggregates the financiero models split across
several files so that ``apps.financiero.models`` keeps exposing every model
(Django app loading, migrations, admin, etc. resolve them from here).

- ``models_base``: monolito legacy (CostoRecurso, Presupuesto, ...).
- ``models_finv2_mapeo``: mapeo contable v2 (B1 / #120 lo llena).
"""
from .models_base import *  # noqa
from .models_finv2_mapeo import *  # noqa
