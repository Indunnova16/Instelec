"""Instelec#171 (Sprint final, GRUPO A) — B5: modelo `ColumnaConfigurableValor`
(EAV) para columnas CUSTOM (`es_sistema=False`) agregadas por el cliente vía
la futura UI de administración (B6). Las 21 columnas "de fábrica"
(`es_sistema=True`) NO usan este modelo — su dato sigue viviendo en los
campos reales de `ObraCivilTorre`/`MontajeEstructuraTorre`/`TendidoTorre`
(decisión de diseño de B2).

Cubre también los helpers `ColumnaConfigurable.valor_para_torre()` /
`.set_valor_para_torre()` — el punto de integración que B3/B4 ya detectan
vía `getattr(columna, 'valor_para_torre', None)` (duck-typing, para que
avance_ponderado/avance_conductor/avance_fibra funcionen con columnas
custom sin necesitar cambios adicionales una vez B5 existe).

Convención de colección: `tests/unit/` (`pyproject.toml` → `testpaths =
["tests"]`).
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.construccion.models import (
    ColumnaConfigurable,
    ColumnaConfigurableValor,
    ObraCivilTorre,
    ProyectoConstruccion,
    TorreConstruccion,
)
from apps.contratos.models import Contrato


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B5-001',
        nombre='Proyecto test #171 B5 — ColumnaConfigurableValor',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto B5', estado='EJECUCION',
    )


@pytest.fixture
def torre(proyecto):
    return TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B5-1')


@pytest.fixture
def columna_custom_decimal(proyecto):
    """Columna custom DECIMAL — simula lo que B6 crearía vía UI."""
    return ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='pintura_extra', etiqueta='Pintura extra (custom)', orden=99,
        peso_pct=10, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL,
        es_sistema=False, activa=True,
    )


@pytest.fixture
def columna_custom_boolean(proyecto):
    return ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_TENDIDO_CONDUCTOR,
        clave='inspeccion_extra', etiqueta='Inspección extra (custom)', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN,
        es_sistema=False, activa=True,
    )


# ==============================================================================
# 1) get/set valor — decimal y boolean
# ==============================================================================

@pytest.mark.django_db
def test_set_valor_para_torre_decimal_crea_fila(columna_custom_decimal, torre):
    fila = columna_custom_decimal.set_valor_para_torre(torre, Decimal('0.75'))
    assert isinstance(fila, ColumnaConfigurableValor)
    assert fila.columna == columna_custom_decimal
    assert fila.torre == torre
    assert fila.valor_decimal == Decimal('0.75')
    assert fila.valor_boolean is None


@pytest.mark.django_db
def test_set_valor_para_torre_boolean_crea_fila(columna_custom_boolean, torre):
    fila = columna_custom_boolean.set_valor_para_torre(torre, True)
    assert fila.valor_boolean is True
    assert fila.valor_decimal is None


@pytest.mark.django_db
def test_valor_para_torre_decimal_devuelve_valor_guardado(columna_custom_decimal, torre):
    columna_custom_decimal.set_valor_para_torre(torre, Decimal('0.4'))
    assert columna_custom_decimal.valor_para_torre(torre) == Decimal('0.4')


@pytest.mark.django_db
def test_valor_para_torre_boolean_devuelve_valor_guardado(columna_custom_boolean, torre):
    columna_custom_boolean.set_valor_para_torre(torre, True)
    assert columna_custom_boolean.valor_para_torre(torre) is True
    columna_custom_boolean.set_valor_para_torre(torre, False)
    assert columna_custom_boolean.valor_para_torre(torre) is False


@pytest.mark.django_db
def test_set_valor_para_torre_es_idempotente_update_or_create(columna_custom_decimal, torre):
    """Llamar set_valor_para_torre 2 veces sobre la misma columna+torre
    actualiza la fila existente, no crea una segunda (unique_together)."""
    columna_custom_decimal.set_valor_para_torre(torre, Decimal('0.2'))
    columna_custom_decimal.set_valor_para_torre(torre, Decimal('0.9'))
    assert ColumnaConfigurableValor.objects.filter(
        columna=columna_custom_decimal, torre=torre,
    ).count() == 1
    assert columna_custom_decimal.valor_para_torre(torre) == Decimal('0.9')


# ==============================================================================
# 2) Default cuando NO existe fila todavía
# ==============================================================================

@pytest.mark.django_db
def test_valor_para_torre_decimal_default_cero_si_torre_nunca_toco_la_columna(
    columna_custom_decimal, torre,
):
    assert ColumnaConfigurableValor.objects.filter(
        columna=columna_custom_decimal, torre=torre,
    ).count() == 0
    assert columna_custom_decimal.valor_para_torre(torre) == Decimal('0')


@pytest.mark.django_db
def test_valor_para_torre_boolean_default_false_si_torre_nunca_toco_la_columna(
    columna_custom_boolean, torre,
):
    assert ColumnaConfigurableValor.objects.filter(
        columna=columna_custom_boolean, torre=torre,
    ).count() == 0
    assert columna_custom_boolean.valor_para_torre(torre) is False


@pytest.mark.django_db
def test_valor_para_torre_default_no_afecta_otras_torres(columna_custom_decimal, proyecto):
    """El default 0/False es por torre — una torre sin valor no debe leer
    (ni afectar) el valor de otra torre de la misma columna."""
    torre_a = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B5-A')
    torre_b = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B5-B')
    columna_custom_decimal.set_valor_para_torre(torre_a, Decimal('1.0'))

    assert columna_custom_decimal.valor_para_torre(torre_a) == Decimal('1.0')
    assert columna_custom_decimal.valor_para_torre(torre_b) == Decimal('0')


# ==============================================================================
# 3) unique_together columna+torre — constraint de BD
# ==============================================================================

@pytest.mark.django_db
def test_unique_together_columna_torre_constraint_bd(columna_custom_decimal, torre):
    ColumnaConfigurableValor.objects.create(
        columna=columna_custom_decimal, torre=torre, valor_decimal=Decimal('0.5'),
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ColumnaConfigurableValor.objects.create(
                columna=columna_custom_decimal, torre=torre, valor_decimal=Decimal('0.9'),
            )


@pytest.mark.django_db
def test_unique_together_permite_misma_torre_en_columnas_distintas(
    columna_custom_decimal, columna_custom_boolean, torre,
):
    """El unique_together es (columna, torre) — una torre SÍ puede tener
    valores en varias columnas custom distintas."""
    ColumnaConfigurableValor.objects.create(
        columna=columna_custom_decimal, torre=torre, valor_decimal=Decimal('0.5'),
    )
    ColumnaConfigurableValor.objects.create(
        columna=columna_custom_boolean, torre=torre, valor_boolean=True,
    )
    assert ColumnaConfigurableValor.objects.filter(torre=torre).count() == 2


# ==============================================================================
# 4) __str__ + integración con avance_ponderado (duck-typing B3)
# ==============================================================================

@pytest.mark.django_db
def test_str_incluye_etiqueta_y_torre(columna_custom_decimal, torre):
    columna_custom_decimal.set_valor_para_torre(torre, Decimal('0.5'))
    fila = ColumnaConfigurableValor.objects.get(columna=columna_custom_decimal, torre=torre)
    texto = str(fila)
    assert 'Pintura extra (custom)' in texto
    assert torre.numero_display in texto or torre.numero in texto


@pytest.mark.django_db
def test_columna_custom_activa_con_valor_participa_en_avance_ponderado(
    proyecto, columna_custom_decimal,
):
    """Integración con B3: una columna custom ACTIVA con un valor guardado
    debe sumar al SUMPRODUCT de avance_ponderado — prueba end-to-end de que
    el duck-typing `getattr(columna, 'valor_para_torre', None)` en
    ObraCivilTorre.avance_ponderado realmente engancha con B5."""
    torre_local = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B5-INTEG')
    oc = ObraCivilTorre.objects.create(proyecto=proyecto, torre=torre_local)  # todo en 0
    columna_custom_decimal.set_valor_para_torre(torre_local, Decimal('1.0'))

    # Pesos sistema (5/30/5/15/30/15=100) + columna custom peso=10 → total=110.
    # Único aporte: columna custom (peso 10, valor 1.0) → 10/110 = 9.09...%
    oc.refresh_from_db()
    assert oc.avance_ponderado_pct == pytest.approx(9.1, abs=0.05)
