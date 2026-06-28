"""Tests #149 (bounce=5, decisión HITL) — ELIMINAR la aplicabilidad por-torre.

Reproceso bounce-5 (MALENTENDIDO): durante 5 intervenciones se intentó MEJORAR
el mecanismo de filtro por-torre ``ObraCivilTorre.aplica_obras_proteccion``,
cuando la solicitud real del cliente (verbo imperativo "eliminar") + el HITL de
Miguel era ELIMINAR ese checkbox de raíz.

Comportamiento NUEVO (lo que estos tests asertan):

  * El módulo Obras de Protección (``TrinchosCunetasListView``) lista TODAS las
    torres APLICABLES del proyecto, gobernadas SOLO por el flag global
    ``TorreConstruccion.aplica`` (#160). Ya NO hay opt-in/opt-out por-torre.
      - Una torre con ``aplica_obras_proteccion=False`` (antes oculta) ahora
        APARECE (porque su flag global ``aplica=True``). ← dato legacy.
      - La torre ANULADA (``aplica=False``) NO aparece (no se rompe nada).
  * El checkbox "Obras Protección" se eliminó de la matriz Obra Civil: el markup
    ``data-toggle-aplica="aplica_obras_proteccion"`` ya NO se renderiza; los
    toggles que QUEDAN (``aplica`` global y ``aplica_pintura_aeronautica``) sí.
  * El upsert (``TrinchosCunetasUpsertView``) ya NO rechaza una torre por el flag
    eliminado.

SIN migración: la columna ``ObraCivilTorre.aplica_obras_proteccion`` queda
DORMIDA (reversible, no se borra).
"""
import re

import pytest
from django.db import connection
from django.urls import reverse


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sqlite_regexp_replace():
    """Registra regexp_replace en sqlite — ordenar_torres_construccion la usa.

    En CI (Postgres) es nativa; el backend sqlite de dev_lite no la trae.
    """
    if connection.vendor != 'sqlite':
        yield
        return

    def _regexp_replace(value, pattern, replacement, *flags):
        if value is None:
            return None
        return re.sub(pattern, replacement, str(value))

    connection.connection.create_function('regexp_replace', -1, _regexp_replace)
    yield


@pytest.fixture
def proyecto_i149(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I149-001',
        nombre='Contrato test #149',
        cliente='Cliente #149',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto obras protección #149',
        estado='EJECUCION',
    )


@pytest.fixture
def torres_i149(proyecto_i149):
    """Torres que cubren el comportamiento NUEVO (gobernado por torre.aplica):

    - E10: aplica=True, aplica_obras_proteccion=False (el flag por-torre eliminado).
      ANTES estaba OCULTA por el filtro; AHORA debe APARECER. ← DATO LEGACY:
      la fila ObraCivilTorre con el flag por-torre en False existía antes del fix.
    - E19: aplica=True, aplica_obras_proteccion=True, con obra capturada (legacy).
      Sigue visible (con su obra).
    - E25: aplica=False (torre ANULADA, #160). NO debe colarse en el listado.
    """
    from apps.construccion.models import (
        TorreConstruccion, ObraCivilTorre, TrinchoCuneta,
    )

    # E10: aplica global True, flag por-torre (eliminado) en False → DATO LEGACY.
    e10 = TorreConstruccion.objects.create(
        proyecto=proyecto_i149, numero='10', tipo='D6', aplica=True,
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_i149, torre=e10, aplica_obras_proteccion=False,
    )

    # E19: aplica global True, flag por-torre en True, con obra capturada legacy.
    e19 = TorreConstruccion.objects.create(
        proyecto=proyecto_i149, numero='19', tipo='D6', aplica=True,
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_i149, torre=e19, aplica_obras_proteccion=True,
    )
    TrinchoCuneta.objects.create(
        proyecto=proyecto_i149, torre=e19,
        medida_manejo=TrinchoCuneta.TipoObra.AMBAS,
        metros_trinchos=12, metros_cunetas=8, cuadrilla='Cuadrilla A',
        completado=True,
    )

    # E25: torre ANULADA (aplica global False) → no debe aparecer.
    e25 = TorreConstruccion.objects.create(
        proyecto=proyecto_i149, numero='25', tipo='D6', aplica=False,
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_i149, torre=e25, aplica_obras_proteccion=True,
    )
    return {'e10': e10, 'e19': e19, 'e25': e25}


def _ctx(authenticated_client, proyecto):
    """GET la lista del módulo Obras de Protección y devuelve la respuesta."""
    url = reverse('construccion:trinchos_cunetas',
                  kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]
    return resp


def _filas_por_torre(resp):
    return {f['torre'].id: f for f in resp.context['filas']}


# ===========================================================================
# Listado gobernado SOLO por torre.aplica (#160) — el filtro por-torre se eliminó
# ===========================================================================

