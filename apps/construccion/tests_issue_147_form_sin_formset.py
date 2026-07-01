"""Test #147 Sprint A2 — FaseTorreTendidoForm + TendidoTorreView sin formset.

Nota: el template tendido_torre.html todavía referencia `tiros_formset` en
este punto de la cadena (A3 lo reescribe a continuación) — por eso estos
tests son de FORM/VIEW en aislamiento (no GET/POST end-to-end contra la URL,
eso lo cubre A3+ una vez el template ya no depende del formset).
"""
import inspect

import pytest

from apps.construccion.forms import FaseTorreTendidoForm
from apps.construccion.views import TendidoTorreView


def test_form_incluye_numero_tiro_y_ft931_ok():
    assert 'numero_tiro' in FaseTorreTendidoForm.Meta.fields
    assert 'ft931_ok' in FaseTorreTendidoForm.Meta.fields


def test_view_ya_no_referencia_riega_manila_tiro_formset():
    """form_valid/get_context_data ya no deben mencionar el formset viejo."""
    fuente_form_valid = inspect.getsource(TendidoTorreView.form_valid)
    fuente_context = inspect.getsource(TendidoTorreView.get_context_data)
    for fuente in (fuente_form_valid, fuente_context):
        assert 'RiegaManilaTiroFormSet' not in fuente
        assert 'tiros_formset' not in fuente


def test_views_module_no_importa_riega_manila_tiro_formset():
    import apps.construccion.views as views_mod

    assert not hasattr(views_mod, 'RiegaManilaTiroFormSet')


@pytest.mark.django_db
def test_fasetorre_form_valid_guarda_numero_tiro_y_ft931(db):
    """Instanciar el form directo (sin la vista/template) y confirmar que
    numero_tiro + ft931_ok se guardan en la instancia."""
    from apps.construccion.models import (
        FaseTorre,
        ProyectoConstruccion,
        TorreConstruccion,
    )
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I147-A2',
        nombre='Contrato test #147 A2',
        cliente='Cliente #147',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto A2', estado='EJECUCION',
    )
    torre = TorreConstruccion.objects.create(proyecto=proyecto, numero='9', tipo='D6')
    fase = FaseTorre.objects.create(torre=torre, proyecto=proyecto)

    form = FaseTorreTendidoForm(
        data={'numero_tiro': '4', 'ft931_ok': 'on', 'circuito_2_aplica': 'on'},
        instance=fase,
    )
    assert form.is_valid(), form.errors
    guardada = form.save()
    assert guardada.numero_tiro == 4
    assert guardada.ft931_ok is True
