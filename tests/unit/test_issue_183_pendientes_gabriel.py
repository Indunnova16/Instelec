"""Instelec#183 — 3 pendientes puntuales de la revisión en vivo con Gabriel
Valencia (2026-07-17), sobre trabajo ya deployado del mismo issue.

Reproceso (bounce #1, FIX_INCOMPLETO): el cierre 2026-07-13 v2 ("Freeze-header
resuelto de raíz (v2) en las 13 tablas") barrió el patrón por módulo top-level
sin verificar que `spt_pintura_index.html` -- template hermano dentro del mismo
grupo de navbar "Montaje" -- tuviera su propia tabla cubierta. Este archivo
también cubre los otros 2 hallazgos de la misma sesión en vivo:

1. `templates/components/sidebar.html`: el `<li>` "Obras de Protección" se
   reclasifica de dominio -- pasa del `<ul aria-label="Submenu Tendido
   Construccion">` al `<ul aria-label="Submenu Obra Civil Construccion">`
   (trinchos/cunetas/gaviones son obra civil, no tendido).
2. `templates/construccion/montaje_torre.html`: se elimina el
   `{% include 'construccion/_proyecto_tabs.html' %}` redundante (la
   navegación entre categorías vive en el sidebar desde el issue #71).
3. `templates/construccion/spt_pintura_index.html`: se aplica el MISMO
   mecanismo de freeze-header ya usado en tendido_matriz.html /
   actividades_finales.html / obra_civil_matriz.html (gap de cobertura del
   barrido de 13 archivos del cierre anterior).

Archivo de test por-issue (convención del repo, ver test_issue_123_*.py /
test_issue_164.py): no se apenda a tests.py ni a test_sidebar_modulos.py /
test_spt_pintura.py compartidos.
"""

import os
import re

import pytest
from django.conf import settings
from django.urls import reverse


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def proyecto_construccion_183(db):
    """Proyecto + contrato Construcción para renderizar sidebar / vistas."""
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-TEST-183",
        nombre="Contrato Pendientes #183",
        cliente="Cliente Test",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto Pendientes #183",
        estado="EJECUCION",
    )


@pytest.fixture
def torres_183(proyecto_construccion_183):
    from apps.construccion.models import TorreConstruccion

    return [
        TorreConstruccion.objects.create(
            proyecto=proyecto_construccion_183, numero=f"T-{i}", tipo="A"
        )
        for i in range(1, 3)
    ]


