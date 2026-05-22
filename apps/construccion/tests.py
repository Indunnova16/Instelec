"""Tests para las UIs nuevas de Obra Civil, Montaje y Tendido (#53-#58)."""
import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    ProyectoConstruccion,
    TorreConstruccion,
    PataObra,
    FaseTorre,
)


@pytest.fixture
def proyecto_construccion(db):
    """Contrato + Proyecto de construcción listos para crear torres."""
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-OC-001',
        nombre='Proyecto test Obra Civil',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto test OC/Montaje/Tendido',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_legacy(proyecto_construccion):
    """Torre creada SIN PataObra/FaseTorre — simula dato legacy pre-migración.
    Las nuevas views deben auto-crearlas defensivamente."""
    return TorreConstruccion.objects.create(
        proyecto=proyecto_construccion,
        numero='T-LEGACY-01',
    )


@pytest.fixture
def torre_completa(proyecto_construccion):
    """Torre con sus 4 PataObra + FaseTorre ya creadas (flujo normal)."""
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion,
        numero='T-NEW-01',
    )
    for pata in ['A', 'B', 'C', 'D']:
        PataObra.objects.create(torre=torre, pata=pata)
    FaseTorre.objects.create(torre=torre, proyecto=proyecto_construccion)
    return torre


# ====== Obra Civil ======

@pytest.mark.django_db
def test_obra_civil_lista_renderiza_y_autocrea_relaciones(
    authenticated_client, proyecto_construccion, torre_legacy
):
    """Lista responde 200 y crea PataObra+FaseTorre defensivamente para legacy."""
    url = reverse('construccion:obra_civil_lista',
                  kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:300]
    assert b'Obra civil' in resp.content
    assert b'T-LEGACY-01' in resp.content
    assert torre_legacy.pata_obra.count() == 4
    torre_legacy.refresh_from_db()
    assert FaseTorre.objects.filter(torre=torre_legacy).exists()


