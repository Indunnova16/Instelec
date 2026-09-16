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
from apps.contratos.models import Contrato
from apps.lineas.models import Linea


@pytest.fixture
def datos_factura(db):
    linea = Linea.objects.create(codigo="FINV2-01", nombre="Línea facturable")
    cliente = Cliente.objects.create(nombre="Cliente legado S.A.", nit="900249001")
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.MANTENIMIENTO,
        codigo="FINV2-249",
        nombre="Proyecto facturable",
        cliente=cliente.nombre,
    )
    presupuesto = Presupuesto.objects.create(
        anio=2026, mes=9, linea=linea, cliente=cliente, proyecto=contrato,
        facturacion_esperada="250.00",
    )
    banco = Banco.objects.create(nombre="Banco pruebas")
    metodo = MetodoPago.objects.create(nombre="Transferencia")
    return presupuesto, cliente, contrato, banco, metodo


def _payload(presupuesto, cliente, **extra):
    data = {
        "presupuesto": str(presupuesto.pk),
        "cliente": str(cliente.pk),
        "proyecto": str(presupuesto.proyecto_id),
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
    presupuesto, cliente, _, _, _ = datos_factura
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
    presupuesto, cliente, _, banco, metodo = datos_factura
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
    presupuesto, cliente, _, banco, metodo = datos_factura
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
    presupuesto, _, _, _, _ = datos_factura
    legacy = CicloFacturacion.objects.create(presupuesto=presupuesto, numero_factura="LEG-1")
    legacy.refresh_from_db()
    assert legacy.numero_secuencial is None
    assert legacy.numero_factura == "LEG-1"


@pytest.mark.django_db
def test_consecutivo_es_global_y_no_reinicia_por_anio(datos_factura):
    """#249 v2 (gap 4): la numeración es secuencial GLOBAL, no anual.

    Antes de este fix, `generar_numero_factura` calculaba el máximo filtrado
    por año -- la primera factura de 2027 habría vuelto a pedir
    numero_secuencial=1, que ya usó la primera factura de 2026 histórica
    creada más abajo, y habría reventado el `unique=True` del campo en
    producción (IntegrityError en la primera emisión de cada año nuevo).
    """
    presupuesto, cliente, _, _, _ = datos_factura
    CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        cliente=cliente,
        fecha_factura=date(2026, 1, 1),
        numero_factura="FI-2026-00001",
        numero_secuencial=1,
    )
    CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        cliente=cliente,
        fecha_factura=date(2026, 2, 1),
        numero_factura="FI-2026-00007",
        numero_secuencial=7,
    )
    assert generar_numero_factura(date(2026, 9, 8)) == "FI-2026-00008"
    # El folio del año siguiente muestra el año 2027, pero el consecutivo
    # sigue la secuencia global (8, no reinicia a 1).
    assert generar_numero_factura(date(2027, 1, 1)) == "FI-2027-00008"
    with pytest.raises(ValueError):
        generar_numero_factura(None)


@pytest.mark.django_db
def test_emite_sin_presupuesto_y_persiste_contexto(client, admin_user, datos_factura):
    presupuesto, cliente, contrato, _, _ = datos_factura
    client.force_login(admin_user)
    payload = _payload(presupuesto, cliente)
    payload["presupuesto"] = ""
    respuesta = client.post("/financiero/facturas-ingresos/nueva/", payload, follow=True)
    factura = CicloFacturacion.objects.get(cliente=cliente)
    assert respuesta.status_code == 200
    assert factura.presupuesto is None
    assert factura.proyecto == contrato


@pytest.mark.django_db
def test_presupuesto_incompatible_es_rechazado(client, admin_user, datos_factura):
    presupuesto, cliente, _, _, _ = datos_factura
    otro_cliente = Cliente.objects.create(nombre="Otro cliente", nit="900249002")
    client.force_login(admin_user)
    respuesta = client.post(
        "/financiero/facturas-ingresos/nueva/", _payload(presupuesto, otro_cliente)
    )
    assert respuesta.status_code == 200
    assert not CicloFacturacion.objects.filter(cliente=otro_cliente).exists()


@pytest.mark.django_db
def test_contexto_solo_expone_proyecto_y_presupuesto_compatibles(client, admin_user, datos_factura):
    presupuesto, cliente, contrato, _, _ = datos_factura
    Cliente.objects.create(nombre="Cliente inactivo", nit="900249003", activo=False)
    client.force_login(admin_user)
    respuesta = client.get(
        "/financiero/facturas-ingresos/contexto/",
        {"cliente": cliente.pk, "proyecto": contrato.pk, "fecha": "2026-09-08"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["proyectos"] == [{"id": str(contrato.pk), "label": str(contrato)}]
    assert respuesta.json()["presupuestos"] == [{"id": str(presupuesto.pk), "label": str(presupuesto)}]


@pytest.mark.django_db
def test_dos_lineas_calculan_total_y_alertan_meta(client, admin_user, datos_factura):
    presupuesto, cliente, _, _, _ = datos_factura
    client.force_login(admin_user)
    respuesta = client.post(
        "/financiero/facturas-ingresos/nueva/",
        _payload(
            presupuesto, cliente,
            **{
                "lineas-TOTAL_FORMS": "2",
                "lineas-1-descripcion": "Materiales",
                "lineas-1-cantidad": "1",
                "lineas-1-valor_unitario": "100.00",
            },
        ),
        follow=True,
    )
    factura = CicloFacturacion.objects.get(cliente=cliente)
    assert factura.lineas_factura.count() == 2
    assert factura.subtotal == 351
    assert str(factura.iva) == "66.69"
    assert "supera la meta" in respuesta.content.decode()
