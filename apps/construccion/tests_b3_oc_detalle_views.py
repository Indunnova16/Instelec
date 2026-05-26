"""Tests B2b (#74) — Vistas paridad Obra Civil CANT OOCC.

Cubre los 10 tests declarados en BLUEPRINT.sub_features.B2b.tests_e2e:

1. test_resumen_get_200_seis_columnas_visible
2. test_detalle_get_200_cuatro_patas_seis_secciones
3. test_post_cerramiento_finalizado_ok_recalcula_resumen
4. test_post_excavacion_metros_m3_persiste
5. test_post_solado_sub_bloque_agua_arena_grava_cemento
6. test_endpoint_legacy_avance_update_410_gone
7. test_links_matriz_apuntan_correctamente_a_detalle
8. test_role_operario_ve_solo_torres_cuadrilla
9. test_cross_proyecto_404
10. test_panel_pesos_sigue_editable
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


User = get_user_model()


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def proyecto_oc_b2b(db):
    """ProyectoConstruccion con pesos default (5/30/5/15/30/15 = 100)."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B2B-001',
        nombre='Contrato test B2b',
        cliente='Test Cliente B2b',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto OC paridad B2b',
        estado='EJECUCION',
    )


@pytest.fixture
def proyecto_oc_b2b_otro(db):
    """Segundo proyecto para test cross-proyecto 404."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B2B-002',
        nombre='Contrato test B2b - otro',
        cliente='Otro cliente',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B2b Otro',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_oc_b2b(proyecto_oc_b2b):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_oc_b2b,
        numero='100',
        tipo='D6',
    )


# ===========================================================================
# 1. ObraCivilResumenView GET 200 — 6 columnas visibles
# ===========================================================================

@pytest.mark.django_db
def test_resumen_get_200_seis_columnas_visible(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """Vista resumen (URL legacy `obra_civil_lista`) responde 200 con las 6
    columnas y el banner de re-propósito.
    """
    url = reverse(
        'construccion:obra_civil_lista',
        kwargs={'proyecto_id': proyecto_oc_b2b.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]

    body = resp.content.decode()
    # Las 6 columnas aparecen
    for label in ('Cerramiento', 'Excavación', 'Solado',
                  'Acero', 'Vaciado', 'Compactación'):
        assert label in body, f'columna {label} faltante'

    # Banner explicativo del re-propósito B2b
    assert 'Vista resumen' in body or 'resumen' in body.lower()


# ===========================================================================
# 2. ObraCivilDetalleView GET 200 — 4 patas + 6 secciones en tabs
# ===========================================================================

@pytest.mark.django_db
def test_detalle_get_200_cuatro_patas_seis_secciones(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """Detalle responde 200 y renderiza 4 patas + 6 secciones."""
    url = reverse(
        'construccion:obra_civil_detalle',
        kwargs={'proyecto_id': proyecto_oc_b2b.id, 'torre_id': torre_oc_b2b.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]
    body = resp.content.decode()

    # 4 patas
    for pata in ('Pata A', 'Pata B', 'Pata C', 'Pata D'):
        assert pata in body, f'{pata} faltante en tabs'

    # 6 secciones (labels en pestaña horizontal)
    for label in ('Cerramiento', 'Excavación', 'Solado',
                  'Acero', 'Vaciado', 'Compactación'):
        assert label in body, f'sección {label} faltante en tabs'


# ===========================================================================
# 3. POST cerramiento_finalizado_ok → recalcula resumen vía signal
# ===========================================================================

@pytest.mark.django_db
def test_post_cerramiento_finalizado_ok_recalcula_resumen(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """POST cerramiento con cerr_finalizado_ok=True actualiza el cache
    ObraCivilTorre.avance_cerramiento (signal de B2a corre post_save).
    """
    from apps.construccion.models import ObraCivilTorre

    url = reverse(
        'construccion:obra_civil_detalle_seccion',
        kwargs={
            'proyecto_id': proyecto_oc_b2b.id,
            'torre_id': torre_oc_b2b.id,
            'pata': 'A',
            'seccion': 'cerramiento',
        },
    )
    resp = authenticated_client.post(url, {
        'cerr_madera_un': '5',
        'cerr_lona_m': '12.50',
        'cerr_senalizacion_ok': 'on',
        'cerr_notas': 'Test',
        'cerr_finalizado_ok': 'on',
    })
    assert resp.status_code == 200, resp.content[:500]
    data = resp.json()
    assert data['ok'] is True

    # El signal debe haber creado/actualizado el cache de la torre
    cache = ObraCivilTorre.objects.get(torre=torre_oc_b2b)
    # Con 1 pata finalizada, promedio de 1 muestra = Decimal('1')
    assert cache.avance_cerramiento == Decimal('1'), (
        f'esperaba 1 (pata A finalizada), got {cache.avance_cerramiento}'
    )


# ===========================================================================
# 4. POST excavación con metros_m3 persiste
# ===========================================================================

@pytest.mark.django_db
def test_post_excavacion_metros_m3_persiste(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """POST excavación: exc_metros_m3 y exc_ejecutada_pct se persisten."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    url = reverse(
        'construccion:obra_civil_detalle_seccion',
        kwargs={
            'proyecto_id': proyecto_oc_b2b.id,
            'torre_id': torre_oc_b2b.id,
            'pata': 'B',
            'seccion': 'excavacion',
        },
    )
    resp = authenticated_client.post(url, {
        'exc_cuadrilla': 'Cuadrilla 1',
        'exc_tipo': 'MANUAL',
        'exc_metros_m3': '25.75',
        'exc_monitoreo_arq': 'LIBERADA',
        'exc_ejecutada_pct': '0.45',
        'exc_observaciones': 'Test obs',
        'exc_ft022_ok': 'on',
    })
    assert resp.status_code == 200, resp.content[:500]
    data = resp.json()
    assert data['ok'] is True

    det = ObraCivilTorreDetalle.objects.get(
        torre=torre_oc_b2b, pata='B',
    )
    assert det.exc_metros_m3 == Decimal('25.75')
    assert det.exc_ejecutada_pct == Decimal('0.4500')
    assert det.exc_cuadrilla == 'Cuadrilla 1'
    assert det.exc_ft022_ok is True


