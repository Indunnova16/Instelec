"""Tests #147 — Tendido items 9/10/11 (feature).

- Item 9: protecciones con "No aplica" (protecciones_no_aplica gana sobre
  protecciones_ok en form_valid).
- Item 10: fecha_riega_manila (cabecera) + modelo hijo RiegaManilaTiro por tiros
  (F.T = flecha de tendido).
- Item 11: regulación/flechado por circuito (c1/c2/guarda); regulacion_flechado_ok
  legacy se conserva; si C2 no aplica se limpia regulacion_flechado_c2.
"""
from datetime import date

import pytest
from django.urls import reverse


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def proyecto_i147(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I147-001',
        nombre='Contrato test #147',
        cliente='Cliente #147',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto tendido #147',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_i147(proyecto_i147):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_i147, numero='42', tipo='D6',
    )


def _tendido_url(proyecto, torre):
    return reverse('construccion:tendido_torre',
                   kwargs={'proyecto_id': proyecto.id, 'torre_id': torre.id})


def _base_post():
    """POST mínimo con el management_form vacío del formset de tiros."""
    return {
        'circuito_2_aplica': 'on',
        'tiros_manila-TOTAL_FORMS': '0',
        'tiros_manila-INITIAL_FORMS': '0',
        'tiros_manila-MIN_NUM_FORMS': '0',
        'tiros_manila-MAX_NUM_FORMS': '1000',
    }


# ===========================================================================
# 1. Modelo: campos nuevos + RiegaManilaTiro
# ===========================================================================

@pytest.mark.django_db
def test_fasetorre_campos_nuevos_default(torre_i147):
    from apps.construccion.models import FaseTorre
    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    assert fase.protecciones_ok is False
    assert fase.protecciones_no_aplica is False
    assert fase.protecciones_fecha is None
    assert fase.fecha_riega_manila is None
    assert fase.regulacion_flechado_c1_ok is False
    assert fase.regulacion_flechado_c2_ok is False
    assert fase.regulacion_flechado_guarda_ok is False
    # legacy conservado
    assert hasattr(fase, 'regulacion_flechado_ok')


@pytest.mark.django_db
def test_riega_manila_tiro_ordering_y_unique(torre_i147):
    from django.db import IntegrityError, transaction
    from apps.construccion.models import FaseTorre, RiegaManilaTiro
    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=2, flecha_tendido_m=12.5)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=1, flecha_tendido_m=8.0)
    nums = list(fase.tiros_manila.values_list('numero_tiro', flat=True))
    assert nums == [1, 2], "ordering por numero_tiro"
    # unique_together(fase, numero_tiro)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RiegaManilaTiro.objects.create(fase=fase, numero_tiro=1)


# ===========================================================================
# 2. View POST: protecciones N/A + tiros
# ===========================================================================

@pytest.mark.django_db
def test_post_protecciones_no_aplica_gana(authenticated_client, proyecto_i147,
                                          torre_i147):
    """protecciones_no_aplica=True limpia protecciones_ok=False y fecha=None."""
    from apps.construccion.models import FaseTorre
    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update({
        'protecciones_no_aplica': 'on',
        'protecciones_ok': 'on',           # el cliente marcó ambos; N/A gana
        'protecciones_fecha': '2026-06-19',
        'fecha_riega_manila': '2026-06-18',
    })
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.protecciones_no_aplica is True
    assert fase.protecciones_ok is False, "No aplica gana sobre instaladas"
    assert fase.protecciones_fecha is None
    assert fase.fecha_riega_manila == date(2026, 6, 18)


@pytest.mark.django_db
def test_post_crea_dos_tiros(authenticated_client, proyecto_i147, torre_i147):
    """POST con 2 filas de tiros crea 2 RiegaManilaTiro en DB."""
    from apps.construccion.models import FaseTorre, RiegaManilaTiro
    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update({
        'tiros_manila-TOTAL_FORMS': '2',
        'tiros_manila-0-numero_tiro': '1',
        'tiros_manila-0-fecha': '2026-06-10',
        'tiros_manila-0-flecha_tendido_m': '10.5',
        'tiros_manila-0-observaciones': 'tiro uno',
        'tiros_manila-1-numero_tiro': '2',
        'tiros_manila-1-fecha': '2026-06-11',
        'tiros_manila-1-flecha_tendido_m': '11.0',
        'tiros_manila-1-observaciones': 'tiro dos',
    })
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)
    tiros = list(fase.tiros_manila.all())
    assert len(tiros) == 2, [t.numero_tiro for t in tiros]
    assert {t.numero_tiro for t in tiros} == {1, 2}
    assert RiegaManilaTiro.objects.filter(fase=fase, flecha_tendido_m=10.5).exists()


