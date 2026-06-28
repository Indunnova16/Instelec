"""Tests Trinchos y Cunetas (issue #80)."""

import re
from decimal import Decimal

import pytest
from django.db import connection
from django.urls import reverse


@pytest.fixture
def sqlite_regexp_replace():
    """Shim de regexp_replace para sqlite (dev_lite); en Postgres es nativa.

    ordenar_torres_construccion usa la función Postgres regexp_replace que el
    backend sqlite local no trae. Permite ejercer el render del listado.
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

from apps.contratos.models import Contrato
from apps.construccion.models import (
    ObraCivilTorre, ProyectoConstruccion, TorreConstruccion, TrinchoCuneta,
)


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-TRC-80", nombre="Trinchos", cliente="C",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre="Trinchos", estado="EJECUCION",
    )


@pytest.fixture
def torres(proyecto):
    return [
        TorreConstruccion.objects.create(proyecto=proyecto, numero=f"T{i:03d}", tipo="A")
        for i in (4, 19, 33, 50)
    ]


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestTrinchoCunetaModel:
    def test_total_metros_obra(self, proyecto, torres):
        o = TrinchoCuneta.objects.create(
            proyecto=proyecto, torre=torres[0],
            medida_manejo=TrinchoCuneta.TipoObra.AMBAS,
            metros_trinchos=Decimal("27.5"), metros_cunetas=Decimal("10"),
        )
        assert o.total_metros_obra == Decimal("37.5")

    def test_estado_completo(self, proyecto, torres):
        o = TrinchoCuneta.objects.create(
            proyecto=proyecto, torre=torres[0],
            medida_manejo=TrinchoCuneta.TipoObra.CUNETA,
            metros_cunetas=Decimal("15"), completado=True,
        )
        assert o.estado == "Completo"

    def test_unique_proyecto_torre(self, proyecto, torres):
        TrinchoCuneta.objects.create(
            proyecto=proyecto, torre=torres[0],
            medida_manejo=TrinchoCuneta.TipoObra.CUNETA, metros_cunetas=Decimal("10"),
        )
        with pytest.raises(Exception):
            TrinchoCuneta.objects.create(
                proyecto=proyecto, torre=torres[0],
                medida_manejo=TrinchoCuneta.TipoObra.TRINCHO, metros_trinchos=Decimal("5"),
            )


@pytest.mark.django_db
class TestTrinchosListView:
    def test_get_200(self, admin_client, proyecto, torres):
        url = reverse("construccion:trinchos_cunetas", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200

    def test_totales_y_resumen(self, admin_client, proyecto, torres):
        TrinchoCuneta.objects.create(
            proyecto=proyecto, torre=torres[0],
            medida_manejo=TrinchoCuneta.TipoObra.CUNETA,
            metros_cunetas=Decimal("15"), completado=True, cuadrilla="Mec",
        )
        TrinchoCuneta.objects.create(
            proyecto=proyecto, torre=torres[1],
            medida_manejo=TrinchoCuneta.TipoObra.AMBAS,
            metros_trinchos=Decimal("10"), metros_cunetas=Decimal("20"),
            cuadrilla="Angel",
        )
        url = reverse("construccion:trinchos_cunetas", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        ctx = resp.context
        assert len(ctx["obras"]) == 2
        assert ctx["total_metros"] == Decimal("45")  # 15 + 10 + 20
        assert ctx["completadas"] == 1
        assert "Mec" in ctx["por_cuadrilla"]


@pytest.mark.django_db
class TestTrinchosUpsert:
    def _url(self, p):
        return reverse("construccion:trinchos_cunetas_upsert", kwargs={"proyecto_id": p.id})

    def test_crear_cuneta(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto), {
            "torre_id": str(torres[0].id),
            "medida_manejo": "CUNETA",
            "metros_cunetas": "15.0",
            "tubo_metalico": "0", "malla_eslabonada": "0",
            "alambre_galvanizado": "0", "geotextil": "0", "cemento": "0",
            "arena": "0", "grava": "0",
            "cuadrilla": "Mec",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert TrinchoCuneta.objects.filter(torre=torres[0]).exists()

    def test_crear_trincho_sin_metros_rechaza(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto), {
            "torre_id": str(torres[0].id),
            "medida_manejo": "TRINCHO",
            # falta metros_trinchos>0
        })
        assert resp.status_code == 400
        assert "metros_trinchos" in resp.json()["error"]

    def test_crear_ambas_requiere_ambos_metros(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto), {
            "torre_id": str(torres[0].id),
            "medida_manejo": "AMBAS",
            "metros_trinchos": "10",
            # falta metros_cunetas
        })
        assert resp.status_code == 400

    def test_actualizar(self, admin_client, proyecto, torres):
        admin_client.post(self._url(proyecto), {
            "torre_id": str(torres[0].id),
            "medida_manejo": "CUNETA",
            "metros_cunetas": "15.0",
            "cuadrilla": "Mec",
        })
        # Re-post mismo torre con valores actualizados
        resp = admin_client.post(self._url(proyecto), {
            "torre_id": str(torres[0].id),
            "medida_manejo": "CUNETA",
            "metros_cunetas": "20.0",
            "cuadrilla": "Angel",
            "completado": "1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is False
        o = TrinchoCuneta.objects.get(torre=torres[0])
        assert o.metros_cunetas == Decimal("20")
        assert o.cuadrilla == "Angel"
        assert o.completado is True

    def test_material_negativo_rechaza(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto), {
            "torre_id": str(torres[0].id),
            "medida_manejo": "CUNETA",
            "metros_cunetas": "10",
            "cemento": "-5",
        })
        assert resp.status_code == 400

    def test_tipo_invalido(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto), {
            "torre_id": str(torres[0].id),
            "medida_manejo": "FANTASMA",
        })
        assert resp.status_code == 400


@pytest.mark.django_db
class TestTrinchosDelete:
    def test_delete(self, admin_client, proyecto, torres):
        obra = TrinchoCuneta.objects.create(
            proyecto=proyecto, torre=torres[0],
            medida_manejo=TrinchoCuneta.TipoObra.CUNETA, metros_cunetas=Decimal("10"),
        )
        url = reverse("construccion:trinchos_cunetas_delete",
                      kwargs={"proyecto_id": proyecto.id, "pk": obra.id})
        resp = admin_client.post(url)
        assert resp.status_code == 200
        assert not TrinchoCuneta.objects.filter(id=obra.id).exists()


@pytest.mark.django_db
class TestAplicaObrasProteccion:
    """#149 (bounce=5, HITL): la aplicabilidad por-torre aplica_obras_proteccion
    se ELIMINÓ. El módulo se rige SOLO por el flag global torre.aplica (#160).

    La columna BD queda dormida (default=True), pero ya no gobierna el listado ni
    el upsert. Estos tests asertan el comportamiento NUEVO (anti golden-stale)."""

    def test_default_true_columna_dormida(self, proyecto, torres):
        # La columna sigue existiendo (dormida, sin migración): default True.
        oc = ObraCivilTorre.objects.create(proyecto=proyecto, torre=torres[0])
        assert oc.aplica_obras_proteccion is True

    def test_listado_no_excluye_por_flag_por_torre(self, admin_client, proyecto,
                                                   torres, sqlite_regexp_replace):
        # Aunque torres[1] tenga el flag por-torre en False, AMBAS aparecen:
        # el módulo ya no se rige por aplica_obras_proteccion (solo torre.aplica).
        ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0], aplica_obras_proteccion=True)
        ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[1], aplica_obras_proteccion=False)
        url = reverse("construccion:trinchos_cunetas",
                      kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        ids = {t.id for t in resp.context["torres_disponibles"]}
        assert torres[0].id in ids
        assert torres[1].id in ids, (
            "torres[1] (flag por-torre=False) DEBE aparecer: el filtro se eliminó.")

    def test_listado_excluye_torre_anulada_global(self, admin_client, proyecto,
                                                  torres, sqlite_regexp_replace):
        # El único gobernante es torre.aplica (#160): anular globalmente excluye.
        torres[1].aplica = False
        torres[1].save(update_fields=["aplica"])
        url = reverse("construccion:trinchos_cunetas",
                      kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        ids = {t.id for t in resp.context["torres_disponibles"]}
        assert torres[0].id in ids
        assert torres[1].id not in ids, (
            "torres[1] (aplica global=False) NO debe aparecer.")

    def test_upsert_no_bloquea_por_flag_por_torre(self, admin_client, proyecto,
                                                  torres):
        # ANTES el upsert rechazaba con 400 si aplica_obras_proteccion=False.
        # AHORA el guard se eliminó → procesa la torre normalmente.
        ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0], aplica_obras_proteccion=False)
        url = reverse("construccion:trinchos_cunetas_upsert",
                      kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "torre_id": str(torres[0].id),
            "medida_manejo": "CUNETA",
            "metros_cunetas": "15.0",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert TrinchoCuneta.objects.filter(torre=torres[0]).exists()

    def test_upsert_permite_torre(self, admin_client, proyecto, torres):
        ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0], aplica_obras_proteccion=True)
        url = reverse("construccion:trinchos_cunetas_upsert",
                      kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "torre_id": str(torres[0].id),
            "medida_manejo": "CUNETA",
            "metros_cunetas": "15.0",
        })
        assert resp.status_code == 200
        assert TrinchoCuneta.objects.filter(torre=torres[0]).exists()

    def test_aplica_update_endpoint_rechaza_campo_eliminado(self, admin_client,
                                                            proyecto, torres):
        # #149 (bounce=5): aplica_obras_proteccion salió del whitelist. El
        # endpoint ahora lo rechaza (400) — el frontend ya no envía ese campo.
        ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0], aplica_obras_proteccion=True)
        url = reverse("construccion:obra_civil_aplica_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {
            "campo": "aplica_obras_proteccion", "aplica": "0"})
        assert resp.status_code == 400, (
            "El campo eliminado ya no está en CAMPOS_PERMITIDOS.")

    def test_aplica_update_endpoint_pintura_sigue_ok(self, admin_client, proyecto,
                                                     torres):
        # El toggle que QUEDA (#153 pintura aeronáutica) sigue funcionando.
        oc = ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0], aplica_pintura_aeronautica=True)
        url = reverse("construccion:obra_civil_aplica_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {
            "campo": "aplica_pintura_aeronautica", "aplica": "0"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        oc.refresh_from_db()
        assert oc.aplica_pintura_aeronautica is False

    def test_aplica_update_campo_no_permitido(self, admin_client, proyecto, torres):
        ObraCivilTorre.objects.create(proyecto=proyecto, torre=torres[0])
        url = reverse("construccion:obra_civil_aplica_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"campo": "observaciones", "aplica": "1"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestObrasProteccionFiltro149:
    """#149 (bounce=5, HITL): el listado de Obras de Protección lista TODAS las
    torres aplicables (gobernadas por torre.aplica), sin el filtro por-torre."""

    def test_listado_muestra_todas_las_torres_aplicables(
            self, admin_client, proyecto, torres, sqlite_regexp_replace):
        # NINGUNA torre tiene ObraCivilTorre al entrar (caso del cliente): todas
        # aplican (torre.aplica=True por default) → todas deben listarse.
        url = reverse("construccion:trinchos_cunetas",
                      kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        ids = {t.id for t in resp.context["torres_disponibles"]}
        for t in torres:
            assert t.id in ids
        assert resp.context["total_torres"] == len(torres)

    def test_listado_muestra_torre_con_flag_por_torre_false(
            self, admin_client, proyecto, torres, sqlite_regexp_replace):
        # Dato legacy: una torre con aplica_obras_proteccion=False (antes oculta)
        # AHORA aparece, porque el flag por-torre ya no gobierna el listado.
        ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0], aplica_obras_proteccion=False)
        url = reverse("construccion:trinchos_cunetas",
                      kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        ids = {t.id for t in resp.context["torres_disponibles"]}
        assert torres[0].id in ids, (
            "Torre con flag por-torre=False DEBE aparecer (filtro eliminado).")
        assert torres[1].id in ids
