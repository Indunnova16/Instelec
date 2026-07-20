"""Instelec#171 (Sprint final, GRUPO A) — B8: `entrega.html` (matriz real) +
`EntregaTorreView` (detalle editable por torre).

Mismo patrón ya ejecutado y validado en Sprint A para `torre_form.html`:
reemplaza el placeholder "En Desarrollo" por una matriz real de solo-listado
(EntregaView.get_context_data ya construía `entregas`, sin cambio de
backend) + una vista de detalle nueva (`EntregaTorreView`) para editar TODOS
los campos de `EntregaElectromecanica` por torre.

Convención de colección: `tests/unit/test_issue_171_*.py` (ver
`tests/unit/test_issue_185.py` para el hallazgo de por qué
`apps/construccion/tests_issue_171.py` NO colecta).
"""
from datetime import date

import pytest
from django.urls import reverse

from apps.construccion.models import (
    EntregaElectromecanica,
    ProyectoConstruccion,
    TorreConstruccion,
)
from apps.contratos.models import Contrato


@pytest.fixture
def proyecto_construccion(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B8-001',
        nombre='Proyecto test #171 B8 entrega',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto test #171 B8',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_con_entrega(proyecto_construccion):
    """Torre + EntregaElectromecanica ya diligenciada — dato 'legacy' real
    (no un fixture vacío) para probar que la matriz y el detalle reflejan
    valores pre-existentes, no solo estado inicial."""
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='E1', tipo='D',
    )
    entrega = EntregaElectromecanica.objects.create(
        torre=torre,
        observacion_formato='Falta firma del residente',
        firmo_hmv=True,
        firmo_wsp=False,
        cajas_opgw=3,
        fecha_primera_visita=date(2026, 6, 1),
        avance=75,
        estado='PENDIENTE',
    )
    return torre, entrega


# ==============================================================================
# 1) Matriz — GET /entrega/, sin placeholder, lista torres reales
# ==============================================================================

@pytest.mark.django_db
def test_entrega_matriz_reemplaza_placeholder_en_desarrollo(authenticated_client, proyecto_construccion, torre_con_entrega):
    url = reverse('construccion:entrega', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'En Desarrollo' not in resp.content


@pytest.mark.django_db
def test_entrega_matriz_lista_torre_real_con_datos_legacy(authenticated_client, proyecto_construccion, torre_con_entrega):
    torre, entrega = torre_con_entrega
    url = reverse('construccion:entrega', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    content = resp.content.decode()
    assert torre.numero_display in content
    assert 'Pendiente' in content  # badge de estado
    assert '75' in content  # avance


@pytest.mark.django_db
def test_entrega_matriz_torre_link_a_detalle(authenticated_client, proyecto_construccion, torre_con_entrega):
    torre, entrega = torre_con_entrega
    url = reverse('construccion:entrega', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    detalle_url = reverse('construccion:entrega_torre',
                           kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id})
    assert detalle_url in resp.content.decode()


@pytest.mark.django_db
def test_entrega_matriz_vacia_sin_torres(authenticated_client, proyecto_construccion):
    """Proyecto sin torres todavía — la matriz no debe tronar, muestra
    estado vacío amable."""
    url = reverse('construccion:entrega', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'En Desarrollo' not in resp.content


# ==============================================================================
# 2) Detalle por torre — GET/POST, campos pre-poblados, guarda
# ==============================================================================

@pytest.mark.django_db
def test_entrega_torre_get_200_con_datos_precargados(authenticated_client, proyecto_construccion, torre_con_entrega):
    torre, entrega = torre_con_entrega
    url = reverse('construccion:entrega_torre',
                   kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'Falta firma del residente' in content
    assert torre.numero_display in content


@pytest.mark.django_db
def test_entrega_torre_get_crea_registro_si_no_existe(authenticated_client, proyecto_construccion):
    """Torre SIN EntregaElectromecanica todavía (torre legacy pre-wiring de
    TorreCreateView.form_valid) — get_or_create la crea sin tronar."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E2')
    assert not EntregaElectromecanica.objects.filter(torre=torre).exists()

    url = reverse('construccion:entrega_torre',
                   kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert EntregaElectromecanica.objects.filter(torre=torre).exists()


@pytest.mark.django_db
def test_entrega_torre_post_guarda_todos_los_campos(authenticated_client, proyecto_construccion, torre_con_entrega):
    torre, entrega = torre_con_entrega
    url = reverse('construccion:entrega_torre',
                   kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id})
    resp = authenticated_client.post(url, data={
        'observacion_formato': 'Corregido — firma recibida',
        'obs_spt': 'SPT OK',
        'obs_estructura': 'Estructura OK',
        'obs_conductor_a': 'Fase A OK',
        'obs_conductor_b': 'Fase B OK',
        'obs_conductor_c': 'Fase C OK',
        'obs_opgw_izq': 'OPGW izq OK',
        'obs_opgw_der': 'OPGW der OK',
        'firmo_hmv': 'on',
        'firmo_wsp': 'on',
        'cajas_opgw': '5',
        'fecha_primera_visita': '2026-06-01',
        'fecha_segunda_visita': '2026-06-15',
        'avance': '100',
        'estado': 'LIBERADA',
        'observaciones_adicionales': 'Entrega liberada sin pendientes',
    })
    assert resp.status_code == 302
    entrega.refresh_from_db()
    assert entrega.observacion_formato == 'Corregido — firma recibida'
    assert entrega.firmo_hmv is True
    assert entrega.firmo_wsp is True
    assert entrega.cajas_opgw == 5
    assert entrega.avance == 100
    assert entrega.estado == 'LIBERADA'
    assert entrega.fecha_segunda_visita == date(2026, 6, 15)


@pytest.mark.django_db
def test_entrega_torre_post_redirige_a_matriz(authenticated_client, proyecto_construccion, torre_con_entrega):
    torre, entrega = torre_con_entrega
    url = reverse('construccion:entrega_torre',
                   kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id})
    resp = authenticated_client.post(url, data={
        'observacion_formato': '', 'obs_spt': '', 'obs_estructura': '',
        'obs_conductor_a': '', 'obs_conductor_b': '', 'obs_conductor_c': '',
        'obs_opgw_izq': '', 'obs_opgw_der': '',
        'cajas_opgw': '', 'fecha_primera_visita': '', 'fecha_segunda_visita': '',
        'avance': '0', 'estado': '', 'observaciones_adicionales': '',
    })
    assert resp.status_code == 302
    assert resp.url == reverse('construccion:entrega', kwargs={'proyecto_id': proyecto_construccion.id})
