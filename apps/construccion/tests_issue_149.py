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


# ===========================================================================
# Bug PRINCIPAL (bounce=3) — el LISTADO lista UNA FILA POR TORRE QUE APLICA
# (no solo las torres con obra capturada). invierte_comportamiento=True.
# ===========================================================================

@pytest.fixture
def torres_pendientes_i149(proyecto_i149):
    """Torres que aplican a Obras de Protección pero SIN obra capturada
    (escenario exacto del cliente: E19/E34 marcadas en Obra Civil, 0 obras).

    Cubre ≥2 torres distintas (generalización, raíz del reproceso #3):
      - e19 / e34: oc=True, 0 TrinchoCuneta → DEBEN salir como "Pendiente".
      - e23: oc=True, CON obra capturada (dato legacy) → sale con sus datos.
      - e1:  oc=False → NO debe salir en el listado.
    """
    from apps.construccion.models import (
        TorreConstruccion, ObraCivilTorre, TrinchoCuneta,
    )

    def _torre(num, *, oc_aplica, global_aplica=True):
        t = TorreConstruccion.objects.create(
            proyecto=proyecto_i149, numero=str(num), tipo='D6',
            aplica=global_aplica,
        )
        ObraCivilTorre.objects.create(
            proyecto=proyecto_i149, torre=t,
            aplica_obras_proteccion=oc_aplica,
        )
        return t

    e19 = _torre(19, oc_aplica=True)   # aplica, 0 obras → Pendiente
    e34 = _torre(34, oc_aplica=True)   # aplica, 0 obras → Pendiente (2ª torre)
    e23 = _torre(23, oc_aplica=True)   # aplica, con obra (legacy)
    e1 = _torre(1, oc_aplica=False)    # no aplica → ausente

    # Dato legacy: E23 ya tenía una obra capturada antes del cambio.
    TrinchoCuneta.objects.create(
        proyecto=proyecto_i149, torre=e23,
        medida_manejo=TrinchoCuneta.TipoObra.AMBAS,
        metros_trinchos=12, metros_cunetas=8, cuadrilla='Cuadrilla A',
        completado=True,
    )
    return {'e19': e19, 'e34': e34, 'e23': e23, 'e1': e1}


def _filas_por_torre(resp):
    return {f['torre'].id: f for f in resp.context['filas']}


@pytest.mark.django_db
def test_listado_lista_torres_que_aplican_sin_obra(
        authenticated_client, proyecto_i149, torres_pendientes_i149,
        sqlite_regexp_replace):
    """REPRODUCE EL BUG (bounce=3): E19 y E34 aplican pero tienen 0 obras
    capturadas. ANTES del fix estaban ausentes del listado (que solo iteraba
    TrinchoCuneta). AHORA deben aparecer como filas 'Pendiente'.

    Cubre ≥2 torres (E19 + E34) para generalizar (raíz #3: no validar 1 sola).
    """
    resp = _ctx(authenticated_client, proyecto_i149)
    filas = _filas_por_torre(resp)
    for clave in ('e19', 'e34'):
        torre = torres_pendientes_i149[clave]
        assert torre.id in filas, (
            f"{torre.numero_display} (aplica=True, 0 obras) DEBE aparecer en el "
            "listado como fila pendiente — es lo que el cliente reclama.")
        assert filas[torre.id]['obra'] is None, (
            f"{torre.numero_display} no tiene obra capturada → obra=None "
            "(fila placeholder Pendiente).")


@pytest.mark.django_db
def test_listado_renderiza_torre_pendiente_en_html(
        authenticated_client, proyecto_i149, torres_pendientes_i149,
        sqlite_regexp_replace):
    """El observable que VE el cliente: la etiqueta T-19 (y T-34) presentes en
    el HTML renderizado del módulo + el marcador 'Pendiente' / 'Capturar'."""
    resp = _ctx(authenticated_client, proyecto_i149)
    html = resp.content.decode()
    assert 'T-19' in html, "T-19 debe estar en el HTML del listado."
    assert 'T-34' in html, "T-34 debe estar en el HTML del listado."
    assert 'Capturar' in html, (
        "Las torres pendientes deben ofrecer la acción 'Capturar'.")


