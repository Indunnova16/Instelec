from datetime import date
from decimal import Decimal

import pytest

from apps.financiero.models import Banco, ConciliacionBancaria, MovimientoBancario


@pytest.fixture
def conciliaciones_reportes(db):
    banco_uno = Banco.objects.create(nombre="Banco Reportes Uno")
    banco_dos = Banco.objects.create(nombre="Banco Reportes Dos")

    def crear(banco, referencia, fecha, estado, monto, diferencia=Decimal("0.00")):
        movimiento = MovimientoBancario.objects.create(
            banco=banco,
            referencia=referencia,
            fecha=fecha,
            descripcion="Movimiento de prueba",
            monto=monto,
            tipo=MovimientoBancario.Tipo.TRANSFERENCIA,
        )
        return ConciliacionBancaria.objects.create(
            movimiento=movimiento, estado=estado, diferencia=diferencia
        )

    return {
        "banco_uno": banco_uno,
        "banco_dos": banco_dos,
        "conciliada": crear(
            banco_uno,
            "CONCILIADA-250",
            date(2026, 9, 2),
            ConciliacionBancaria.Estado.CONCILIADA,
            Decimal("100.00"),
        ),
        "diferencia": crear(
            banco_uno,
            "DIFERENCIA-250",
            date(2026, 9, 5),
            ConciliacionBancaria.Estado.DIFERENCIA,
            Decimal("80.00"),
            Decimal("-20.00"),
        ),
        "pendiente": crear(
            banco_dos,
            "PENDIENTE-250",
            date(2026, 9, 8),
            ConciliacionBancaria.Estado.PENDIENTE,
            Decimal("50.00"),
        ),
    }


@pytest.mark.django_db
class TestB2ConciliacionReportes:
    def test_B2_estado_porcentaje(self, client, admin_user, conciliaciones_reportes):
        client.force_login(admin_user)
        response = client.get("/financiero/conciliacion/estado/")

        assert response.status_code == 200
        assert response.context["resumen"]["total"] == Decimal("3")
        assert response.context["resumen"]["conciliadas"] == Decimal("1")
        assert response.context["porcentaje_conciliado"] == Decimal("100") / Decimal("3")

        banco = conciliaciones_reportes["banco_uno"]
        response = client.get(f"/financiero/conciliacion/estado/?banco={banco.pk}")
        assert response.context["resumen"]["total"] == Decimal("2")
        assert response.context["porcentaje_conciliado"] == Decimal("50")

    def test_B2_historial_diferencias(self, client, admin_user, conciliaciones_reportes):
        client.force_login(admin_user)
        historial = client.get(
            "/financiero/conciliacion/historial/?fecha_inicio=2026-09-03&fecha_fin=2026-09-06"
        )
        assert historial.status_code == 200
        assert list(historial.context["conciliaciones"]) == [conciliaciones_reportes["diferencia"]]

        diferencias = client.get("/financiero/conciliacion/diferencias/")
        assert diferencias.status_code == 200
        assert list(diferencias.context["conciliaciones"]) == [
            conciliaciones_reportes["diferencia"]
        ]

        fechas_invalidas = client.get(
            "/financiero/conciliacion/diferencias/?fecha_inicio=2026-09-10&fecha_fin=2026-09-01"
        )
        assert fechas_invalidas.status_code == 200
        assert "fecha inicial" in fechas_invalidas.content.decode().lower()

    def test_B2_export_csv(self, client, admin_user, conciliaciones_reportes):
        client.force_login(admin_user)
        banco = conciliaciones_reportes["banco_uno"]
        response = client.get(f"/financiero/conciliacion/exportar/?banco={banco.pk}")

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        body = response.content.decode("utf-8-sig")
        assert "DIFERENCIA-250" in body
        assert "CONCILIADA-250" in body
        assert "PENDIENTE-250" not in body

        invalid_bank = client.get("/financiero/conciliacion/exportar/?banco=no-es-uuid")
        assert invalid_bank.status_code == 400
        assert "banco seleccionado" in invalid_bank.content.decode().lower()