# ===========================================================================
# 5. POST solado: sub-bloque agua/arena/grava/cemento (4 valores en 1 POST)
# ===========================================================================

@pytest.mark.django_db
def test_post_solado_sub_bloque_agua_arena_grava_cemento(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """POST solado con 4 sub-bloques (calc/real) en un solo submit persiste."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    url = reverse(
        'construccion:obra_civil_detalle_seccion',
        kwargs={
            'proyecto_id': proyecto_oc_b2b.id,
            'torre_id': torre_oc_b2b.id,
            'pata': 'C',
            'seccion': 'solado',
        },
    )
    resp = authenticated_client.post(url, {
        'sol_agua_calc': '100.00', 'sol_agua_real': '95.50',
        'sol_arena_calc': '200.00', 'sol_arena_real': '210.00',
        'sol_grava_calc': '300.00', 'sol_grava_real': '295.00',
        'sol_cemento_calc': '50.00', 'sol_cemento_real': '52.00',
        'sol_ejecutado_pct': '0.60',
    })
    assert resp.status_code == 200, resp.content[:500]
    assert resp.json()['ok'] is True

    det = ObraCivilTorreDetalle.objects.get(torre=torre_oc_b2b, pata='C')
    assert det.sol_agua_calc == Decimal('100.00')
    assert det.sol_agua_real == Decimal('95.50')
    assert det.sol_arena_real == Decimal('210.00')
    assert det.sol_grava_calc == Decimal('300.00')
    assert det.sol_cemento_real == Decimal('52.00')
    assert det.sol_ejecutado_pct == Decimal('0.6000')

    # Desviaciones calc vs real expuestas por el modelo
    assert det.sol_agua_desv == Decimal('-4.50')
    assert det.sol_arena_desv == Decimal('10.00')


# ===========================================================================
# 6. Endpoint legacy obra_civil_avance_update → 410 Gone
# ===========================================================================

@pytest.mark.django_db
def test_endpoint_legacy_avance_update_410_gone(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """El endpoint `OCAvanceLegacy410View` devuelve 410 con mensaje claro
    apuntando a la nueva vista detalle.

    Verifica también el comportamiento AJAX (JSON) cuando el cliente envía
    `X-Requested-With: XMLHttpRequest`.
    """
    url = reverse(
        'construccion:obra_civil_avance_legacy_410',
        kwargs={
            'proyecto_id': proyecto_oc_b2b.id,
            'torre_id': torre_oc_b2b.id,
        },
    )
    # POST plain → 410 con mensaje texto
    resp = authenticated_client.post(url, {
        'columna': 'cerramiento', 'valor': '0.5',
    })
    assert resp.status_code == 410
    body = resp.content.decode()
    assert 'detalle' in body.lower()
    # URL nueva sugerida en el mensaje
    assert str(torre_oc_b2b.id) in body or 'obra-civil' in body.lower()

    # AJAX → JSON
    resp_ajax = authenticated_client.post(
        url, {'columna': 'cerramiento', 'valor': '0.5'},
        HTTP_X_REQUESTED_WITH='XMLHttpRequest',
    )
    assert resp_ajax.status_code == 410
    data = resp_ajax.json()
    assert data.get('gone') is True
    assert 'error' in data


# ===========================================================================
# 7. Links de matriz apuntan correctamente a detalle
# ===========================================================================

@pytest.mark.django_db
def test_links_matriz_apuntan_correctamente_a_detalle(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """En el HTML del resumen, cada celda enlaza al detalle de la torre con
    `pata=A` y `seccion=<slug>`.
    """
    url = reverse(
        'construccion:obra_civil_lista',
        kwargs={'proyecto_id': proyecto_oc_b2b.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()

    # URL base de detalle para esta torre
    detalle_url = reverse(
        'construccion:obra_civil_detalle',
        kwargs={
            'proyecto_id': proyecto_oc_b2b.id,
            'torre_id': torre_oc_b2b.id,
        },
    )
    assert detalle_url in body, (
        f'el resumen debería enlazar a {detalle_url}, body[:1000]={body[:1000]}'
    )

    # Las 6 secciones deben aparecer como query params seccion=<slug>
    for slug in ('cerramiento', 'excavacion', 'solado',
                 'acero', 'vaciado', 'compactacion'):
        assert f'seccion={slug}' in body, f'link a sección {slug} faltante'


# ===========================================================================
# 8. Operario ve solo torres de su cuadrilla
# ===========================================================================

@pytest.mark.django_db
def test_role_operario_ve_solo_torres_cuadrilla(
    client, proyecto_oc_b2b, torre_oc_b2b, user_password,
):
    """Un usuario rol operario_construccion sin cuadrillas activas ve 0 torres
    en el resumen (queryset filtra a .none()).
    """
    operario = User.objects.create_user(
        email='operario@test.com',
        password=user_password,
        first_name='Operario',
        last_name='Test',
        rol='operario_construccion',
    )
    client.login(username=operario.email, password=user_password)

    url = reverse(
        'construccion:obra_civil_lista',
        kwargs={'proyecto_id': proyecto_oc_b2b.id},
    )
    resp = client.get(url)
    # 200 — operario está permitido (allowed_roles include OPERARIO_ROLES)
    assert resp.status_code == 200, resp.content[:300]
    body = resp.content.decode()
    # Sin cuadrillas activas → queryset .none() → no aparece la torre
    assert torre_oc_b2b.numero not in body or 'No hay torres' in body


# ===========================================================================
# 9. Cross-proyecto 404: torre de B pero URL con proyecto A
# ===========================================================================

@pytest.mark.django_db
def test_cross_proyecto_404(
    authenticated_client, proyecto_oc_b2b, proyecto_oc_b2b_otro, torre_oc_b2b,
):
    """Si pido el detalle con proyecto_id=A pero torre_id pertenece a B → 404."""
    url = reverse(
        'construccion:obra_civil_detalle',
        kwargs={
            'proyecto_id': proyecto_oc_b2b_otro.id,  # OTRO proyecto
            'torre_id': torre_oc_b2b.id,             # torre de proyecto_oc_b2b
        },
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 404


# ===========================================================================
# 10. Panel pesos sigue editable (endpoint legacy obra_civil_pesos_update)
# ===========================================================================

@pytest.mark.django_db
def test_panel_pesos_sigue_editable(
    authenticated_client, proyecto_oc_b2b,
):
    """El endpoint legacy `obra_civil_pesos_update` sigue 200 OK — el panel
    de pesos en el resumen no se rompió por el re-propósito.
    """
    url = reverse(
        'construccion:obra_civil_pesos_update',
        kwargs={'proyecto_id': proyecto_oc_b2b.id},
    )
    # Pesos válidos (suman 100)
    resp = authenticated_client.post(url, {
        'cerramiento': '10',
        'excavacion': '25',
        'solado': '5',
        'acero': '15',
        'vaciado': '30',
        'compactacion': '15',
    })
    assert resp.status_code == 200, resp.content[:300]
    data = resp.json()
    assert data.get('ok') is True
    assert data.get('suma') == 100


# ===========================================================================
# Extras: edge cases
# ===========================================================================

@pytest.mark.django_db
def test_post_seccion_invalida_400(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """POST con sección inválida en URL → 400 explicativo."""
    # No usamos reverse porque la URL exige str — construimos manualmente.
    url = (f'/construccion/{proyecto_oc_b2b.id}/obra-civil/'
           f'{torre_oc_b2b.id}/detalle/A/no_existe/')
    resp = authenticated_client.post(url, {})
    assert resp.status_code == 400
    data = resp.json()
    assert 'error' in data


@pytest.mark.django_db
def test_post_excavacion_pct_fuera_rango_400(
    authenticated_client, proyecto_oc_b2b, torre_oc_b2b,
):
    """exc_ejecutada_pct > 1 dispara 400 con errores del form."""
    url = reverse(
        'construccion:obra_civil_detalle_seccion',
        kwargs={
            'proyecto_id': proyecto_oc_b2b.id,
            'torre_id': torre_oc_b2b.id,
            'pata': 'A',
            'seccion': 'excavacion',
        },
    )
    resp = authenticated_client.post(url, {
        'exc_ejecutada_pct': '2.5',  # fuera de rango
    })
    assert resp.status_code == 400
    data = resp.json()
    assert data['ok'] is False
    assert 'errors' in data
