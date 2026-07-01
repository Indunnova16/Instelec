"""Tests para #171 Sprint A: torre_form.html real (crear/editar torres).

Archivo dedicado (NO tests.py compartido) para evitar colision con #154
que corre en paralelo sobre el mismo repo.
"""
import pytest
from django.urls import reverse

from apps.construccion.models import (
    AmbientalTorre,
    FaseTorre,
    PataObra,
    ProyectoConstruccion,
    SocialPredial,
    TorreConstruccion,
)
from apps.contratos.models import Contrato


@pytest.fixture
def proyecto_construccion(db):
    """Contrato + Proyecto de construccion listos para crear torres."""
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-001',
        nombre='Proyecto test #171 torre_form',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto test #171',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_legacy(proyecto_construccion):
    """Torre pre-existente (dato legacy) usada para probar el flujo de edicion
    contra un registro que ya existia antes del fix del template."""
    return TorreConstruccion.objects.create(
        proyecto=proyecto_construccion,
        numero='T-1',
        tipo='D6',
    )


# ====== A1: crear torre via el form real ======

@pytest.mark.django_db
def test_torre_crear_get_renderiza_form_real(authenticated_client, proyecto_construccion):
    """El placeholder 'En Desarrollo' fue reemplazado por un form Django real."""
    url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'En Desarrollo' not in resp.content
    assert b'<form method="post"' in resp.content
    assert b'csrfmiddlewaretoken' in resp.content


@pytest.mark.django_db
def test_torre_crear_post_crea_torre_y_redirige(authenticated_client, proyecto_construccion):
    """POST valido crea la torre y redirige (302) al listado, con las relaciones
    dependientes (PataObra x4, FaseTorre, SocialPredial, AmbientalTorre) creadas
    por TorreCreateView.form_valid."""
    url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.post(url, data={
        'numero': 'T-65',
        'tipo': 'D6',
        'tipo_cimentacion': 'ZAPATA',
        'peso_kg': '1200.5',
        'tramo_tendido': 'TEND 1',
        'latitud': '6.25184',
        'longitud': '-75.56359',
        'cuadrilla_civil': 'Cuadrilla A',
        'cuadrilla_montaje': '',
        'cuadrilla_tendido': '',
        'observaciones': 'Torre creada via test #171',
    })
    assert resp.status_code == 302
    expected_redirect = reverse('construccion:torres_lista', kwargs={'proyecto_id': proyecto_construccion.id})
    assert resp.url == expected_redirect

    torre = TorreConstruccion.objects.get(proyecto=proyecto_construccion, numero='T-65')
    assert torre.tipo == 'D6'
    assert torre.tipo_cimentacion == 'ZAPATA'
    assert PataObra.objects.filter(torre=torre).count() == 4
    assert FaseTorre.objects.filter(torre=torre).exists()
    assert SocialPredial.objects.filter(torre=torre).exists()
    assert AmbientalTorre.objects.filter(torre=torre).exists()


# ====== A1 edge case: editar torre existente ======

@pytest.mark.django_db
def test_torre_editar_get_prepopula_form(authenticated_client, proyecto_construccion, torre_legacy):
    """UpdateView: el form GET viene pre-poblado con los datos de la torre legacy."""
    url = reverse('construccion:torre_editar',
                  kwargs={'proyecto_id': proyecto_construccion.id, 'pk': torre_legacy.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'En Desarrollo' not in resp.content
    assert b'value="T-1"' in resp.content


@pytest.mark.django_db
def test_torre_editar_post_actualiza_torre_legacy(authenticated_client, proyecto_construccion, torre_legacy):
    """POST sobre una torre legacy (creada antes del fix) actualiza correctamente."""
    url = reverse('construccion:torre_editar',
                  kwargs={'proyecto_id': proyecto_construccion.id, 'pk': torre_legacy.id})
    resp = authenticated_client.post(url, data={
        'numero': 'T-1A',
        'tipo': 'B4',
        'tipo_cimentacion': 'PILOTE',
        'peso_kg': '',
        'tramo_tendido': '',
        'latitud': '',
        'longitud': '',
        'cuadrilla_civil': '',
        'cuadrilla_montaje': '',
        'cuadrilla_tendido': '',
        'observaciones': 'Editada via test #171',
    })
    assert resp.status_code == 302
    torre_legacy.refresh_from_db()
    assert torre_legacy.numero == 'T-1A'
    assert torre_legacy.tipo == 'B4'
    assert torre_legacy.tipo_cimentacion == 'PILOTE'
    assert torre_legacy.observaciones == 'Editada via test #171'


# ====== A2: numero alfanumerico ======

@pytest.mark.django_db
@pytest.mark.parametrize('numero_alfanumerico', ['T-1A', 'T-25B', 'E25', 'T-100'])
def test_torre_crear_numero_alfanumerico_valido(authenticated_client, proyecto_construccion, numero_alfanumerico):
    """El campo numero acepta formatos alfanumericos sin error de validacion
    (CharField sin validator numerico, help_text lo comunica en el form)."""
    url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.post(url, data={
        'numero': numero_alfanumerico,
        'tipo': '',
        'tipo_cimentacion': '',
        'peso_kg': '',
        'tramo_tendido': '',
        'latitud': '',
        'longitud': '',
        'cuadrilla_civil': '',
        'cuadrilla_montaje': '',
        'cuadrilla_tendido': '',
        'observaciones': '',
    })
    assert resp.status_code == 302, resp.content[:500]
    assert TorreConstruccion.objects.filter(proyecto=proyecto_construccion, numero=numero_alfanumerico).exists()


@pytest.mark.django_db
def test_torre_form_muestra_help_text_numero_alfanumerico(authenticated_client, proyecto_construccion):
    """El form real expone el help_text del campo numero indicando formato alfanumerico."""
    url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert b'alfanum' in resp.content.lower()


# ====== A3: conteo Social Predial / Ambiental no excluye por 'aplica' ======

@pytest.mark.django_db
def test_social_predial_cuenta_todas_las_torres_creadas_via_form(
    authenticated_client, proyecto_construccion
):
    """Verificacion de A3: SocialPredialView cuenta TODAS las torres del proyecto
    (incluida una creada recien via el form arreglado), sin excluir por 'aplica'."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='T-65')
    url = reverse('construccion:social_predial', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert torre.numero.encode() in resp.content


@pytest.mark.django_db
def test_ambiental_cuenta_todas_las_torres_creadas_via_form(
    authenticated_client, proyecto_construccion
):
    """Verificacion de A3: AmbientalView cuenta TODAS las torres del proyecto,
    sin excluir por 'aplica'."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='T-65')
    url = reverse('construccion:ambiental', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert torre.numero.encode() in resp.content
