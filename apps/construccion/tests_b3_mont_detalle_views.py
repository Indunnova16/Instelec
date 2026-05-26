"""Tests B3b - UX completa de Montaje paridad Excel (#76).

Cubre las 8 specs E2E del BLUEPRINT:
  1. test_resumen_get_200_cuatro_etapas
  2. test_detalle_get_200_siete_secciones
  3. test_post_general_tipo_A_funcion_suspension_visible
  4. test_post_pesos_desviacion_8pct_warning_visible
  5. test_post_montaje_fechas_dias_calculado
  6. test_post_facturacion_charfield_subcontratista_persiste
  7. test_endpoint_legacy_avance_update_410_gone_montaje
  8. test_cross_proyecto_404_montaje

Patron pytest + @pytest.mark.django_db + `authenticated_client` fixture
(definida en conftest.py raiz - admin superuser).

La suite real corre en F4 (no hay venv local). Sintaxis verificada con
py_compile.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse


# ===========================================================================
# Fixtures locales
# ===========================================================================

@pytest.fixture
def contrato_b3b(db):
    from apps.contratos.models import Contrato
    return Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B3B-001',
        nombre='Contrato test B3b',
        cliente='Cliente Test B3b',
    )


@pytest.fixture
def proyecto_b3b(contrato_b3b):
    from apps.construccion.models import ProyectoConstruccion
    return ProyectoConstruccion.objects.create(
        contrato=contrato_b3b,
        nombre='Proyecto B3b test',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_b3b(proyecto_b3b):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_b3b,
        numero='T001',
        tipo='B4',
    )


@pytest.fixture
def proyecto_b3b_otro(contrato_b3b):
    """Un segundo proyecto para verificar el aislamiento cross-proyecto."""
    from apps.construccion.models import ProyectoConstruccion
    return ProyectoConstruccion.objects.create(
        contrato=contrato_b3b,
        nombre='Proyecto OTRO B3b',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_b3b_otro(proyecto_b3b_otro):
    """Torre que pertenece a OTRO proyecto - para cross-tests."""
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_b3b_otro,
        numero='T999',
        tipo='B4',
    )


# ===========================================================================
# 1. GET resumen - 4 etapas presentes
# ===========================================================================

@pytest.mark.django_db
def test_resumen_get_200_cuatro_etapas(authenticated_client, proyecto_b3b, torre_b3b):
    """GET /construccion/<p>/montaje/ devuelve 200 y referencia las 4 etapas
    (Estructura sitio, Prearmada, Torre Montada, Revisada)."""
    url = reverse('construccion:montaje_lista',
                  kwargs={'proyecto_id': proyecto_b3b.id})
    r = authenticated_client.get(url)
    assert r.status_code == 200
    content = r.content.decode('utf-8')
    # Las 4 etapas estan presentes en el header
    assert 'Estructura en sitio' in content
    assert 'Prearmada' in content
    assert 'Torre Montada' in content
    assert 'Revisada' in content


# ===========================================================================
# 2. GET detalle - 7 secciones disponibles
# ===========================================================================

@pytest.mark.django_db
def test_detalle_get_200_siete_secciones(authenticated_client, proyecto_b3b, torre_b3b):
    """GET detalle devuelve 200 y referencia las 7 secciones en los tabs."""
    url = reverse('construccion:montaje_detalle',
                  kwargs={'proyecto_id': proyecto_b3b.id, 'torre_id': torre_b3b.id})
    r = authenticated_client.get(url)
    assert r.status_code == 200
    content = r.content.decode('utf-8')
    # Las 7 secciones aparecen como labels en los tabs
    assert 'Info General' in content
    assert 'Recepcion Patio' in content
    assert 'Pre-armado' in content
    assert 'Montaje' in content
    assert 'Controles Calidad' in content
    assert 'Pesos' in content
    assert 'Facturacion' in content


# ===========================================================================
# 3. POST general tipo=A -> funcion=Suspension visible
# ===========================================================================

@pytest.mark.django_db
def test_post_general_tipo_A_funcion_suspension_visible(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """POST a seccion=general con tipo_torre=A devuelve JSON funcion='Suspension'."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    url = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
        'seccion': 'general',
    })
    r = authenticated_client.post(url, {
        'tipo_torre': 'A',
        'cuerpo': 'C1',
    })
    assert r.status_code == 200, r.content
    data = r.json()
    assert data['ok'] is True
    # `funcion` puede venir con o sin tilde segun el codec; la AC dice
    # Suspension/Retencion. Aceptamos ambas variantes.
    assert data['funcion'] in ('Suspension', 'Suspensión')

    # Persistio en BD
    detalle = MontajeEstructuraTorreDetalle.objects.get(torre=torre_b3b)
    assert detalle.tipo_torre == 'A'
    assert detalle.funcion in ('Suspension', 'Suspensión')


