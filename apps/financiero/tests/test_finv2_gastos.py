from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.contratos.models import Contrato
from apps.financiero.models import Banco, FacturaGasto, MetodoPago, Proveedor
from apps.financiero.services_finv2_gastos import calcular_totales


@pytest.fixture
def gasto_base(db):
    contrato = Contrato.objects.create(
        codigo="GASTO-248",
        nombre="Contrato gasto",
        unidad_negocio="MANTENIMIENTO",
    )
    proveedor = Proveedor.objects.create(nombre="Proveedor QA", nit="900248001")
    banco = Banco.objects.create(nombre="Banco QA")
    metodo = MetodoPago.objects.create(nombre="Transferencia QA")
    return {"contrato": contrato, "proveedor": proveedor, "banco": banco, "metodo": metodo}


@pytest.mark.django_db
class TestB1Gastos:
    def test_B1_gasto_umbral_aprobacion(self, client, admin_user, gasto_base):
        client.force_login(admin_user)
        response = client.post(
            "/financiero/facturas-gastos/nueva/",
            {
                "proveedor": gasto_base["proveedor"].pk,
                "contrato": gasto_base["contrato"].pk,
                "numero_documento": "FG-UMBRAL-1",
                "fecha": "2026-09-08",
                "concepto": "Servicio especializado",
                "categoria": "Servicios",
                "subtotal": "1000000.00",
            },
            follow=True,
        )
        assert response.status_code == 200
        factura = FacturaGasto.objects.get(numero_documento="FG-UMBRAL-1")
        assert factura.iva == Decimal("190000.00")
        assert factura.total == Decimal("1190000.00")
        assert factura.estado == FacturaGasto.Estado.PENDIENTE_APROBACION

        response = client.post(
            f"/financiero/facturas-gastos/{factura.pk}/",
            {
                "accion": "aprobar",
                "comentario_decision": "Aprobación de dirección",
            },
            follow=True,
        )
        assert response.status_code == 200
        factura.refresh_from_db()
        assert factura.estado == FacturaGasto.Estado.PENDIENTE_PAGO

    def test_B1_gasto_pago_referencia(self, client, admin_user, gasto_base):
        client.force_login(admin_user)
        factura = FacturaGasto.objects.create(
            proveedor=gasto_base["proveedor"],
            contrato=gasto_base["contrato"],
            numero_documento="FG-PAGO-1",
            fecha=date(2026, 9, 8),
            concepto="Materiales",
            categoria="Materiales",
            subtotal=Decimal("100.00"),
            iva=Decimal("19.00"),
            total=Decimal("119.00"),
            estado=FacturaGasto.Estado.PENDIENTE_PAGO,
        )
        response = client.post(
            f"/financiero/facturas-gastos/{factura.pk}/",
            {
                "accion": "pagar",
                "banco": gasto_base["banco"].pk,
                "metodo_pago": gasto_base["metodo"].pk,
                "fecha": "2026-09-08",
                "monto": "119.00",
                "referencia": "TRX-248",
            },
            follow=True,
        )
        assert response.status_code == 200
        factura.refresh_from_db()
        assert factura.estado == FacturaGasto.Estado.PAGADA
        assert factura.referencia_pago == "TRX-248"
        assert factura.pagos.get().monto == Decimal("119.00")

    def test_gasto_rechaza_pago_parcial(self, client, admin_user, gasto_base):
        client.force_login(admin_user)
        factura = FacturaGasto.objects.create(
            proveedor=gasto_base["proveedor"],
            contrato=gasto_base["contrato"],
            numero_documento="FG-PARCIAL-1",
            fecha=date(2026, 9, 8),
            concepto="Materiales",
            categoria="Materiales",
            subtotal=Decimal("100.00"),
            iva=Decimal("19.00"),
            total=Decimal("119.00"),
            estado=FacturaGasto.Estado.PENDIENTE_PAGO,
        )
        client.post(
            f"/financiero/facturas-gastos/{factura.pk}/",
            {
                "accion": "pagar",
                "banco": gasto_base["banco"].pk,
                "metodo_pago": gasto_base["metodo"].pk,
                "fecha": "2026-09-08",
                "monto": "100.00",
                "referencia": "TRX-PARCIAL",
            },
        )
        factura.refresh_from_db()
        assert factura.estado == FacturaGasto.Estado.PENDIENTE_PAGO
        assert not factura.pagos.exists()

    def test_gasto_rechaza_tasa_iva_invalida(self):
        with pytest.raises(ValidationError):
            calcular_totales("100", tasa_iva=Decimal("1.01"))
