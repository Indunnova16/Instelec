"""Regresión: la migración 0032 normaliza area a las choice-keys [issue #225]."""
import pytest
from django.apps import apps

pytestmark = pytest.mark.django_db


def _crear_personal(documento, area):
    PersonalCuadrilla = apps.get_model('cuadrillas', 'PersonalCuadrilla')
    return PersonalCuadrilla.objects.create(
        nombre=f'QA_225_{documento}', documento=documento, area=area, activo=True,
    )


def test_normaliza_construccion_y_mantenimiento_legacy():
    from apps.construccion.services_psc_disponibilidad import personal_elegible

    legacy_construccion = _crear_personal('QA-225-NORM-1', 'Construcción')
    legacy_mantenimiento = _crear_personal('QA-225-NORM-2', 'Mantenimiento')

    from apps.cuadrillas.migrations import __path__ as _  # noqa: F401  (paquete existe)
    from django.db import migrations as _dj_migrations  # noqa: F401
    from importlib import import_module
    mod = import_module('apps.cuadrillas.migrations.0032_normaliza_area_choice_keys'.replace('.py', ''))
    from django.apps import apps as django_apps
    mod.normalizar_hacia_adelante(django_apps, None)

    legacy_construccion.refresh_from_db()
    legacy_mantenimiento.refresh_from_db()
    assert legacy_construccion.area == 'CONSTRUCCION'
    assert legacy_mantenimiento.area == 'MANTENIMIENTO'


def test_ya_normalizado_no_se_rompe():
    PersonalCuadrilla = apps.get_model('cuadrillas', 'PersonalCuadrilla')
    ya_ok = PersonalCuadrilla.objects.create(
        nombre='QA_225_ya_ok', documento='QA-225-NORM-3', area='CONSTRUCCION', activo=True,
    )
    from importlib import import_module
    mod = import_module('apps.cuadrillas.migrations.0032_normaliza_area_choice_keys'.replace('.py', ''))
    from django.apps import apps as django_apps
    mod.normalizar_hacia_adelante(django_apps, None)
    ya_ok.refresh_from_db()
    assert ya_ok.area == 'CONSTRUCCION'
