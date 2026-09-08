from decimal import Decimal

import pytest
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.models_pc import EjecucionSemanalCuadrilla, ProgramacionSemanalCuadrilla
from apps.cuadrillas.services_produccion_analisis import (
    ESTADO_DISPONIBLE,
    ESTADO_SIN_BASE,
    ESTADO_SIN_DATO,
    calcular_varianza_pct,
    construir_analisis,
)


@pytest.fixture
def programacion_analisis(db):
    cuadrilla = Cuadrilla.objects.create(codigo="ANA-252", nombre="Cuadrilla análisis")
    return ProgramacionSemanalCuadrilla.objects.create(
        cuadrilla=cuadrilla,
        anio=2026,
        semana=37,
        torres_programadas=10,
        actividades_programadas="Montaje de estructuras",
    )


@pytest.mark.django_db
def test_analisis_de_programacion_existente(admin_user, client, programacion_analisis):
    EjecucionSemanalCuadrilla.objects.create(
        programacion=programacion_analisis,
        torres_ejecutadas=8,
    )
    client.force_login(admin_user)

    response = client.get(
        reverse("construccion:produccion_diaria_analisis", args=[programacion_analisis.pk])
    )

    assert response.status_code == 200
    assert response.context["analisis"]["estado_torres"] == ESTADO_DISPONIBLE
    assert response.context["analisis"]["varianza_torres_pct"] == Decimal("-20.00")
    assert 'id="produccion-diaria-analisis"' in response.content.decode()


@pytest.mark.django_db
def test_analisis_sin_ejecucion_expone_sin_dato(programacion_analisis):
    analisis = construir_analisis(programacion_analisis)

    assert analisis["estado_torres"] == ESTADO_SIN_DATO
    assert analisis["torres_ejecutadas"] is None
    assert analisis["varianza_torres_pct"] is None


@pytest.mark.django_db
def test_analisis_sin_torres_programadas_no_divide_por_cero(programacion_analisis):
    programacion_analisis.torres_programadas = 0
    programacion_analisis.save(update_fields=["torres_programadas"])
    EjecucionSemanalCuadrilla.objects.create(
        programacion=programacion_analisis, torres_ejecutadas=3
    )

    analisis = construir_analisis(programacion_analisis)

    assert analisis["estado_torres"] == ESTADO_SIN_BASE
    assert calcular_varianza_pct(3, 0) is None
