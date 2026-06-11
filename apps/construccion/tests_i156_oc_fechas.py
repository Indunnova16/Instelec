"""Tests #156 — Fechas de seguimiento por torre en la matriz Obra Civil.

Cubre:
- property ObraCivilTorre.alerta_retraso (True/False según fecha_esperada vs
  fecha_final vs hoy).
- POST AJAX ObraCivilFechasUpdateView persiste las 3 fechas.
- Render del input type=date con value YYYY-MM-DD (bug es-CO #130:
  format='%Y-%m-%d' obligatorio).
- Badge "Atrasado" aparece en la matriz cuando la torre está atrasada.
"""
import re
from datetime import date, timedelta

import pytest
from django.db import connection
from django.urls import reverse


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sqlite_regexp_replace():
    """Registra regexp_replace en sqlite para los tests que GET la matriz.

    ObraCivilMatrizView ordena las torres con la función Postgres
    regexp_replace (views.ordenar_torres_construccion); el backend sqlite de
    dev_lite no la trae. En CI (Postgres) existe nativa. Este shim permite
    ejercer el render de la matriz (badge/inputs) también en sqlite local.
    """
    if connection.vendor != 'sqlite':  # Postgres: nativa, no hacer nada
        yield
        return

    def _regexp_replace(value, pattern, replacement, *flags):
        if value is None:
            return None
        return re.sub(pattern, replacement, str(value))

    conn = connection.connection
    # -1 = variadic: Postgres lo invoca con 4 args (incluye el flag 'g').
    conn.create_function('regexp_replace', -1, _regexp_replace)
    yield

@pytest.fixture
def proyecto_i156(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I156-001',
        nombre='Contrato test #156',
        cliente='Cliente #156',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto fechas OC #156',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_i156(proyecto_i156):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_i156, numero='65', tipo='D6',
    )


@pytest.fixture
def oc_i156(proyecto_i156, torre_i156):
    from apps.construccion.models import ObraCivilTorre
    return ObraCivilTorre.objects.create(proyecto=proyecto_i156, torre=torre_i156)


# ===========================================================================
# 1. property alerta_retraso
# ===========================================================================

@pytest.mark.django_db
def test_alerta_retraso_true_cuando_esperada_pasada_sin_final(oc_i156):
    """Esperada en el pasado + final NULL → atrasado."""
    oc_i156.fecha_esperada = date.today() - timedelta(days=10)
    oc_i156.fecha_final = None
    oc_i156.save()
    assert oc_i156.alerta_retraso is True


@pytest.mark.django_db
def test_alerta_retraso_false_si_hay_fecha_final(oc_i156):
    """Aunque la esperada pasó, si ya hay fecha_final NO está atrasado."""
    oc_i156.fecha_esperada = date.today() - timedelta(days=10)
    oc_i156.fecha_final = date.today() - timedelta(days=2)
    oc_i156.save()
    assert oc_i156.alerta_retraso is False


@pytest.mark.django_db
def test_alerta_retraso_false_si_esperada_futura(oc_i156):
    """Esperada en el futuro → no atrasado."""
    oc_i156.fecha_esperada = date.today() + timedelta(days=10)
    oc_i156.fecha_final = None
    oc_i156.save()
    assert oc_i156.alerta_retraso is False


@pytest.mark.django_db
def test_alerta_retraso_false_sin_esperada(oc_i156):
    """Sin fecha_esperada nunca está atrasado."""
    oc_i156.fecha_esperada = None
    oc_i156.fecha_final = None
    oc_i156.save()
    assert oc_i156.alerta_retraso is False


# ===========================================================================
# 2. POST persiste las 3 fechas
# ===========================================================================

