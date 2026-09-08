"""E2E pytest de maestros y cartera financiera v2 (#248, #249)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.contratos.models import Contrato
from apps.financiero.models import CicloFacturacion, FacturaGasto, Presupuesto, Proveedor
from apps.lineas.models import Linea


@pytest.fixture
def base_financiera(db):
    linea = Linea.objects.create(codigo="B3-REPORTES", nombre="Línea reportes")
    presupuesto = Presupuesto.objects.create(anio=2026, mes=9, linea=linea)
    proveedor = Proveedor.objects.create(nombre="Proveedor de gasto", nit="900248B3")
    contrato = Contrato.objects.create(
        codigo="B3-CONTRATO", nombre="Contrato cartera", unidad_negocio="MANTENIMIENTO"
    )
    return presupuesto, proveedor, contrato


@pytest.mark.django_db
class TestB3ReportesFacturacion:
    def test_B3_proveedor_crud(self, client, admin_user):
        client.force_login(admin_user)
        response = client.post(
            "/financiero/maestros/proveedores/nuevo/",
            {
                "nombre": "Proveedor B3 S.A.S.",
                "nit": "900248003",
                "email": "pagos@proveedor.test",
                "telefono": "3000000000",
                "activo": "on",
            },
            follow=True,
        )
        assert response.status_code == 200
        proveedor = Proveedor.objects.get(nit="900248003")
        assert proveedor.nombre == "Proveedor B3 S.A.S."

        response = client.post(
            f"/financiero/maestros/proveedores/{proveedor.pk}/",
            {"nombre": "Proveedor B3 actualizado", "nit": "900248003", "activo": ""},
            follow=True,
        )
        proveedor.refresh_from_db()
        assert response.status_code == 200
        assert proveedor.nombre == "Proveedor B3 actualizado"
        assert not proveedor.activo

    def test_B3_proveedor_crud_rechaza_nit_duplicado(self, client, admin_user):
        client.force_login(admin_user)
        Proveedor.objects.create(nombre="Proveedor existente", nit="900248004")
        response = client.post(
            "/financiero/maestros/proveedores/nuevo/",
            {"nombre": "Duplicado", "nit": "900248004", "activo": "on"},
        )
        assert response.status_code == 200
        assert Proveedor.objects.filter(nit="900248004").count() == 1
        assert "nit" in response.context["form"].errors

    def test_B3_cartera_indicadores(self, client, admin_user, base_financiera):
        client.force_login(admin_user)
        presupuesto, proveedor, contrato = base_financiera
        hoy = timezone.localdate()
        FacturaGasto.objects.create(
            proveedor=proveedor,
            contrato=contrato,
            numero_documento="G-B3-1",
            fecha=hoy,
            concepto="Servicio",
            categoria="Servicios",
            subtotal=Decimal("100.00"),
            iva=Decimal("19.00"),
            total=Decimal("119.00"),
            estado=FacturaGasto.Estado.PENDIENTE_PAGO,
        )
        CicloFacturacion.objects.create(
            presupuesto=presupuesto,
            numero_factura="FI-B3-1",
            numero_secuencial=1,
            fecha_factura=hoy - timedelta(days=45),
            plazo_pago_dias=30,
            total=Decimal("500.00"),
            monto_pagado=Decimal("100.00"),
        )
        CicloFacturacion.objects.create(
            presupuesto=presupuesto,
            numero_factura="FI-B3-2",
            numero_secuencial=2,
            fecha_factura=hoy,
            plazo_pago_dias=15,
            total=Decimal("200.00"),
            monto_pagado=Decimal("0.00"),
        )
        # Pagada: cuenta para plazo_promedio (días REALES hasta el pago), no
        # para cartera_vencida/facturas_vencidas (ya está saldada).
        CicloFacturacion.objects.create(
            presupuesto=presupuesto,
            numero_factura="FI-B3-3",
            numero_secuencial=3,
            fecha_factura=hoy - timedelta(days=20),
            plazo_pago_dias=30,
            total=Decimal("100.00"),
            monto_pagado=Decimal("100.00"),
            estado=CicloFacturacion.Estado.PAGO_RECIBIDO,
            fecha_pago=hoy - timedelta(days=8),
        )

        response = client.get("/financiero/reportes/facturacion/")
        assert response.status_code == 200
        assert response.context["gastos_pendientes"] == Decimal("119.00")
        assert response.context["cartera_total"] == Decimal("600.00")
        assert response.context["cartera_vencida"] == Decimal("400.00")
        assert response.context["facturas_vencidas"] == 1
        # Morosidad: 1 de 3 facturas vencida = 33.3%
        assert response.context["tasa_morosidad"] == 33.3
        # Plazo promedio REAL de pago: solo FI-B3-3, pagada 12 días después de emitida
        # (20 - 8), no el promedio de plazo_pago_dias contractual (30, 15).
        assert response.context["plazo_promedio"] == 12.0

    def test_B3_cartera_indicadores_sin_plazo_no_es_morosa(
        self, client, admin_user, base_financiera
    ):
        client.force_login(admin_user)
        presupuesto, _, _ = base_financiera
        CicloFacturacion.objects.create(
            presupuesto=presupuesto,
            numero_factura="FI-B3-SIN-PLAZO",
            numero_secuencial=1,
            fecha_factura=timezone.localdate() - timedelta(days=365),
            total=Decimal("300.00"),
        )
        response = client.get("/financiero/reportes/facturacion/")
        assert response.status_code == 200
        assert response.context["cartera_vencida"] == Decimal("0.00")
        assert response.context["facturas_vencidas"] == 0
        assert response.context["tasa_morosidad"] == 0.0
        assert response.context["plazo_promedio"] is None
