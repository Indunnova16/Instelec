"""Tests para sidebar reestructurado (issue #73) + placeholders Fase 1."""

import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_construccion(db):
    """Crea un proyecto + contrato Construcción para tests de sidebar."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-TEST-73",
        nombre="Contrato Sidebar #73",
        cliente="Cliente Test",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto Sidebar #73",
        estado="EJECUCION",
    )


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


SIDEBAR_NUEVOS_MODULOS = [
    # (url_name, label visible en sidebar)
    ("construccion:obra_civil_lista", "Obra Civil"),
    ("construccion:dashboard_obra_civil", "Dashboard Obra Civil"),
    ("construccion:montaje_lista", "Montaje"),
    ("construccion:dashboard_montaje", "Dashboard Montaje"),
    ("construccion:spt_pintura", "SPT y Pintura"),
    ("construccion:tendido_lista", "CANT Tendido"),
    ("construccion:trinchos_cunetas", "Trinchos y Cunetas"),
    ("construccion:actividades_finales", "Actividades Finales"),
    ("construccion:indicadores_financieros", "Indicadores Financieros"),
]


@pytest.mark.django_db
class TestSidebarUrlsResuelven:
    """Issue #73: los 9 módulos del sidebar deben tener URL nombrada resoluble."""

    @pytest.mark.parametrize("url_name,_label", SIDEBAR_NUEVOS_MODULOS)
    def test_url_resuelve(self, url_name, _label, proyecto_construccion):
        url = reverse(url_name, kwargs={"proyecto_id": proyecto_construccion.id})
        assert url.startswith("/construccion/")


@pytest.mark.django_db
class TestPlaceholdersResponden200:
    """Issue #73: los 6 placeholders (módulos sin issue) deben renderizar 200."""

    PLACEHOLDERS = [
        # dashboard_obra_civil (#75) y dashboard_montaje (#77) ahora son vistas reales (Fase 3).
        # spt_pintura (#78 Fase 2C) y trinchos_cunetas (#80 Fase 2E) ahora son vistas reales.
        "construccion:actividades_finales",
        "construccion:indicadores_financieros",
    ]

    @pytest.mark.parametrize("url_name", PLACEHOLDERS)
    def test_placeholder_responde(self, url_name, admin_client, proyecto_construccion):
        url = reverse(url_name, kwargs={"proyecto_id": proyecto_construccion.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        # Mensaje del template placeholder.
        assert b"Modulo en construcc" in resp.content or b"M\xc3\xb3dulo en construcc" in resp.content

    def test_placeholder_titulo_correcto(self, admin_client, proyecto_construccion):
        url = reverse("construccion:spt_pintura", kwargs={"proyecto_id": proyecto_construccion.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert b"SPT y Pintura" in resp.content

    def test_placeholder_404_si_proyecto_no_existe(self, admin_client):
        import uuid
        url = reverse(
            "construccion:dashboard_obra_civil",
            kwargs={"proyecto_id": uuid.uuid4()},
        )
        resp = admin_client.get(url)
        assert resp.status_code == 404


@pytest.mark.django_db
class TestSidebarTemplateRendering:
    """Issue #73: el sidebar muestra los 9 items con sus labels visibles."""

    def test_sidebar_contiene_9_modulos_nuevos(self, admin_client, proyecto_construccion):
        # Cualquier vista que use base.html renderiza el sidebar.
        url = reverse(
            "construccion:dashboard_obra_civil",
            kwargs={"proyecto_id": proyecto_construccion.id},
        )
        resp = admin_client.get(url)
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        for _, label in SIDEBAR_NUEVOS_MODULOS:
            assert label in body, f"Falta etiqueta sidebar: {label!r}"

    def test_sidebar_no_contiene_modulos_viejos(self, admin_client, proyecto_construccion):
        """Los items legacy de PROYECTO ACTIVO (Sociopredial/Ambiental/Torres/Kits/etc.)
        ya no están en el sidebar tras la reestructuración."""
        url = reverse(
            "construccion:dashboard_obra_civil",
            kwargs={"proyecto_id": proyecto_construccion.id},
        )
        resp = admin_client.get(url)
        body = resp.content.decode("utf-8")
        for legacy_slug in ["catUrl('social')", "catUrl('ambiental')",
                            "catUrl('torres')", "catUrl('protecciones')",
                            "catUrl('kits')", "catUrl('cilindros')",
                            "catUrl('dashboard-financiero')"]:
            assert legacy_slug not in body, f"Sidebar aún expone item legacy: {legacy_slug}"