@pytest.mark.django_db
def test_listado_incluye_torre_legacy_con_sus_datos(
        authenticated_client, proyecto_i149, torres_pendientes_i149,
        sqlite_regexp_replace):
    """Dato legacy: E23 (oc=True, con obra capturada antes del cambio) sigue
    apareciendo CON su obra (no se rompe el caso ya existente)."""
    resp = _ctx(authenticated_client, proyecto_i149)
    filas = _filas_por_torre(resp)
    e23 = torres_pendientes_i149['e23']
    assert e23.id in filas, "E23 (con obra) debe seguir en el listado."
    obra = filas[e23.id]['obra']
    assert obra is not None, "E23 conserva su obra capturada en la fila."
    assert obra.completado is True
    assert obra.cuadrilla == 'Cuadrilla A'


@pytest.mark.django_db
def test_listado_excluye_torre_que_no_aplica(
        authenticated_client, proyecto_i149, torres_pendientes_i149,
        sqlite_regexp_replace):
    """E1 (oc=False) NO debe aparecer como fila en el listado (opt-in real)."""
    resp = _ctx(authenticated_client, proyecto_i149)
    filas = _filas_por_torre(resp)
    assert torres_pendientes_i149['e1'].id not in filas, (
        "E1 (oc=False) no debe aparecer en el listado.")


@pytest.mark.django_db
def test_contadores_pendientes(
        authenticated_client, proyecto_i149, torres_pendientes_i149,
        sqlite_regexp_replace):
    """Los contadores del header reflejan torres que aplican vs capturadas."""
    resp = _ctx(authenticated_client, proyecto_i149)
    # 3 torres aplican (e19, e34, e23); 1 con obra capturada (e23) → 2 pendientes.
    assert resp.context['total_torres'] == 3
    assert resp.context['pendientes'] == 2
    assert len(resp.context['obras']) == 1


# ===========================================================================
# Rename de ruta — /trinchos-cunetas/ → /obras-proteccion/ (301)
# ===========================================================================

@pytest.mark.django_db
def test_ruta_nueva_obras_proteccion_resuelve(
        authenticated_client, proyecto_i149, torres_pendientes_i149,
        sqlite_regexp_replace):
    """La ruta canónica nueva /obras-proteccion/ responde 200 (name= intacto)."""
    url = reverse('construccion:trinchos_cunetas',
                  kwargs={'proyecto_id': proyecto_i149.id})
    assert url.endswith('/obras-proteccion/'), (
        f"El reverse debe apuntar a la ruta nueva, no a {url!r}.")
    resp = authenticated_client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_ruta_vieja_trinchos_cunetas_redirige(
        authenticated_client, proyecto_i149):
    """El path viejo /trinchos-cunetas/ redirige 301 a /obras-proteccion/
    (no rompe backlinks/bookmarks que el cliente tenga guardados)."""
    vieja = f'/construccion/{proyecto_i149.id}/trinchos-cunetas/'
    resp = authenticated_client.get(vieja)
    assert resp.status_code in (301, 302), (
        f"La ruta vieja debe redirigir, status={resp.status_code}.")
    assert '/obras-proteccion/' in resp['Location'], (
        f"Debe redirigir a la ruta nueva, Location={resp.get('Location')!r}.")


@pytest.mark.django_db
def test_ruta_vieja_upsert_redirige(authenticated_client, proyecto_i149):
    """El path viejo /trinchos-cunetas/upsert/ redirige a /obras-proteccion/upsert/."""
    vieja = f'/construccion/{proyecto_i149.id}/trinchos-cunetas/upsert/'
    resp = authenticated_client.get(vieja)
    assert resp.status_code in (301, 302)
    assert '/obras-proteccion/upsert/' in resp['Location']
