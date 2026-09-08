from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.contratos.models import Contrato
from apps.financiero.models import (
    Banco,
    CicloFacturacion,
    ConciliacionBancaria,
    FacturaGasto,
    Presupuesto,
    Proveedor,
)
from apps.financiero.services_finv2_conciliacion import aplicar_override, resumen_conciliacion
from apps.lineas.models import Linea


@pytest.fixture
def conciliacion_base(db):
    banco = Banco.objects.create(nombre="Banco Conciliación")
    contrato = Contrato.objects.create(
        codigo="CONC-250", nombre="Contrato conciliación", unidad_negocio="MANTENIMIENTO"
    )
    proveedor = Proveedor.objects.create(nombre="Proveedor conciliación", nit="900250001")
    linea = Linea.objects.create(codigo="CONC-250", nombre="Línea conciliación")
    presupuesto = Presupuesto.objects.create(anio=2026, mes=9, linea=linea)
    gasto = FacturaGasto.objects.create(
        proveedor=proveedor,
        contrato=contrato,
        numero_documento="FG-250-1",
        fecha=date(2026, 9, 8),
        concepto="Servicio",
        categoria="Servicios",
        subtotal=Decimal("100.00"),
        iva=Decimal("19.00"),
        total=Decimal("119.00"),
    )
    ingreso = CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        numero_factura="FI-2026-00001",
        total=Decimal("200.00"),
    )
    return {"banco": banco, "gasto": gasto, "ingreso": ingreso}


def csv_upload(content):
    return SimpleUploadedFile("movimientos.csv", content.encode(), content_type="text/csv")


@pytest.mark.django_db
class TestB1Conciliacion:
    def test_B1_importacion_csv(self, client, admin_user, conciliacion_base):
        client.force_login(admin_user)
        csv = "Fecha,Referencia,Descripción,Monto,Tipo,Banco\n2026-09-08,FG-250-1,Pago proveedor,119.00,Transferencia,Banco Conciliación\n"
        response = client.post(
            "/financiero/conciliacion/importar/", {"archivo": csv_upload(csv)}, follow=True
        )
        assert response.status_code == 200
        conciliacion = ConciliacionBancaria.objects.get()
        assert conciliacion.estado == ConciliacionBancaria.Estado.CONCILIADA
        response = client.post(
            "/financiero/conciliacion/importar/", {"archivo": csv_upload(csv)}, follow=True
        )
        assert response.status_code == 200
        assert ConciliacionBancaria.objects.count() == 1

    def test_B1_match_referencia_real(self, client, admin_user, conciliacion_base):
        client.force_login(admin_user)
        csv = "Fecha,Referencia,Descripción,Monto,Tipo,Banco\n08/09/2026,FG-250-1,Pago parcial,100.00,Transferencia,Banco Conciliación\n2026-09-08,FI-2026-00001,Depósito cliente,200.00,Depósito,Banco Conciliación\n"
        client.post("/financiero/conciliacion/importar/", {"archivo": csv_upload(csv)})
        conciliacion = ConciliacionBancaria.objects.get(movimiento__referencia="FG-250-1")
        assert conciliacion.factura_gasto == conciliacion_base["gasto"]
        assert conciliacion.estado == ConciliacionBancaria.Estado.DIFERENCIA
        assert conciliacion.diferencia == Decimal("-19.00")
        ingreso = ConciliacionBancaria.objects.get(movimiento__referencia="FI-2026-00001")
        assert ingreso.ciclo_ingreso == conciliacion_base["ingreso"]
        assert ingreso.estado == ConciliacionBancaria.Estado.CONCILIADA

    def test_B1_override_y_diferencia(self, admin_user, conciliacion_base):
        movimiento_csv = "Fecha,Referencia,Descripción,Monto,Tipo,Banco\n2026-09-08,SIN-MATCH,Sin referencia,119.00,Transferencia,Banco Conciliación\n"
        from apps.financiero.services_finv2_conciliacion import importar_movimientos_csv

        importar_movimientos_csv(csv_upload(movimiento_csv))
        conciliacion = ConciliacionBancaria.objects.get()
        aplicar_override(
            conciliacion,
            accion="redirigir",
            usuario=admin_user,
            factura_gasto=conciliacion_base["gasto"],
            motivo="Referencia bancaria incompleta",
        )
        conciliacion.refresh_from_db()
        assert conciliacion.es_override is True
        assert conciliacion.usuario_override == admin_user
        assert conciliacion.fecha_override is not None
        assert conciliacion.estado == ConciliacionBancaria.Estado.CONCILIADA
        aplicar_override(
            conciliacion, accion="deshacer", usuario=admin_user, motivo="Corrección solicitada"
        )
        conciliacion.refresh_from_db()
        assert conciliacion.estado == ConciliacionBancaria.Estado.PENDIENTE
        assert resumen_conciliacion()["pendientes"] == Decimal("1")

    def test_importacion_rechaza_tipo_y_columnas_invalidas(
        self, client, admin_user, conciliacion_base
    ):
        client.force_login(admin_user)
        invalid_columns = "Fecha,Referencia,Monto\n2026-09-08,FG-250-1,119.00\n"
        response = client.post(
            "/financiero/conciliacion/importar/", {"archivo": csv_upload(invalid_columns)}
        )
        assert response.status_code == 200
        assert ConciliacionBancaria.objects.count() == 0
        invalid_type = "Fecha,Referencia,Descripción,Monto,Tipo,Banco\n2026-09-08,FG-250-1,Pago,119.00,Cheque,Banco Conciliación\n"
        response = client.post(
            "/financiero/conciliacion/importar/", {"archivo": csv_upload(invalid_type)}
        )
        assert response.status_code == 200
        assert ConciliacionBancaria.objects.count() == 0