@pytest.mark.django_db
def test_obra_civil_torre_render_4_patas(
    authenticated_client, proyecto_construccion, torre_completa
):
    """Vista por torre muestra las 4 patas como tabs + 6 bloques."""
    url = reverse('construccion:obra_civil_torre',
                  kwargs={'proyecto_id': proyecto_construccion.id,
                          'torre_id': torre_completa.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    for letra in ['Pata A', 'Pata B', 'Pata C', 'Pata D']:
        assert letra in body
    for bloque in ['Cerramiento', 'Excavación', 'Solado',
                   'Acero', 'Vaciado', 'compactación']:
        assert bloque in body


@pytest.mark.django_db
def test_obra_civil_guardar_bloque_cerramiento(
    authenticated_client, proyecto_construccion, torre_completa
):
    """POST guarda los campos del bloque Cerramiento de la pata A."""
    url = reverse('construccion:obra_civil_torre',
                  kwargs={'proyecto_id': proyecto_construccion.id,
                          'torre_id': torre_completa.id})
    data = {
        'pata': 'A',
        'pata_A-cerramiento_finalizado_ok': 'on',
        'pata_A-cerramiento_fecha': '2026-05-20',
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code == 302
    pata_a = torre_completa.pata_obra.get(pata='A')
    assert pata_a.cerramiento_finalizado_ok is True
    assert str(pata_a.cerramiento_fecha) == '2026-05-20'


@pytest.mark.django_db
def test_obra_civil_alerta_materiales_acero(
    authenticated_client, proyecto_construccion, torre_completa
):
    """Si desviación de acero ≥5%, la fila lleva la clase bg-red-50."""
    pata = torre_completa.pata_obra.get(pata='B')
    pata.acero_solicitado_kg = 1000
    pata.acero_instalado_kg = 1100
    pata.save()
    assert pata.alarma_materiales is True

    url = reverse('construccion:obra_civil_lista',
                  kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'bg-red-50' in resp.content


# ====== Montaje ======

@pytest.mark.django_db
def test_montaje_lista_renderiza(
    authenticated_client, proyecto_construccion, torre_completa
):
    url = reverse('construccion:montaje_lista',
                  kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'Montaje' in resp.content
    assert b'T-NEW-01' in resp.content


@pytest.mark.django_db
def test_montaje_torre_guarda_entrega_carga_habilita_tendido(
    authenticated_client, proyecto_construccion, torre_completa
):
    """Marcar entrega_carga_ok habilita el módulo Tendido (gate #58)."""
    fase = torre_completa.fase
    assert fase.puede_iniciar_tendido is False

    url = reverse('construccion:montaje_torre',
                  kwargs={'proyecto_id': proyecto_construccion.id,
                          'torre_id': torre_completa.id})
    data = {
        'entrega_carga_ok': 'on',
        'entrega_carga_fecha': '2026-05-21',
        'pct_montaje': '80',
        'pct_completitud_estructura': '100',
        'prearmado_pct': '50',
        'spt_pct': '0',
        'spt_polvora_tiros_por_caja': '100',
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code == 302
    fase.refresh_from_db()
    assert fase.entrega_carga_ok is True
    assert fase.puede_iniciar_tendido is True


# ====== Tendido ======

@pytest.mark.django_db
def test_tendido_lista_renderiza(
    authenticated_client, proyecto_construccion, torre_completa
):
    url = reverse('construccion:tendido_lista',
                  kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'Tendido' in resp.content


@pytest.mark.django_db
def test_tendido_torre_muestra_aviso_si_bloqueada(
    authenticated_client, proyecto_construccion, torre_completa
):
    """Si entrega_carga_ok=False, la vista detalle muestra aviso de bloqueo."""
    fase = torre_completa.fase
    assert fase.entrega_carga_ok is False

    url = reverse('construccion:tendido_torre',
                  kwargs={'proyecto_id': proyecto_construccion.id,
                          'torre_id': torre_completa.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'no tiene marcada' in body or 'Entrega para carga' in body


@pytest.mark.django_db
def test_tendido_torre_guarda_3_fases_circuito_1(
    authenticated_client, proyecto_construccion, torre_completa
):
    """POST guarda los 3 OK del circuito 1 (Fase A/B/C)."""
    fase = torre_completa.fase
    fase.entrega_carga_ok = True
    fase.save()

    url = reverse('construccion:tendido_torre',
                  kwargs={'proyecto_id': proyecto_construccion.id,
                          'torre_id': torre_completa.id})
    data = {
        'tendido_conductor_a_ok': 'on',
        'tendido_conductor_a_fecha': '2026-05-22',
        'tendido_conductor_b_ok': 'on',
        'tendido_conductor_b_fecha': '2026-05-22',
        'tendido_conductor_c_ok': 'on',
        'tendido_conductor_c_fecha': '2026-05-22',
        'pct_tendido': '40',
        'pct_facturacion': '0',
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code == 302
    fase.refresh_from_db()
    assert fase.tendido_conductor_a_ok is True
    assert fase.tendido_conductor_b_ok is True
    assert fase.tendido_conductor_c_ok is True
    assert fase.pct_tendido == 40


# ====== Sociopredial (#51) ======

from apps.construccion.models import SocialPredial, AmbientalTorre


@pytest.mark.django_db
def test_sociopredial_lista_autocrea_relaciones(
    authenticated_client, proyecto_construccion, torre_legacy
):
    """Lista responde 200 y crea SocialPredial defensivamente para torre legacy."""
    url = reverse('construccion:social_predial',
                  kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:300]
    body = resp.content.decode()
    assert 'Sociopredial' in body
    assert 'T-LEGACY-01' in body
    assert SocialPredial.objects.filter(torre=torre_legacy).exists()


@pytest.mark.django_db
def test_sociopredial_semaforo_verde_con_4_actas(
    authenticated_client, proyecto_construccion, torre_completa
):
    """Las 4 actas con fecha → semáforo VERDE (regla Ana Sofía)."""
    from datetime import date
    social, _ = SocialPredial.objects.get_or_create(torre=torre_completa)
    assert social.semaforo == 'ROJO'

    url = reverse('construccion:social_predial_torre',
                  kwargs={'proyecto_id': proyecto_construccion.id,
                          'torre_id': torre_completa.id})
    data = {
        'acta_vecindad_fecha': '2026-04-01',
        'acta_acceso_comunitario_fecha': '2026-04-02',
        'autorizacion_propietario_fecha': '2026-04-03',
        'acta_acceso_privado_fecha': '2026-04-04',
        'propietario': 'Juan Pérez',
        'predio': 'Finca La Esperanza',
        'municipio': 'Manizales',
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code == 302
    social.refresh_from_db()
    assert social.semaforo == 'VERDE'
    assert social.propietario == 'Juan Pérez'


@pytest.mark.django_db
def test_sociopredial_lista_muestra_stats_verdes(
    authenticated_client, proyecto_construccion, torre_completa
):
    """KPI 'Liberadas' suma torres con semáforo VERDE."""
    from datetime import date
    social, _ = SocialPredial.objects.get_or_create(torre=torre_completa)
    social.acta_vecindad_fecha = date(2026, 4, 1)
    social.acta_acceso_comunitario_fecha = date(2026, 4, 2)
    social.autorizacion_propietario_fecha = date(2026, 4, 3)
    social.acta_acceso_privado_fecha = date(2026, 4, 4)
    social.save()

    url = reverse('construccion:social_predial',
                  kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert '🟢 Liberada' in body


# ====== Ambiental (#52) ======

@pytest.mark.django_db
def test_ambiental_lista_autocrea_relaciones(
    authenticated_client, proyecto_construccion, torre_legacy
):
    """Lista responde 200 y crea AmbientalTorre defensivamente."""
    url = reverse('construccion:ambiental',
                  kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'Ambiental' in body
    assert 'T-LEGACY-01' in body
    assert AmbientalTorre.objects.filter(torre=torre_legacy).exists()


@pytest.mark.django_db
def test_ambiental_semaforo_verde_si_nada_aplica(
    authenticated_client, proyecto_construccion, torre_completa
):
    """Si todas las actividades están en `_aplica=False`, semáforo es VERDE
    automáticamente (regla Gabriel Valencia: 'potrero limpio')."""
    amb, _ = AmbientalTorre.objects.get_or_create(torre=torre_completa)
    amb.ahuyentamiento_aplica = False
    amb.epifitas_aplica = False
    amb.aprov_forestal_torre_aplica = False
    amb.aprov_forestal_vano_aplica = False
    amb.rescate_arqueologico_aplica = False
    amb.save()
    assert amb.semaforo == 'VERDE'


@pytest.mark.django_db
def test_ambiental_guarda_aprovechamiento_forestal(
    authenticated_client, proyecto_construccion, torre_completa
):
    """POST guarda los campos de aprovechamiento forestal (torre + vano)."""
    amb, _ = AmbientalTorre.objects.get_or_create(torre=torre_completa)
    url = reverse('construccion:ambiental_torre',
                  kwargs={'proyecto_id': proyecto_construccion.id,
                          'torre_id': torre_completa.id})
    data = {
        'aprov_forestal_torre_aplica': 'on',
        'aprov_forestal_torre_fecha': '2026-05-10',
        'aprov_forestal_torre_ok': 'on',
        'aprov_forestal_vano_aplica': 'on',
        'aprov_forestal_vano_fecha': '2026-05-12',
        'adecuacion_accesos_porcentaje': '60',
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code == 302
    amb.refresh_from_db()
    assert amb.aprov_forestal_torre_ok is True
    assert str(amb.aprov_forestal_torre_fecha) == '2026-05-10'
    assert str(amb.aprov_forestal_vano_fecha) == '2026-05-12'
    assert amb.adecuacion_accesos_porcentaje == 60