# ===========================================================================
# 4. POST pesos desviacion 8% -> warning visible
# ===========================================================================

@pytest.mark.django_db
def test_post_pesos_desviacion_8pct_warning_visible(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """POST peso_diseno=100, peso_instalado=108 (8% desviacion) -> JSON
    peso_alerta=True. Tras guardar, el detalle GET muestra el warning."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    save_url = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
        'seccion': 'pesos',
    })
    r = authenticated_client.post(save_url, {
        'peso_diseno_kl': '100',
        'peso_instalado_kl': '108',
    })
    assert r.status_code == 200, r.content
    data = r.json()
    assert data['ok'] is True
    assert data['peso_alerta'] is True
    # La desviacion calculada es 8.0 (con 2 decimales)
    assert data['peso_desviacion_pct'] == 8.0

    # Modelo refleja el cambio
    detalle = MontajeEstructuraTorreDetalle.objects.get(torre=torre_b3b)
    assert detalle.peso_diseno_kl == Decimal('100.00')
    assert detalle.peso_instalado_kl == Decimal('108.00')
    assert detalle.peso_alerta is True

    # GET detalle?seccion=pesos renderiza el warning visual (SSR)
    get_url = reverse('construccion:montaje_detalle', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
    }) + '?seccion=pesos'
    r2 = authenticated_client.get(get_url)
    assert r2.status_code == 200
    body = r2.content.decode('utf-8')
    assert 'mont-peso-warning-ssr' in body or 'mont-warning-peso-header' in body
    assert 'data-peso-alerta="true"' in body


# ===========================================================================
# 5. POST montaje fechas -> dias_montaje calculado
# ===========================================================================

@pytest.mark.django_db
def test_post_montaje_fechas_dias_calculado(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """POST montaje_fecha_inicio + montaje_fecha_fin -> JSON dias_montaje=N."""
    save_url = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
        'seccion': 'montaje',
    })
    r = authenticated_client.post(save_url, {
        'montaje_encargado': 'Ana',
        'montaje_fecha_inicio': '2026-05-10',
        'montaje_fecha_fin': '2026-05-17',
        'torre_montada_ok': 'on',
        'montaje_observaciones': '',
    })
    assert r.status_code == 200, r.content
    data = r.json()
    assert data['ok'] is True
    # 2026-05-17 - 2026-05-10 = 7 dias
    assert data['dias_montaje'] == 7


# ===========================================================================
# 6. POST facturacion -> facturada_por_contratista (CharField) persiste
# ===========================================================================

@pytest.mark.django_db
def test_post_facturacion_charfield_subcontratista_persiste(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """`facturada_por_contratista` es CharField - debe aceptar y persistir
    strings como 'Cruz' (no Boolean)."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    save_url = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
        'seccion': 'facturacion',
    })
    r = authenticated_client.post(save_url, {
        'facturada_a_dueno_ok': 'on',
        'facturada_por_contratista': 'Cruz',
    })
    assert r.status_code == 200, r.content
    data = r.json()
    assert data['ok'] is True

    detalle = MontajeEstructuraTorreDetalle.objects.get(torre=torre_b3b)
    assert detalle.facturada_a_dueno_ok is True
    assert detalle.facturada_por_contratista == 'Cruz'
    assert isinstance(detalle.facturada_por_contratista, str)


# ===========================================================================
# 7. Endpoint legacy `montaje_avance_update_gone` -> 410 Gone
# ===========================================================================

@pytest.mark.django_db
def test_endpoint_legacy_avance_update_410_gone_montaje(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """El reemplazo del endpoint legacy de edicion inline de matriz devuelve
    410 Gone con mensaje explicando que se reemplaza por el detalle."""
    url = reverse('construccion:montaje_avance_update_gone', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
    })
    r = authenticated_client.post(url, {
        'columna': 'estructura_sitio',
        'valor': '1',
    })
    assert r.status_code == 410
    data = r.json()
    assert data['ok'] is False
    assert 'deprecado' in data['error'].lower() or 'detalle' in data['error'].lower()

    # GET tambien -> 410
    r2 = authenticated_client.get(url)
    assert r2.status_code == 410


