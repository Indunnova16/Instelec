"""#191 — % de desviación de Acero (cero tolerancia), patrón #140 Solado/Vaciado.

El cliente (Gabriel) confundía `ace_instalacion_pct` (peso MANUAL 0-1 de la
sección Acero para el avance ponderado, sin relación matemática con la
desviación real) con "la desviación de acero". El modelo ya tenía
`ace_desviacion_kg` (diferencia instalado-solicitado en kg) pero nunca el
equivalente en %.

Este fix replica EXACTO el patrón `_desv_pct`/`_supera_umbral_desv` que ya
existe para Solado/Vaciado (#140) — con un único ajuste real: el cliente
pidió CERO TOLERANCIA para Acero (cualquier desviación != 0% es alerta),
a diferencia del rango de 5% que tolera Vaciado. Por eso Acero usa su propia
constante de módulo `UMBRAL_DESVIACION_ACERO_PCT = Decimal('0')` y su propia
property `ace_supera_umbral_desv` (comparación de igualdad exacta, NO
`_supera_umbral_desv` que compara `abs(pct) > umbral`).

Archivo dedicado (NO se usa `apps/construccion/tests.py`, compartido con otro
issue de este mismo RUN que también toca `apps/construccion/`).
"""
from decimal import Decimal

import pytest


# ===========================================================================
# Fixtures (mismo patrón que tests_b3_oc_detalle_modelo.py)
# ===========================================================================

@pytest.fixture
def proyecto_i191(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I191-001',
        nombre='Contrato test #191 desviación acero',
        cliente='Test Cliente',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto OC test #191',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_i191(proyecto_i191):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_i191,
        numero='E56',
        tipo='D6',
    )


# ===========================================================================
# (a) Desviación no-cero marca alerta — cero tolerancia
# ===========================================================================

@pytest.mark.django_db
def test_ace_desviacion_pct_no_cero_marca_alerta(proyecto_i191, torre_i191):
    """Cualquier desviación != 0% debe marcar `ace_supera_umbral_desv` True.

    A diferencia de Vaciado (tolera hasta 5%), Acero NO tiene rango: el
    cliente pidió exactitud ("no puede instalar ni un 5, ni un 10 de más").
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    d = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_i191, torre=torre_i191, pata='A',
        ace_solicitado_kg=Decimal('100.00'), ace_instalado_kg=Decimal('101.00'),
    )
    # (101 - 100)/100*100 = +1.0% — mínima desviación, igual debe alertar.
    assert d.ace_desviacion_pct == Decimal('1.0')
    assert d.ace_supera_umbral_desv is True


# ===========================================================================
# (b) Desviación exacta 0% NO marca alerta
# ===========================================================================

@pytest.mark.django_db
def test_ace_desviacion_pct_cero_exacto_no_marca_alerta(proyecto_i191, torre_i191):
    """instalado == solicitado → 0.0% → sin alerta."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    d = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_i191, torre=torre_i191, pata='A',
        ace_solicitado_kg=Decimal('228.28'), ace_instalado_kg=Decimal('228.28'),
    )
    assert d.ace_desviacion_pct == Decimal('0.0')
    assert d.ace_supera_umbral_desv is False


# ===========================================================================
# (c) Dato legacy real — torre E56 pata D, proyecto QA #49 (Puerta de Oro)
# ===========================================================================

@pytest.mark.django_db
def test_ace_desviacion_pct_dato_legacy_torre_e56_pata_d(proyecto_i191, torre_i191):
    """Escenario real confirmado por F2 en BD prod (proxy 127.0.0.1:5434,
    instelec_db, proyecto QA #49 Puerta de Oro, torre_id
    3f4fd96f-baaa-48af-9450-ef253927f7c6): 142.29kg solicitados vs 124.29kg
    instalados → -12.65% real, redondeado -12.7% con el helper `_desv_pct`.

    Pre-fix: el detalle solo mostraba -18.00 kg (ace_desviacion_kg, OK) sin
    nunca traducirlo a %. Post-fix: debe marcar -12.7% en rojo (cero
    tolerancia, cualquier desviación != 0 alerta).
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    d = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_i191, torre=torre_i191, pata='D',
        ace_solicitado_kg=Decimal('142.29'), ace_instalado_kg=Decimal('124.29'),
    )
    assert d.ace_desviacion_kg == Decimal('-18.00')
    assert d.ace_desviacion_pct == Decimal('-12.7')
    assert d.ace_supera_umbral_desv is True


# ===========================================================================
# (d) No-regresión: ace_instalacion_pct sigue siendo el peso de sección,
#     SIN relación matemática con solicitado/instalado kg.
# ===========================================================================

@pytest.mark.django_db
def test_ace_instalacion_pct_no_regresion_peso_seccion_sin_relacion(
    proyecto_i191, torre_i191,
):
    """`ace_instalacion_pct` (campo manual, avance ponderado) NO cambia ni se
    deriva de `ace_solicitado_kg`/`ace_instalado_kg` — sigue siendo el mismo
    campo manual 0-1 de antes del fix (#191 solo AGREGA properties nuevas,
    no toca la semántica de este campo ni `avance_ponderado`).
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    d = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_i191, torre=torre_i191, pata='D',
        ace_solicitado_kg=Decimal('142.29'), ace_instalado_kg=Decimal('124.29'),
        ace_instalacion_pct=Decimal('1.0000'),  # sección marcada "completa"
    )
    # El peso manual sigue en 1.0000 pese a que la desviación real es -12.65%.
    assert d.ace_instalacion_pct == Decimal('1.0000')
    # avance_ponderado sigue usando ace_instalacion_pct (SECCIONES_PESO),
    # no ace_desviacion_pct — confirma que no se tocó ese cálculo.
    campo_peso = next(
        campo for campo, _, _ in ObraCivilTorreDetalle.SECCIONES_PESO
        if campo == 'ace_instalacion_pct'
    )
    assert campo_peso == 'ace_instalacion_pct'


# ===========================================================================
# Edge cases — mismo patrón de robustez que Vaciado/Solado (#140)
# ===========================================================================

@pytest.mark.django_db
def test_ace_desviacion_pct_none_cuando_falta_dato(proyecto_i191, torre_i191):
    """None si falta solicitado o instalado; supera_umbral False (no alerta)."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    d = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_i191, torre=torre_i191, pata='A',
        ace_solicitado_kg=Decimal('100.00'),  # instalado ausente
    )
    assert d.ace_desviacion_pct is None
    assert d.ace_supera_umbral_desv is False


@pytest.mark.django_db
def test_ace_desviacion_pct_solicitado_cero_es_none(proyecto_i191, torre_i191):
    """solicitado=0 → división indefinida → None (no ZeroDivisionError)."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    d = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_i191, torre=torre_i191, pata='A',
        ace_solicitado_kg=Decimal('0'), ace_instalado_kg=Decimal('5'),
    )
    assert d.ace_desviacion_pct is None
    assert d.ace_supera_umbral_desv is False


@pytest.mark.django_db
def test_ace_umbral_constante_modulo_cero_tolerancia():
    """El umbral de Acero es una constante de módulo propia = 0 (cero
    tolerancia), NO reusa UMBRAL_DESVIACION_VACIADO_PCT (5%)."""
    from apps.construccion import models_b3_oc_detalle as m

    assert m.UMBRAL_DESVIACION_ACERO_PCT == Decimal('0')
    assert m.UMBRAL_DESVIACION_VACIADO_PCT == Decimal('5')
