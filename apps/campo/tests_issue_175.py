"""Issue #175 — Filtro "Tipo de Daño" causaba HTTP 500 en el listado.

Root cause (confirmado por F2 en vivo contra prod, con traceback de Cloud
Run): ``ReportesDanoListView.get_queryset()`` (``apps/campo/views.py:361``)
ejecutaba ``qs.filter(tipo=tipo)``, pero ``ReporteDano`` no tiene un campo
``tipo`` — solo ``tipo_dano``. Cualquier usuario que seleccionara una opción
del ``<select name="tipo">`` (auto-submit ``onchange``) en
``/campo/reportes-dano/`` recibía un ``django.core.exceptions.FieldError``
envuelto en un HTTP 500. El mapa (``ReportesDanoMapaPartialView``) ya usaba
el patrón correcto (``tipo_dano=tipo``) y no se toca.

Bounce=1: la entrega anterior (A4) validó pines + filtro de severidad en el
mapa, pero nunca ejercitó el filtro "Tipo de Daño" del LISTADO en el
navegador real (solo existía cobertura del endpoint JSON del mapa). Este
archivo cierra ese gap exacto para el listado.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.campo.models import ReporteDano
from tests.factories import ReporteDanoFactory


@pytest.mark.django_db
class TestReportesDanoListViewFiltroTipo:
    """Fix de 1 línea: ``qs.filter(tipo=tipo)`` -> ``qs.filter(tipo_dano=tipo)``."""

    def test_filtro_tipo_no_revienta_y_devuelve_200(self, authenticated_client):
        """Regresión directa del bug: antes del fix esto era un HTTP 500
        (FieldError: Cannot resolve keyword 'tipo' into field)."""
        ReporteDanoFactory(tipo_dano=ReporteDano.TipoDano.ELECTRICO)

        url = reverse("campo:reportes_dano")
        resp = authenticated_client.get(url, {"tipo": ReporteDano.TipoDano.ELECTRICO})

        assert resp.status_code == 200

    def test_filtro_tipo_electrico_devuelve_solo_esos_reportes(self, authenticated_client):
        """Réplica local de los valores reales de prod confirmados por F2
        (ELECTRICO=3, ESTRUCTURAL=2 en BD prod) con conteos equivalentes."""
        ReporteDanoFactory.create_batch(3, tipo_dano=ReporteDano.TipoDano.ELECTRICO)
        ReporteDanoFactory.create_batch(2, tipo_dano=ReporteDano.TipoDano.ESTRUCTURAL)

        url = reverse("campo:reportes_dano")
        resp = authenticated_client.get(url, {"tipo": ReporteDano.TipoDano.ELECTRICO})

        assert resp.status_code == 200
        reportes = list(resp.context["reportes"])
        assert len(reportes) == 3
        assert all(r.tipo_dano == ReporteDano.TipoDano.ELECTRICO for r in reportes)

    def test_filtro_tipo_estructural_devuelve_solo_esos_reportes(self, authenticated_client):
        """Segundo valor distinto (ESTRUCTURAL) — confirma que el filtro
        realmente discrimina por tipo_dano, no solo que no revienta."""
        ReporteDanoFactory.create_batch(3, tipo_dano=ReporteDano.TipoDano.ELECTRICO)
        ReporteDanoFactory.create_batch(2, tipo_dano=ReporteDano.TipoDano.ESTRUCTURAL)

        url = reverse("campo:reportes_dano")
        resp = authenticated_client.get(url, {"tipo": ReporteDano.TipoDano.ESTRUCTURAL})

        assert resp.status_code == 200
        reportes = list(resp.context["reportes"])
        assert len(reportes) == 2
        assert all(r.tipo_dano == ReporteDano.TipoDano.ESTRUCTURAL for r in reportes)

    def test_listado_sin_filtro_sigue_devolviendo_todos(self, authenticated_client):
        """Regresión: el listado sin el parámetro ``tipo`` no debe verse
        afectado por el fix — sigue devolviendo todos los reportes."""
        ReporteDanoFactory.create_batch(3, tipo_dano=ReporteDano.TipoDano.ELECTRICO)
        ReporteDanoFactory.create_batch(2, tipo_dano=ReporteDano.TipoDano.ESTRUCTURAL)

        url = reverse("campo:reportes_dano")
        resp = authenticated_client.get(url)

        assert resp.status_code == 200
        reportes = list(resp.context["reportes"])
        assert len(reportes) == 5

    def test_filtro_tipo_combinado_con_severidad_sigue_funcionando(self, authenticated_client):
        """Regresión: los otros filtros (línea/severidad) del mismo
        get_queryset no se tocaron y siguen combinándose correctamente."""
        ReporteDanoFactory(
            tipo_dano=ReporteDano.TipoDano.ELECTRICO,
            severidad=ReporteDano.Severidad.ALTA,
        )
        ReporteDanoFactory(
            tipo_dano=ReporteDano.TipoDano.ELECTRICO,
            severidad=ReporteDano.Severidad.BAJA,
        )

        url = reverse("campo:reportes_dano")
        resp = authenticated_client.get(
            url, {"tipo": ReporteDano.TipoDano.ELECTRICO, "severidad": ReporteDano.Severidad.ALTA}
        )

        assert resp.status_code == 200
        reportes = list(resp.context["reportes"])
        assert len(reportes) == 1
        assert reportes[0].severidad == ReporteDano.Severidad.ALTA
