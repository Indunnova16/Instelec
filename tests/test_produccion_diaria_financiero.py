"""Contrato del adaptador financiero de Producción Diaria (#252, B4)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.cuadrillas.models import Cuadrilla, PersonalCuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import (
    ActividadProduccion,
    MaterialProduccion,
    ProduccionDiaria,
    RegistroPersonalProduccion,
)
from apps.financiero.services_produccion_diaria import (
    agregado_financiero_periodo,
    agregado_financiero_produccion,
)


def _produccion(fecha=date(2026, 9, 8)):
    cuadrilla = Cuadrilla.objects.create(
        codigo=f"B4-{fecha:%Y%m%d}", nombre="Cuadrilla B4", activa=True
    )
    programacion = ProgramacionSemanalCuadrilla.objects.create(
        cuadrilla=cuadrilla, anio=fecha.isocalendar().year, semana=fecha.isocalendar().week
    )
    return ProduccionDiaria.objects.create(programacion=programacion, fecha=fecha)


@pytest.mark.django_db
class TestProduccionDiariaFinanciero:
    def test_detalle_preserva_valores_agregables(self):
        produccion = _produccion()
        persona = PersonalCuadrilla.objects.create(
            nombre="Persona B4", documento="B4-001", salario_base=Decimal("2400000")
        )
        RegistroPersonalProduccion.objects.create(
            produccion=produccion, personal=persona, horas_trabajadas=Decimal("8")
        )
        MaterialProduccion.objects.create(
            produccion=produccion,
            descripcion="Cable",
            cantidad=Decimal("3"),
            costo_unitario_estimado=Decimal("125"),
        )
        ActividadProduccion.objects.create(
            produccion=produccion, descripcion="Tendido", avance_pct=Decimal("60")
        )

        resumen = agregado_financiero_produccion(produccion)

        assert resumen["produccion_id"] == produccion.pk
        assert resumen["horas_trabajadas"] == Decimal("8")
        assert resumen["costo_nomina"] == Decimal("80000")
        assert resumen["costo_materiales"] == Decimal("375")
        assert resumen["costo_total_estimado"] == Decimal("80375")
        assert resumen["actividades"] == [
            {
                "id": resumen["actividades"][0]["id"],
                "descripcion": "Tendido",
                "avance_pct": Decimal("60"),
                "observacion": "",
            }
        ]

    def test_periodo_es_idempotente_y_excluye_fechas_fuera_del_rango(self):
        produccion = _produccion()
        MaterialProduccion.objects.create(
            produccion=produccion,
            descripcion="Conector",
            cantidad=Decimal("2"),
            costo_unitario_estimado=Decimal("5"),
        )
        _produccion(date(2026, 9, 20))

        primero = agregado_financiero_periodo(
            fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 10)
        )
        segundo = agregado_financiero_periodo(
            fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 10)
        )

        assert primero == segundo
        assert primero["cantidad_producciones"] == 1
        assert primero["costo_materiales"] == Decimal("10")
        assert ProduccionDiaria.objects.count() == 2

    def test_periodo_vacio_y_fechas_invertidas_son_explicitos(self):
        vacio = agregado_financiero_periodo(
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 2)
        )

        assert vacio["cantidad_producciones"] == 0
        assert vacio["costo_total_estimado"] == Decimal("0")
        assert vacio["actividades"] == []
        with pytest.raises(ValueError, match="fecha_inicio"):
            agregado_financiero_periodo(fecha_inicio=date(2026, 1, 2), fecha_fin=date(2026, 1, 1))
