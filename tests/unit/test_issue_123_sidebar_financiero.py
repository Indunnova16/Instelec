"""Issue #123 — el sidebar de Construcción debe incluir el bloque Financiero (B4).

Antes de #123 la sección Construcción del sidebar (``<template x-if="modulo ===
'construccion'">`` en ``templates/components/sidebar.html``) NO tenía ningún
enlace Financiero, aunque las 6 rutas de ``apps/construccion/urls_fin.py`` ya
existían en prod. Este test verifica que el submenú expandible "Financiero" con
sus 6 sub-links (que apuntan a las rutas NUEVAS ``catUrl('financiero/<sub>')``,
no al grid legacy ``catUrl('financiero')``) está presente en el sidebar
renderizado.

Archivo de test por-issue (RUN con hermanos): NO se apenda al
``tests/unit/test_sidebar_modulos.py`` compartido para evitar colisión de merge.
"""

import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_construccion_123(db):
    """Proyecto + contrato Construcción para renderizar el sidebar."""
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-TEST-123",
        nombre="Contrato Sidebar #123",
        cliente="Cliente Test",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto Sidebar #123",
        estado="EJECUCION",
    )


@pytest.fixture
def admin_client_123(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


# Los 6 sub-links del bloque Financiero, en el orden de urls_fin.py.
# Cada uno apunta a la ruta NUEVA del módulo financiero de construcción
# (sub-path /financiero/<x>/), NO al grid legacy /financiero/ a secas.
FINANCIERO_SLUGS = [
    "catUrl('financiero/dashboard')",
    "catUrl('financiero/presupuesto-planeado')",
    "catUrl('financiero/presupuesto-real')",
    "catUrl('financiero/costos')",
    "catUrl('financiero/nomina')",
    "catUrl('financiero/facturacion')",
]

FINANCIERO_LABELS = [
    "Dashboard",
    "Presupuesto Planeado",
    "Presupuesto Real",
    "Costos",
    "Nómina",
    "Facturación",
]


@pytest.mark.django_db
class TestSidebarConstruccionFinanciero:
    """Issue #123: el sidebar de Construcción expone el bloque Financiero."""

    def _render_sidebar(self, admin_client_123, proyecto):
        """Cualquier vista de construcción que use base.html renderiza el sidebar."""
        url = reverse(
            "construccion:dashboard_obra_civil",
            kwargs={"proyecto_id": proyecto.id},
        )
        resp = admin_client_123.get(url)
        assert resp.status_code == 200, f"render falló: {resp.status_code}"
        return resp.content.decode("utf-8")

    def test_sidebar_tiene_label_financiero(self, admin_client_123, proyecto_construccion_123):
        body = self._render_sidebar(admin_client_123, proyecto_construccion_123)
        # El menú de Construcción debe contener un item "Financiero".
        # (en #73 no estaba; sí existe en Mantenimiento, pero esa sección está
        #  gateada por x-show modulo==='mantenimiento' y no se renderiza en construccion)
        assert "Financiero" in body, "Falta el bloque Financiero en el sidebar de Construcción"

    @pytest.mark.parametrize("slug", FINANCIERO_SLUGS)
    def test_sidebar_tiene_los_6_slugs_nuevos(
        self, slug, admin_client_123, proyecto_construccion_123
    ):
        body = self._render_sidebar(admin_client_123, proyecto_construccion_123)
        assert slug in body, f"Falta el sub-link Financiero: {slug!r}"

    @pytest.mark.parametrize("label", FINANCIERO_LABELS)
    def test_sidebar_tiene_los_6_labels(self, label, admin_client_123, proyecto_construccion_123):
        body = self._render_sidebar(admin_client_123, proyecto_construccion_123)
        assert label in body, f"Falta el label Financiero: {label!r}"

    def test_sidebar_no_usa_grid_legacy(self, admin_client_123, proyecto_construccion_123):
        """El fix apunta a las rutas NUEVAS, no al grid financiero legacy
        ``catUrl('financiero')`` (sin sub-path). Asegura que no se reintrodujo."""
        body = self._render_sidebar(admin_client_123, proyecto_construccion_123)
        assert "catUrl('financiero')" not in body, (
            "El sidebar de Construcción apunta al financiero legacy en vez de los sub-módulos B4"
        )

    def test_urls_financiero_construccion_resuelven(self, proyecto_construccion_123):
        """Las 6 rutas que el menú referencia existen (urls_fin.py)."""
        for name in [
            "construccion:fin_dashboard",
            "construccion:fin_presupuesto_planeado",
            "construccion:fin_presupuesto_real",
            "construccion:fin_nomina",
            "construccion:fin_costos",
            "construccion:fin_facturacion",
        ]:
            url = reverse(name, kwargs={"proyecto_id": proyecto_construccion_123.id})
            assert url.startswith("/construccion/"), f"{name} no resuelve: {url}"
