"""E2E de B2: emisión manual/PDF y cobranza de facturas de ingreso (#249)."""

from datetime import date
from types import SimpleNamespace

import pytest

from apps.financiero.models import (
    Banco,
    CicloFacturacion,
    Cliente,
    MetodoPago,
    PagoFacturaIngreso,
    Presupuesto,
)
from apps.financiero.services_finv2_ingresos import generar_numero_factura
from apps.lineas.models import Linea


@pytest.fixture
def datos_factura(db):
    linea = Linea.objects.create(codigo="FINV2-01", nombre="Línea facturable")
    presupuesto = Presupuesto.objects.create(anio=2026, mes=9, linea=linea)
    cliente = Cliente.objects.create(nombre="Cliente legado S.A.", nit="900249001")
    banco = Banco.objects.create(nombre="Banco pruebas")
    metodo = MetodoPago.objects.create(nombre="Transferencia")
    return presupuesto, cliente, banco, metodo


def _payload(presupuesto, cliente, **extra):
    data = {
        "presupuesto": str(presupuesto.pk),
        "cliente": str(cliente.pk),
        "fecha_factura": "2026-09-08",
        "plazo_pago_dias": "30",
        "referencia_cobro": "OC-249",
        "observaciones": "Factura manual",
        "lineas-TOTAL_FORMS": "1",
        "lineas-INITIAL_FORMS": "0",
        "lineas-MIN_NUM_FORMS": "1",
        "lineas-MAX_NUM_FORMS": "1000",
        "lineas-0-descripcion": "Servicio de mantenimiento",
        "lineas-0-cantidad": "2",
        "lineas-0-valor_unitario": "125.50",
    }
    data.update(extra)
    return data


@pytest.mark.django_db
def test_B2_factura_manual_pdf(client, admin_user, datos_factura, monkeypatch):
    presupuesto, cliente, _, _ = datos_factura
    client.force_login(admin_user)
    respuesta = client.post(
        "/financiero/facturas-ingresos/nueva/", _payload(presupuesto, cliente), follow=True
    )
    assert respuesta.status_code == 200
    factura = CicloFacturacion.objects.get(cliente=cliente)
    assert factura.numero_factura == "FI-2026-00001"
    assert str(factura.subtotal) == "251.00"
    assert str(factura.iva) == "47.69"
    assert str(factura.total) == "298.69"
    assert factura.lineas_factura.count() == 1

    class FakeHTML:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def write_pdf(self):
            return b"%PDF-factura"

    monkeypatch.setitem(__import__("sys").modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))
    pdf = client.get(f"/financiero/facturas-ingresos/{factura.pk}/pdf/")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_B2_pago_ingreso(client, admin_user, datos_factura):
    presupuesto, cliente, banco, metodo = datos_factura
    client.force_login(admin_user)
    client.post("/financiero/facturas-ingresos/nueva/", _payload(presupuesto, cliente))
    factura = CicloFacturacion.objects.get(cliente=cliente)
    respuesta = client.post(
        f"/financiero/facturas-ingresos/{factura.pk}/",
        {
            "banco": banco.pk,
            "metodo_pago": metodo.pk,
            "fecha": "2026-09-09",
            "monto": "298.69",
            "referencia": "TRX-249",
        },
        follow=True,
    )
    factura.refresh_from_db()
    assert respuesta.status_code == 200
    assert factura.estado == CicloFacturacion.Estado.PAGO_RECIBIDO
    assert factura.monto_pagado == factura.total
    assert PagoFacturaIngreso.objects.filter(ciclo=factura, referencia="TRX-249").exists()


@pytest.mark.django_db
def test_B2_pago_no_permite_superar_saldo(client, admin_user, datos_factura):
    presupuesto, cliente, banco, metodo = datos_factura
    client.force_login(admin_user)
    client.post("/financiero/facturas-ingresos/nueva/", _payload(presupuesto, cliente))
    factura = CicloFacturacion.objects.get(cliente=cliente)
    respuesta = client.post(
        f"/financiero/facturas-ingresos/{factura.pk}/",
        {
            "banco": banco.pk,
            "metodo_pago": metodo.pk,
            "fecha": "2026-09-09",
            "monto": "400.00",
            "referencia": "TRX-EXCESO",
        },
    )
    assert respuesta.status_code == 200
    assert not PagoFacturaIngreso.objects.filter(ciclo=factura).exists()
    assert "no puede exceder el saldo" in respuesta.content.decode()


@pytest.mark.django_db
def test_dato_legacy_preservado(datos_factura):
    """Un ciclo previo sin los campos v2 continúa siendo interpretable."""
    presupuesto, _, _, _ = datos_factura
    legacy = CicloFacturacion.objects.create(presupuesto=presupuesto, numero_factura="LEG-1")
    legacy.refresh_from_db()
    assert legacy.numero_secuencial is None
    assert legacy.numero_factura == "LEG-1"


@pytest.mark.django_db
def test_consecutivo_anual_reinicia_y_valida_fecha(datos_factura):
    presupuesto, cliente, _, _ = datos_factura
    CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        cliente=cliente,
        fecha_factura=date(2026, 2, 1),
        numero_factura="FI-2026-00007",
        numero_secuencial=7,
    )
    assert generar_numero_factura(date(2026, 9, 8)) == "FI-2026-00008"
    assert generar_numero_factura(date(2027, 1, 1)) == "FI-2027-00001"
    with pytest.raises(ValueError):
        generar_numero_factura(None)