@pytest.mark.django_db
def test_post_tiro_sin_numero_autoasigna(authenticated_client, proyecto_i147,
                                         torre_i147):
    """numero_tiro vacío → autoasigna max+1 (empieza en 1)."""
    from apps.construccion.models import FaseTorre
    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update({
        'tiros_manila-TOTAL_FORMS': '1',
        'tiros_manila-0-numero_tiro': '',   # vacío
        'tiros_manila-0-flecha_tendido_m': '7.0',
    })
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]
    fase = FaseTorre.objects.get(torre=torre_i147)
    nums = list(fase.tiros_manila.values_list('numero_tiro', flat=True))
    assert nums == [1], f"autoasignar a 1, fue {nums}"


@pytest.mark.django_db
def test_post_circuito2_no_aplica_limpia_regulacion_c2(authenticated_client,
                                                       proyecto_i147, torre_i147):
    """Si circuito_2_aplica=False, regulacion_flechado_c2 queda limpio."""
    from apps.construccion.models import FaseTorre
    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.pop('circuito_2_aplica')   # checkbox desmarcado = no aplica
    data.update({
        'regulacion_flechado_c2_ok': 'on',
        'regulacion_flechado_c2_fecha': '2026-06-15',
        'regulacion_flechado_c1_ok': 'on',
    })
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]
    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.circuito_2_aplica is False
    assert fase.regulacion_flechado_c2_ok is False, "C2 no aplica → limpiar regulación C2"
    assert fase.regulacion_flechado_c2_fecha is None
    assert fase.regulacion_flechado_c1_ok is True, "C1 no se toca"


# ===========================================================================
# 3. Render del detalle muestra los campos nuevos
# ===========================================================================

@pytest.mark.django_db
def test_render_incluye_campos_nuevos(authenticated_client, proyecto_i147,
                                      torre_i147):
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    for needle in (
        'name="protecciones_no_aplica"',
        'name="protecciones_ok"',
        'name="fecha_riega_manila"',
        'data-tiros-manila',
        'name="regulacion_flechado_c1_ok"',
        'name="regulacion_flechado_c2_ok"',
        'name="regulacion_flechado_guarda_ok"',
    ):
        assert needle in body, f"falta {needle} en el render"
    # textos que el journey espera
    assert 'riega de manila' in body.lower()
    assert 'F.T' in body


@pytest.mark.django_db
def test_render_incluye_boton_agregar_tiro(authenticated_client, proyecto_i147,
                                           torre_i147):
    """#147 UI: el detalle de tendido renderiza el botón dinámico
    [data-add-tiro] + la plantilla empty_form (placeholder __prefix__) para
    que el cliente pueda agregar tiros (síntoma original: solo 'Quitar')."""
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    # botón con selector contractual del E2E
    assert 'data-add-tiro' in body, "falta el botón '+ Agregar tiro'"
    assert 'Agregar tiro' in body
    # plantilla oculta con el empty_form (placeholder __prefix__)
    assert '__prefix__' in body, "falta la plantilla empty_form clonable"
    assert 'name="tiros_manila-__prefix__-flecha_tendido_m"' in body
    # componente Alpine registrado + management_form presente
    assert "Alpine.data('tirosManila'" in body
    assert 'id_tiros_manila-TOTAL_FORMS' in body


@pytest.mark.django_db
def test_render_total_forms_cuenta_la_fila_extra(authenticated_client,
                                                 proyecto_i147, torre_i147):
    """Con 0 tiros guardados, el formset (extra=1) rinde 1 fila editable y
    TOTAL_FORMS=1 → tras 1 click de 'Agregar tiro' el JS añade el índice 1
    (tiros_manila-1-*) y deja TOTAL_FORMS=2, como espera el journey."""
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    # management_form TOTAL_FORMS = INITIAL(0) + extra(1) = 1
    assert 'name="tiros_manila-TOTAL_FORMS" value="1"' in body, \
        "TOTAL_FORMS inicial debe contar la fila extra editable"
    # la fila extra (índice 0) es editable de entrada
    assert 'name="tiros_manila-0-flecha_tendido_m"' in body
