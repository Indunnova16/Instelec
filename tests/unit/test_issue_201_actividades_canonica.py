"""Regression coverage for the canonical activities listing (issue #201)."""

from datetime import date

import pytest
from django.urls import reverse

from tests.factories import ActividadFactory


@pytest.mark.django_db
class TestProgramacionBusquedaGlobal:
    def test_sin_busqueda_usa_el_mes_actual_como_contexto(self, authenticated_client):
        actividad = ActividadFactory(
            aviso_sap="AVISO-CONTEXTO",
            fecha_programada=date.today().replace(day=15),
        )

        response = authenticated_client.get(reverse("actividades:programacion"))

        assert response.status_code == 200
        assert response.context["selected_mes"] == date.today().month
        assert response.context["selected_anio"] == date.today().year
        assert "AVISO-CONTEXTO" in response.content.decode()
        assert actividad in response.context["actividades"]

    def test_busqueda_por_aviso_encuentra_actividad_historica(self, authenticated_client):
        ActividadFactory(
            aviso_sap="AVISO-ACTUAL",
            fecha_programada=date.today().replace(day=15),
        )
        historica = ActividadFactory(
            aviso_sap="AVISO-HISTORICO-LEGACY",
            fecha_programada=date(2024, 1, 15),
        )

        response = authenticated_client.get(
            reverse("actividades:programacion"),
            {"buscar_aviso": "HISTORICO-LEGACY"},
        )

        assert response.status_code == 200
        assert "AVISO-HISTORICO-LEGACY" in response.content.decode()
        assert list(response.context["actividades"]) == [historica]

    def test_busqueda_por_aviso_inexistente_renderiza_estado_vacio(self, authenticated_client):
        response = authenticated_client.get(
            reverse("actividades:programacion"),
            {"buscar_aviso": "NO-EXISTE-201"},
        )

        assert response.status_code == 200
        assert not list(response.context["actividades"])
        assert "No hay avisos" in response.content.decode()