@pytest.mark.django_db
def test_listado_lista_torre_con_flag_por_torre_false(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """DATO LEGACY + inversión: E10 (aplica=True, aplica_obras_proteccion=False)
    estaba OCULTA por el filtro eliminado; AHORA debe APARECER en el listado.

    Es el corazón del fix: el módulo ya no se rige por el flag por-torre.
    """
    resp = _ctx(authenticated_client, proyecto_i149)
    filas = _filas_por_torre(resp)
    e10 = torres_i149['e10']
    assert e10.id in filas, (
        "E10 (aplica=True, flag por-torre=False) DEBE aparecer: el módulo se "
        "rige SOLO por torre.aplica, ya no por aplica_obras_proteccion.")
    assert filas[e10.id]['obra'] is None, (
        "E10 no tiene obra capturada → fila placeholder (Pendiente).")


@pytest.mark.django_db
def test_listado_excluye_torre_anulada(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """No se rompe nada: la torre ANULADA (E25, aplica=False) NO se cuela en el
    listado, aunque su flag por-torre (dormido) esté en True."""
    resp = _ctx(authenticated_client, proyecto_i149)
    filas = _filas_por_torre(resp)
    assert torres_i149['e25'].id not in filas, (
        "E25 (torre anulada, aplica=False) NO debe aparecer en el listado.")


@pytest.mark.django_db
def test_listado_incluye_torre_legacy_con_su_obra(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """Dato legacy: E19 (con obra capturada antes del cambio) sigue apareciendo
    CON su obra (no se rompe el caso ya existente)."""
    resp = _ctx(authenticated_client, proyecto_i149)
    filas = _filas_por_torre(resp)
    e19 = torres_i149['e19']
    assert e19.id in filas, "E19 (aplica=True) debe seguir en el listado."
    obra = filas[e19.id]['obra']
    assert obra is not None, "E19 conserva su obra capturada en la fila."
    assert obra.completado is True
    assert obra.cuadrilla == 'Cuadrilla A'


@pytest.mark.django_db
def test_listado_lista_todas_las_torres_aplicables(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """El listado lista TODAS las torres aplicables (E10 + E19), independiente
    del flag por-torre eliminado; la anulada (E25) queda fuera → total = 2.

    Cubre ≥2 registros (no 1 fixture), incluyendo el legacy E10 (flag=False)."""
    resp = _ctx(authenticated_client, proyecto_i149)
    filas = _filas_por_torre(resp)
    ids = set(filas)
    assert torres_i149['e10'].id in ids
    assert torres_i149['e19'].id in ids
    assert torres_i149['e25'].id not in ids
    assert resp.context['total_torres'] == 2, (
        "Solo las 2 torres aplicables (E10 + E19); la anulada queda fuera.")


@pytest.mark.django_db
def test_selector_gobernado_por_aplica_global(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """El selector (torres_disponibles) ofrece todas las torres aplicables y
    excluye la anulada — gobernado SOLO por torre.aplica."""
    resp = _ctx(authenticated_client, proyecto_i149)
    ids = {t.id for t in resp.context['torres_disponibles']}
    assert torres_i149['e10'].id in ids, (
        "E10 (aplica=True, flag por-torre=False) debe ofrecerse en el selector.")
    assert torres_i149['e19'].id in ids
    assert torres_i149['e25'].id not in ids, (
        "E25 (anulada) no debe ofrecerse en el selector.")


# ===========================================================================
# Upsert ya no rechaza por el flag eliminado
# ===========================================================================

@pytest.mark.django_db
def test_upsert_no_rechaza_torre_por_flag_eliminado(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """E10 tenía aplica_obras_proteccion=False; ANTES el upsert la rechazaba con
    400. AHORA el guard se eliminó → el upsert procesa la torre (no 400 por el
    flag). Verifica que NO devuelve el error de aplicabilidad por-torre."""
    url = reverse('construccion:trinchos_cunetas_upsert',
                  kwargs={'proyecto_id': proyecto_i149.id})
    resp = authenticated_client.post(url, data={
        'torre_id': str(torres_i149['e10'].id),
        'medida_manejo': 'CUNETA',
        'metros_cunetas': '15',
    })
    # No debe ser el rechazo por el flag eliminado (status 400 con ese mensaje).
    body = resp.content.decode().lower()
    assert 'no aplica a obras de protección' not in body, (
        "El upsert NO debe rechazar la torre por el flag por-torre eliminado.")
    assert resp.status_code in (200, 201), (
        f"El upsert debe procesar la torre, status={resp.status_code}, "
        f"body={resp.content[:300]!r}")


# ===========================================================================
# Matriz Obra Civil — el checkbox 'Obras Protección' se eliminó del render
# ===========================================================================

@pytest.mark.django_db
def test_matriz_oc_no_renderiza_checkbox_obras_proteccion(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """El observable VISIBLE del cliente: la matriz OC ya NO contiene el markup
    del checkbox removido, pero SÍ los toggles que quedan (aplica + pintura)."""
    url = reverse('construccion:obra_civil_lista',
                  kwargs={'proyecto_id': proyecto_i149.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]
    html = resp.content.decode()
    # Removido:
    assert 'data-toggle-aplica="aplica_obras_proteccion"' not in html, (
        "El checkbox 'Obras Protección' (data-toggle-aplica="
        "\"aplica_obras_proteccion\") debe estar AUSENTE del render.")
    assert 'Obras Protección' not in html, (
        "El label 'Obras Protección' debe estar AUSENTE del render.")
    # Conservados:
    assert 'data-toggle-aplica="aplica"' in html, (
        "El toggle global 'aplica' (#160) debe seguir presente.")
    assert 'data-toggle-aplica="aplica_pintura_aeronautica"' in html, (
        "El toggle 'Pintura Aero.' (#153) debe seguir presente.")
