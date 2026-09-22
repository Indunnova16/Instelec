"""Issue #271 Sprint A — A1: split de PersonalCuadrilla.fecha_ingreso en
fecha_firma_contrato + fecha_ingreso_proyecto (modelo + migración 0041).

Mismo patrón que tests/cuadrillas/test_issue_225_normaliza_area.py: la
función de backfill de la migración se ejercita importándola por módulo
(apps.cuadrillas.migrations.0041_split_fecha_ingreso) y corriéndola contra
fixtures reales -- este repo corre pytest con --nomigrations, así que la BD
de test se crea por syncdb desde el estado ACTUAL de los modelos.

Nota de alcance (desviación documentada del plan F2, ver notas_para_orquestador
del output de A1): el plan original de F2 pedía sacar `fecha_ingreso` del
MODEL STATE en esta misma migración vía SeparateDatabaseAndState. Verificado
empíricamente que hacerlo acá revienta 'manage.py check' completo
(ModelForm.Meta.fields de forms_personal.py se valida en import-time) y la
suite de tests que A2-A7 (despachados DESPUÉS de A1 en el mismo worktree)
todavía no actualizaron. Por eso A1 deja `fecha_ingreso` deprecado pero
PRESENTE en el model state -- la remoción real queda para un sub-item de
cierre posterior. Estos tests reflejan ese alcance real: NO se afirma que
`fecha_ingreso` sea inaccesible por ORM (todavía lo es, a propósito).
"""
from datetime import date
from importlib import import_module

import pytest
from django.apps import apps

pytestmark = pytest.mark.django_db


def _mod_migracion_0041():
    return import_module(
        'apps.cuadrillas.migrations.0041_split_fecha_ingreso'.replace('.py', '')
    )


def _crear_personal(documento, **kwargs):
    PersonalCuadrilla = apps.get_model('cuadrillas', 'PersonalCuadrilla')
    return PersonalCuadrilla.objects.create(
        nombre=f'QA_271_{documento}', documento=documento, **kwargs
    )


def test_backfill_puebla_fecha_firma_contrato_desde_legacy():
    """Colaborador con fecha_ingreso legacy poblada -> tras correr el backfill
    de la migración 0041, fecha_firma_contrato queda igual al valor legacy.
    fecha_ingreso_proyecto NO se backfillea (dato nuevo, sin fuente legacy)."""
    con_legado = _crear_personal('QA-271-A1-1', fecha_ingreso=date(2024, 3, 15))

    assert con_legado.fecha_firma_contrato is None
    assert con_legado.fecha_ingreso_proyecto is None

    mod = _mod_migracion_0041()
    mod.backfill_fecha_firma_contrato(apps, None)

    con_legado.refresh_from_db()
    assert con_legado.fecha_firma_contrato == date(2024, 3, 15)
    assert con_legado.fecha_ingreso_proyecto is None
    # El legacy no se borra ni se altera (columna física se conserva, #271 A1).
    assert con_legado.fecha_ingreso == date(2024, 3, 15)


def test_backfill_fixture_sin_fecha_ingreso_no_explota():
    """Colaborador SIN fecha_ingreso (null, caso legacy 61/224 en prod) ->
    fecha_firma_contrato queda NULL tras el backfill, no explota."""
    sin_legado = _crear_personal('QA-271-A1-2', fecha_ingreso=None)

    mod = _mod_migracion_0041()
    mod.backfill_fecha_firma_contrato(apps, None)

    sin_legado.refresh_from_db()
    assert sin_legado.fecha_firma_contrato is None
    assert sin_legado.fecha_ingreso_proyecto is None


def test_backfill_es_idempotente():
    """Correr el backfill 2 veces da el mismo resultado (no un error) --
    relevante porque el job de migración del pipeline puede reintentar."""
    persona = _crear_personal('QA-271-A1-3', fecha_ingreso=date(2023, 6, 1))

    mod = _mod_migracion_0041()
    mod.backfill_fecha_firma_contrato(apps, None)
    mod.backfill_fecha_firma_contrato(apps, None)

    persona.refresh_from_db()
    assert persona.fecha_firma_contrato == date(2023, 6, 1)


def test_campos_nuevos_son_opcionales_y_fecha_ingreso_sigue_accesible():
    """Los 2 campos nuevos son null=True/blank=True: un colaborador se puede
    crear sin ellos. fecha_ingreso (legacy, deprecado) SIGUE siendo accesible
    por ORM en este punto del sprint (A1) -- ver nota de alcance del docstring
    del módulo; su remoción real es un sub-item de cierre posterior a A2-A7."""
    persona = _crear_personal('QA-271-A1-4')

    assert persona.fecha_firma_contrato is None
    assert persona.fecha_ingreso_proyecto is None
    assert persona.fecha_ingreso is None  # legacy, deprecado, todavía presente

    persona.fecha_firma_contrato = date(2026, 1, 10)
    persona.fecha_ingreso_proyecto = date(2026, 2, 1)
    persona.save()
    persona.refresh_from_db()

    assert persona.fecha_firma_contrato == date(2026, 1, 10)
    assert persona.fecha_ingreso_proyecto == date(2026, 2, 1)