@pytest.fixture
def admin_client_183(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


# ==============================================================================
# 1. Sidebar: "Obras de Protección" reclasificado de Tendido -> Obra Civil
# ==============================================================================

def _extraer_ul(body, aria_label):
    """Devuelve el contenido interior del <ul aria-label="..."> ... </ul>
    (sin <ul> anidados dentro, así que el primer </ul> cierra el bloque
    correcto)."""
    m = re.search(
        rf'aria-label="Submenu {re.escape(aria_label)} Construccion">(.*?)</ul>',
        body,
        re.DOTALL,
    )
    assert m, f"No se encontró <ul aria-label=\"Submenu {aria_label} Construccion\"> en el sidebar"
    return m.group(1)


@pytest.mark.django_db
class TestSidebarObrasProteccionReclasificado183:
    """Instelec#183 (hallazgo #1 de la sesión 07-17): "Obras de Protección"
    (trinchos/cunetas/gaviones) es de dominio Obra Civil, no Tendido."""

    def _render_sidebar(self, admin_client_183, proyecto):
        url = reverse(
            "construccion:dashboard_obra_civil",
            kwargs={"proyecto_id": proyecto.id},
        )
        resp = admin_client_183.get(url)
        assert resp.status_code == 200, f"render falló: {resp.status_code}"
        return resp.content.decode("utf-8")

    def test_obras_proteccion_esta_en_obra_civil(
        self, admin_client_183, proyecto_construccion_183
    ):
        body = self._render_sidebar(admin_client_183, proyecto_construccion_183)
        ul_obra_civil = _extraer_ul(body, "Obra Civil")
        assert "catUrl('obras-proteccion')" in ul_obra_civil, (
            "El <li> de Obras de Protección no está dentro del "
            "<ul aria-label='Submenu Obra Civil Construccion'>"
        )
        assert "Obras de Protección" in ul_obra_civil

    def test_obras_proteccion_no_esta_en_tendido(
        self, admin_client_183, proyecto_construccion_183
    ):
        body = self._render_sidebar(admin_client_183, proyecto_construccion_183)
        ul_tendido = _extraer_ul(body, "Tendido")
        assert "catUrl('obras-proteccion')" not in ul_tendido, (
            "El <li> de Obras de Protección sigue dentro del "
            "<ul aria-label='Submenu Tendido Construccion'> (no se movió)"
        )
        assert "Obras de Protección" not in ul_tendido

    def test_tendido_conserva_sus_2_items_propios(
        self, admin_client_183, proyecto_construccion_183
    ):
        """El move no debe arrastrar ni romper los items propios de Tendido."""
        body = self._render_sidebar(admin_client_183, proyecto_construccion_183)
        ul_tendido = _extraer_ul(body, "Tendido")
        assert "catUrl('tendido')" in ul_tendido
        assert "catUrl('dashboard-tendido')" in ul_tendido

    def test_obra_civil_conserva_sus_items_propios(
        self, admin_client_183, proyecto_construccion_183
    ):
        body = self._render_sidebar(admin_client_183, proyecto_construccion_183)
        ul_obra_civil = _extraer_ul(body, "Obra Civil")
        assert "catUrl('obra-civil')" in ul_obra_civil
        assert "catUrl('dashboard-obra-civil')" in ul_obra_civil


# ==============================================================================
# 2. montaje_torre.html: quitar el include de tabs redundante
# ==============================================================================

@pytest.mark.django_db
class TestMontajeTorreSinTabsRedundantes183:
    """Instelec#183 (hallazgo #2): montaje_torre.html incluía
    _proyecto_tabs.html, redundante desde que la navegación vive en el
    sidebar (issue #71) -- se navega directo desde la matriz de Montaje."""

    def test_no_incluye_proyecto_tabs(
        self, admin_client_183, proyecto_construccion_183, torres_183
    ):
        url = reverse(
            "construccion:montaje_torre",
            kwargs={
                "proyecto_id": proyecto_construccion_183.id,
                "torre_id": torres_183[0].id,
            },
        )
        resp = admin_client_183.get(url)
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        # Fingerprint único de _proyecto_tabs.html (no aparece en ningún otro
        # template de construccion -- confirmado por F2/F3 con grep).
        assert "Navega entre categorías desde el panel izquierdo" not in body, (
            "montaje_torre.html sigue incluyendo _proyecto_tabs.html"
        )

    def test_resto_de_la_pagina_intacto(
        self, admin_client_183, proyecto_construccion_183, torres_183
    ):
        """El fix es quirúrgico: el resto del template no se vio afectado."""
        url = reverse(
            "construccion:montaje_torre",
            kwargs={
                "proyecto_id": proyecto_construccion_183.id,
                "torre_id": torres_183[0].id,
            },
        )
        resp = admin_client_183.get(url)
        body = resp.content.decode("utf-8")
        assert "Volver a lista" in body
        assert "Montaje" in body


# ==============================================================================
# 3. spt_pintura_index.html: gap de cobertura del freeze-header (rebote #1)
# ==============================================================================

_SPT_PINTURA_INDEX_PATH = os.path.join(
    settings.BASE_DIR, "templates", "construccion", "spt_pintura_index.html"
)
_SPT_PINTURA_TORRE_PATH = os.path.join(
    settings.BASE_DIR, "templates", "construccion", "spt_pintura_torre.html"
)


def _leer_template(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestSPTPinturaIndexFreezeHeader183:
    """Instelec#183 (hallazgo #3, REPROCESO FIX_INCOMPLETO): réplica EXACTA del
    mecanismo ya validado en tendido_matriz.html / actividades_finales.html /
    obra_civil_matriz.html -- confirmado carácter por carácter contra esos 3
    templates antes de aplicar (F2 + F3)."""

    def test_wrapper_exterior_sin_overflow_hidden(self):
        src = _leer_template(_SPT_PINTURA_INDEX_PATH)
        assert (
            'rounded-lg shadow border border-gray-200 dark:border-gray-700 overflow-hidden'
            not in src
        ), (
            "El wrapper exterior aún tiene 'overflow-hidden' -- bloquea el "
            "freeze-header (el scroll debe vivir en el div interior)."
        )
        # La clase base del wrapper se conserva (solo se quitó overflow-hidden).
        assert (
            'bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700"'
            in src
        )

    def test_div_interior_overflow_auto_max_h(self):
        src = _leer_template(_SPT_PINTURA_INDEX_PATH)
        assert '<div class="overflow-auto max-h-[70vh]">' in src, (
            "Falta 'overflow-auto max-h-[70vh]' en el div interior (mismo patrón "
            "de tendido_matriz.html/actividades_finales.html/obra_civil_matriz.html)"
        )
        assert "overflow-x-auto" not in src, (
            "El div interior sigue con el 'overflow-x-auto' viejo (sin max-h, "
            "sin overflow-y) -- el thead sticky no puede funcionar sin esto"
        )

    def test_thead_sticky(self):
        src = _leer_template(_SPT_PINTURA_INDEX_PATH)
        assert '<thead class="bg-gray-50 dark:bg-gray-900 sticky top-0 z-20">' in src, (
            "El <thead> no tiene 'sticky top-0 z-20' -- freeze-header incompleto"
        )
        # Header de 1 sola fila sin columna fija: NO necesita 'sticky left-0'
        # (a diferencia de tendido_matriz/obra_civil_matriz que sí llevan la
        # columna Torre fija).
        assert "sticky left-0" not in src

    @pytest.mark.django_db
    def test_render_smoke_freeze_header_presente(
        self, admin_client_183, proyecto_construccion_183, torres_183
    ):
        """Sanity de render real (no solo lectura estática del archivo)."""
        url = reverse(
            "construccion:spt_pintura",
            kwargs={"proyecto_id": proyecto_construccion_183.id},
        )
        resp = admin_client_183.get(url)
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "overflow-auto max-h-[70vh]" in body
        assert 'sticky top-0 z-20' in body


class TestSPTPinturaTorreNoTocado183:
    """spt_pintura_torre.html está explícitamente FUERA de scope (F1/F2): no
    tiene ninguna tabla, es un scope-note ya aclarado, no un pendiente."""

    def test_no_tiene_tabla(self):
        src = _leer_template(_SPT_PINTURA_TORRE_PATH)
        assert "<table" not in src, (
            "spt_pintura_torre.html ahora tiene una <table> -- si esto cambió, "
            "revisar si el freeze-header aplica aquí también (F2 asumió que no)"
        )
