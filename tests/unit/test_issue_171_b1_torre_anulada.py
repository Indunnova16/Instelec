"""Instelec#171 (Sprint final, GRUPO A) — B1: V3 estado "Anulada".

`TorreConstruccion.anulada` — BooleanField nuevo, ADITIVO y separado de
`aplica` (default False, puramente informativo). NO altera `aplica` ni
`avance_ponderado`/`avance_conductor`/`avance_fibra` — ver diseño en
PLAN_2026-07-19_171_sprint_final.md sección B1.

Convención de colección: `tests/unit/test_issue_171_*.py` (NO
`apps/construccion/tests_issue_171.py`, que existe pero NO colecta en CI —
ver `tests/unit/test_issue_185.py` para el hallazgo original).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.construccion.models import (
    ObraCivilTorre,
    ProyectoConstruccion,
    TorreConstruccion,
)
from apps.contratos.models import Contrato


@pytest.fixture
def proyecto_construccion(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B1-001',
        nombre='Proyecto test #171 B1 anulada',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto test #171 B1',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_legacy(proyecto_construccion):
    """Torre pre-existente (dato legacy), anulada=False por default — usada
    para probar edición sobre un registro que ya existía antes del fix."""
    return TorreConstruccion.objects.create(
        proyecto=proyecto_construccion,
        numero='T-1',
        tipo='D',
        anulada=False,
    )


# ==============================================================================
# 1) Modelo — default, aditivo, no afecta avance
# ==============================================================================

@pytest.mark.django_db
def test_torre_anulada_default_false(proyecto_construccion):
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='T-10')
    assert torre.anulada is False


@pytest.mark.django_db
def test_torre_anulada_no_afecta_aplica(proyecto_construccion):
    """Aditivo: marcar anulada=True NO cambia `aplica` (#149 ya tiene su
    propia semántica, con 5 rebotes previos por ambigüedad — no se pisa)."""
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='T-11', anulada=True,
    )
    assert torre.aplica is True
    assert torre.anulada is True


@pytest.mark.django_db
def test_torre_anulada_no_afecta_avance_ponderado(proyecto_construccion):
    """Aditivo: avance_ponderado de ObraCivilTorre sigue siendo
    SUMPRODUCT(pesos, avances) sin importar el valor de `anulada` — el
    campo es puramente informativo, no entra en ningún cálculo (#171 V3)."""
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='T-12', anulada=False,
    )
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_construccion, torre=torre,
        avance_cerramiento=Decimal('1.0000'), avance_excavacion=Decimal('1.0000'),
        avance_solado=Decimal('1.0000'), avance_acero=Decimal('1.0000'),
        avance_vaciado=Decimal('1.0000'), avance_compactacion=Decimal('1.0000'),
    )
    avance_antes = oc.avance_ponderado_pct

    torre.anulada = True
    torre.save()
    oc.refresh_from_db()

    assert oc.avance_ponderado_pct == avance_antes == 100.0


# ==============================================================================
# 2) Form — checkbox visible, crear/editar torre con anulada
# ==============================================================================

@pytest.mark.django_db
def test_torre_crear_get_muestra_checkbox_anulada(authenticated_client, proyecto_construccion):
    url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'name="anulada"' in resp.content


@pytest.mark.django_db
def test_torre_crear_post_con_anulada_true(authenticated_client, proyecto_construccion):
    url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.post(url, data={
        'numero': 'T-20',
        'tipo': 'D',
        'tipo_cimentacion': '',
        'anulada': 'on',
        'peso_kg': '',
        'tramo_tendido': '',
        'latitud': '', 'longitud': '',
        'cuadrilla_civil': '', 'cuadrilla_montaje': '', 'cuadrilla_tendido': '',
        'observaciones': '',
    })
    assert resp.status_code == 302
    torre = TorreConstruccion.objects.get(proyecto=proyecto_construccion, numero='T-20')
    assert torre.anulada is True
    assert torre.aplica is True  # aditivo — aplica no se toca


@pytest.mark.django_db
def test_torre_crear_post_sin_anulada_queda_false(authenticated_client, proyecto_construccion):
    """Checkbox sin marcar (ausente del POST, comportamiento HTML estándar de
    checkboxes) debe dejar anulada=False — default seguro."""
    url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.post(url, data={
        'numero': 'T-21',
        'tipo': 'D',
        'tipo_cimentacion': '',
        'peso_kg': '',
        'tramo_tendido': '',
        'latitud': '', 'longitud': '',
        'cuadrilla_civil': '', 'cuadrilla_montaje': '', 'cuadrilla_tendido': '',
        'observaciones': '',
    })
    assert resp.status_code == 302
    torre = TorreConstruccion.objects.get(proyecto=proyecto_construccion, numero='T-21')
    assert torre.anulada is False


@pytest.mark.django_db
def test_torre_editar_get_precarga_checkbox_anulada(authenticated_client, proyecto_construccion, torre_legacy):
    """Editar un registro LEGACY (creado antes del fix, anulada=False) — el
    checkbox debe estar presente y sin marcar."""
    url = reverse('construccion:torre_editar',
                   kwargs={'proyecto_id': proyecto_construccion.id, 'pk': torre_legacy.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'name="anulada"' in resp.content


@pytest.mark.django_db
def test_torre_editar_post_marca_anulada_sobre_torre_legacy(authenticated_client, proyecto_construccion, torre_legacy):
    """Editar una torre LEGACY (dato pre-existente al fix) y marcarla como
    anulada=True — regresión anti-shotgun-fix: el resto de campos del
    registro legacy no se pierde."""
    url = reverse('construccion:torre_editar',
                   kwargs={'proyecto_id': proyecto_construccion.id, 'pk': torre_legacy.id})
    resp = authenticated_client.post(url, data={
        'numero': torre_legacy.numero,
        'tipo': torre_legacy.tipo,
        'tipo_cimentacion': '',
        'anulada': 'on',
        'peso_kg': '',
        'tramo_tendido': '',
        'latitud': '', 'longitud': '',
        'cuadrilla_civil': '', 'cuadrilla_montaje': '', 'cuadrilla_tendido': '',
        'observaciones': '',
    })
    assert resp.status_code == 302
    torre_legacy.refresh_from_db()
    assert torre_legacy.anulada is True
    assert torre_legacy.numero == 'T-1'  # el resto del registro legacy intacto


# ==============================================================================
# 3) Badge visual en la matriz de Obra Civil (una de las 4 — patrón idéntico
#    en montaje_matriz.html/tendido_matriz.html/hochiminh_matriz.html)
# ==============================================================================

@pytest.mark.django_db
def test_obra_civil_matriz_muestra_badge_anulada_para_torre_anulada(authenticated_client, proyecto_construccion):
    torre_anulada = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='T-30', anulada=True,
    )
    torre_normal = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='T-31', anulada=False,
    )
    url = reverse('construccion:obra_civil_lista', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'ANULADA' in content
    # La torre normal no debe traer el badge asociado a ella.
    assert torre_anulada.numero_display in content
    assert torre_normal.numero_display in content
