"""Tests #149 — Obras de Protección: desacoplar del flag global #160.

El módulo Obras de Protección (TrinchosCunetasListView) debe regirse SOLO por
``ObraCivilTorre.aplica_obras_proteccion`` (opt-in real curado por el cliente),
DESACOPLADO del flag global ``TorreConstruccion.aplica`` (#160).

Dos bugs que el fix corrige (ambos invierten comportamiento):

  (a) El selector ``torres_disponibles`` pasaba por
      ``ordenar_torres_construccion(qs)`` con ``incluir_no_aplica=False``, que
      aplica el filtro GLOBAL ``aplica=True`` ENCIMA del filtro por módulo. Una
      torre con ``aplica_obras_proteccion=True`` pero ``aplica=False`` (global)
      quedaba OCULTA. El fix pasa ``incluir_no_aplica=True`` → aparece.

  (b) La tabla de obras existentes (``obras``) no filtraba por
      ``aplica_obras_proteccion``. Una torre con ``aplica_obras_proteccion=False``
      que ya tenía una fila ``TrinchoCuneta`` preexistente seguía apareciendo.
      El fix filtra ``torre__obra_civil__aplica_obras_proteccion=True`` → no aparece.

SIN migración, SIN data_fix (la curación opt-in del cliente vive en la data).
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
    """Dos torres que aíslan los dos bugs:

    - E19: oc (obras protección) = True, pero flag GLOBAL aplica = False.
      Debe APARECER en el selector (el global no debe ocultarla).
    - E1:  oc = False, flag GLOBAL aplica = True, con obra preexistente.
      NO debe APARECER en la tabla de obras (oc gobierna).
    """
    from apps.construccion.models import (
        TorreConstruccion, ObraCivilTorre, TrinchoCuneta,
    )

    # E19: marcada en Obras de Protección, pero "No aplica" globalmente.
    e19 = TorreConstruccion.objects.create(
        proyecto=proyecto_i149, numero='19', tipo='D6', aplica=False,
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_i149, torre=e19, aplica_obras_proteccion=True,
    )

    # E1: NO marcada en Obras de Protección, global aplica=True, con obra previa.
    e1 = TorreConstruccion.objects.create(
        proyecto=proyecto_i149, numero='1', tipo='D6', aplica=True,
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_i149, torre=e1, aplica_obras_proteccion=False,
    )
    # Obra preexistente sobre E1 (creada antes de desmarcar oc).
    TrinchoCuneta.objects.create(
        proyecto=proyecto_i149, torre=e1,
        medida_manejo=TrinchoCuneta.TipoObra.CUNETA,
    )
    return {'e19': e19, 'e1': e1}


def _ctx(authenticated_client, proyecto):
    """GET la lista y devuelve el context (ids del selector + obras)."""
    url = reverse('construccion:trinchos_cunetas',
                  kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]
    return resp


# ===========================================================================
# Bug (a) — selector desacoplado del flag global #160
# ===========================================================================

@pytest.mark.django_db
def test_selector_muestra_torre_oc_true_aunque_global_false(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """E19 (oc=True, global aplica=False) DEBE aparecer en torres_disponibles.

    Antes del fix el segundo filtro global aplica=True la ocultaba.
    """
    resp = _ctx(authenticated_client, proyecto_i149)
    ids = [t.id for t in resp.context['torres_disponibles']]
    assert torres_i149['e19'].id in ids, (
        "E19 (oc=True, global=False) debe aparecer: el módulo se rige SOLO por "
        "aplica_obras_proteccion, no por el flag global #160.")


@pytest.mark.django_db
def test_selector_excluye_torre_oc_false(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """E1 (oc=False) NO debe aparecer en el selector (opt-in real)."""
    resp = _ctx(authenticated_client, proyecto_i149)
    ids = [t.id for t in resp.context['torres_disponibles']]
    assert torres_i149['e1'].id not in ids, (
        "E1 (oc=False) NO debe aparecer en el selector.")


# ===========================================================================
# Bug (b) — tabla de obras filtra por aplica_obras_proteccion
# ===========================================================================

@pytest.mark.django_db
def test_tabla_obras_excluye_oc_false_con_obra_preexistente(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """E1 (oc=False) con TrinchoCuneta preexistente NO debe salir en la tabla.

    Antes del fix la tabla 'obras' no filtraba por aplica_obras_proteccion.
    """
    resp = _ctx(authenticated_client, proyecto_i149)
    obras_torre_ids = [o.torre_id for o in resp.context['obras']]
    assert torres_i149['e1'].id not in obras_torre_ids, (
        "E1 (oc=False) con obra preexistente NO debe aparecer en la tabla.")


@pytest.mark.django_db
def test_tabla_obras_incluye_oc_true_con_obra(
        authenticated_client, proyecto_i149, torres_i149, sqlite_regexp_replace):
    """Una torre oc=True con obra creada SÍ debe seguir apareciendo en la tabla
    (test contra dato legacy: la obra de E19 existía antes del cambio)."""
    from apps.construccion.models import TrinchoCuneta
    # E19 tiene oc=True; le creamos una obra (simula dato legacy preexistente).
    TrinchoCuneta.objects.create(
        proyecto=proyecto_i149, torre=torres_i149['e19'],
        medida_manejo=TrinchoCuneta.TipoObra.TRINCHO,
    )
    resp = _ctx(authenticated_client, proyecto_i149)
    obras_torre_ids = [o.torre_id for o in resp.context['obras']]
    assert torres_i149['e19'].id in obras_torre_ids, (
        "E19 (oc=True) con obra debe seguir visible en la tabla.")