# ===========================================================================
# 8. Cross-proyecto -> 404
# ===========================================================================

@pytest.mark.django_db
def test_cross_proyecto_404_montaje(
    authenticated_client, proyecto_b3b, torre_b3b_otro
):
    """Si el torre_id no pertenece al proyecto_id de la URL, devuelve 404
    (proteccion estandar via get_object_or_404 con filtro proyecto)."""
    # Detalle GET cross-proyecto
    url_get = reverse('construccion:montaje_detalle', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b_otro.id,  # torre pertenece a OTRO proyecto
    })
    r = authenticated_client.get(url_get)
    assert r.status_code == 404

    # Save POST cross-proyecto
    url_save = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b_otro.id,
        'seccion': 'general',
    })
    r2 = authenticated_client.post(url_save, {'tipo_torre': 'A', 'cuerpo': 'C1'})
    assert r2.status_code == 404


# ===========================================================================
# Extras - edge cases y validaciones (no en BLUEPRINT, pero criticos para v1.0)
# ===========================================================================

@pytest.mark.django_db
def test_post_seccion_invalida_400(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """Slug de seccion fuera del catalogo -> 400 sin tocar BD."""
    # Construimos manualmente la URL porque reverse exige slug valido a Django
    url = f'/construccion/{proyecto_b3b.id}/montaje/{torre_b3b.id}/detalle/bogus/save/'
    r = authenticated_client.post(url, {'tipo_torre': 'A'})
    # path `<str:seccion>` acepta cualquier string -> entra al view y rebota.
    assert r.status_code == 400
    data = r.json()
    assert data['ok'] is False


@pytest.mark.django_db
def test_prearmado_fecha_fin_antes_inicio_400(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """clean() del MontSeccionPrearmadoForm rechaza fecha_fin < fecha_inicio."""
    url = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
        'seccion': 'prearmado',
    })
    r = authenticated_client.post(url, {
        'prearmado_encargado': 'Carlos',
        'estructura_en_sitio_ok': 'on',
        'prearmado_fecha_inicio': '2026-05-20',
        'prearmado_fecha_fin': '2026-05-10',  # antes del inicio
        'prearmada_ok': '',
        'prearmado_pct': '0',
    })
    assert r.status_code == 400
    data = r.json()
    assert data['ok'] is False
    assert 'errors' in data


@pytest.mark.django_db
def test_detalle_seccion_invalida_cae_default_general(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """GET detalle?seccion=bogus -> renderiza default `general` (no 500)."""
    url = reverse('construccion:montaje_detalle', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
    }) + '?seccion=bogus'
    r = authenticated_client.get(url)
    assert r.status_code == 200
    # El partial de general esta presente (referencia el form id)
    assert b'mont-form-general' in r.content


@pytest.mark.django_db
def test_post_pesos_desviacion_2pct_sin_alerta(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """Edge case: 2% desviacion -> peso_alerta=False (umbral 5% no excedido)."""
    url = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
        'seccion': 'pesos',
    })
    r = authenticated_client.post(url, {
        'peso_diseno_kl': '100',
        'peso_instalado_kl': '102',
    })
    assert r.status_code == 200
    data = r.json()
    assert data['peso_alerta'] is False
    assert data['peso_desviacion_pct'] == 2.0


@pytest.mark.django_db
def test_post_montaje_fechas_faltantes_dias_none(
    authenticated_client, proyecto_b3b, torre_b3b
):
    """Sin fechas -> dias_montaje=None."""
    url = reverse('construccion:montaje_detalle_save', kwargs={
        'proyecto_id': proyecto_b3b.id,
        'torre_id': torre_b3b.id,
        'seccion': 'montaje',
    })
    r = authenticated_client.post(url, {
        'montaje_encargado': 'Sin fechas',
        'montaje_fecha_inicio': '',
        'montaje_fecha_fin': '',
        'montaje_observaciones': '',
    })
    assert r.status_code == 200
    data = r.json()
    assert data['dias_montaje'] is None