@pytest.mark.django_db
def test_post_fechas_persiste_las_tres(authenticated_client, proyecto_i156,
                                       torre_i156, oc_i156):
    from apps.construccion.models import ObraCivilTorre
    url = reverse('construccion:obra_civil_fechas_update',
                  kwargs={'proyecto_id': proyecto_i156.id,
                          'torre_id': torre_i156.id})
    resp = authenticated_client.post(url, {
        'fecha_inicio': '2026-01-15',
        'fecha_esperada': '2026-03-20',
        'fecha_final': '2026-03-25',
    })
    assert resp.status_code == 200, resp.content[:500]
    assert resp.json()['ok'] is True

    oc = ObraCivilTorre.objects.get(pk=oc_i156.pk)
    assert oc.fecha_inicio == date(2026, 1, 15)
    assert oc.fecha_esperada == date(2026, 3, 20)
    assert oc.fecha_final == date(2026, 3, 25)


@pytest.mark.django_db
def test_post_fechas_parcial_y_limpia(authenticated_client, proyecto_i156,
                                      torre_i156, oc_i156):
    """Guardar solo inicio; el resto queda NULL (campos opcionales)."""
    from apps.construccion.models import ObraCivilTorre
    url = reverse('construccion:obra_civil_fechas_update',
                  kwargs={'proyecto_id': proyecto_i156.id,
                          'torre_id': torre_i156.id})
    resp = authenticated_client.post(url, {
        'fecha_inicio': '2026-02-01',
        'fecha_esperada': '',
        'fecha_final': '',
    })
    assert resp.status_code == 200
    oc = ObraCivilTorre.objects.get(pk=oc_i156.pk)
    assert oc.fecha_inicio == date(2026, 2, 1)
    assert oc.fecha_esperada is None
    assert oc.fecha_final is None


@pytest.mark.django_db
def test_post_fechas_devuelve_alerta_retraso(authenticated_client,
                                             proyecto_i156, torre_i156, oc_i156):
    """El JSON refleja el estado de atraso tras guardar esperada pasada."""
    url = reverse('construccion:obra_civil_fechas_update',
                  kwargs={'proyecto_id': proyecto_i156.id,
                          'torre_id': torre_i156.id})
    pasada = (date.today() - timedelta(days=5)).isoformat()
    resp = authenticated_client.post(url, {
        'fecha_inicio': '', 'fecha_esperada': pasada, 'fecha_final': '',
    })
    assert resp.status_code == 200
    assert resp.json()['alerta_retraso'] is True


# ===========================================================================
# 3. Render del input con value YYYY-MM-DD (bug es-CO #130)
# ===========================================================================

@pytest.mark.django_db
def test_form_renderiza_value_iso(oc_i156):
    """El widget DateInput debe renderizar value='YYYY-MM-DD' (no dd/mm/yyyy),
    de lo contrario el <input type=date> deja el campo vacío al recargar."""
    from apps.construccion.forms import ObraCivilFechasForm
    oc_i156.fecha_inicio = date(2026, 1, 15)
    oc_i156.save()
    form = ObraCivilFechasForm(instance=oc_i156)
    html = form['fecha_inicio'].as_widget()
    assert 'value="2026-01-15"' in html, html


@pytest.mark.django_db
def test_matriz_badge_atrasado_visible(authenticated_client, proyecto_i156,
                                       torre_i156, oc_i156,
                                       sqlite_regexp_replace):
    """La matriz muestra el badge 'Atrasado' para una torre atrasada."""
    oc_i156.fecha_esperada = date(2020, 1, 1)
    oc_i156.fecha_final = None
    oc_i156.save()
    url = reverse('construccion:obra_civil_lista',
                  kwargs={'proyecto_id': proyecto_i156.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]
    body = resp.content.decode()
    assert 'Atrasado' in body
    assert 'data-alerta-retraso' in body
    # input de fecha presente con data-attr por torre
    assert f'data-fecha="inicio" data-torre="{torre_i156.id}"' in body


@pytest.mark.django_db
def test_matriz_sin_badge_cuando_no_atrasado(authenticated_client,
                                             proyecto_i156, torre_i156, oc_i156,
                                             sqlite_regexp_replace):
    """Sin atraso, no aparece el badge 'Atrasado'."""
    oc_i156.fecha_esperada = date.today() + timedelta(days=30)
    oc_i156.save()
    url = reverse('construccion:obra_civil_lista',
                  kwargs={'proyecto_id': proyecto_i156.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert 'data-alerta-retraso' not in resp.content.decode()
