from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.contratos.models import Contrato
from apps.financiero.models import (
    CajaProyecto,
    CicloFacturacion,
    EgresoFijoProyecto,
    FacturaGasto,
    PersonalAdministrativo,
    Presupuesto,
    Proveedor,
)
from apps.financiero.services_finv2_flujo_caja import proyectar_flujo_caja
from apps.financiero.views_finv2_flujo_caja import ExportarFlujoCajaCsvView
from apps.lineas.models import Linea


@pytest.fixture
def caja_proyecto(db):
    linea = Linea.objects.create(codigo="FC-251", nombre="Línea flujo caja")
    presupuesto = Presupuesto.objects.create(anio=2026, mes=9, linea=linea)
    contrato = Contrato.objects.create(
        codigo="FC-251", nombre="Proyecto caja", unidad_negocio="MANTENIMIENTO"
    )
    proveedor = Proveedor.objects.create(nombre="Proveedor caja", nit="900251001")
    CajaProyecto.objects.create(contrato=contrato, saldo_inicial=Decimal("100.00"))
    EgresoFijoProyecto.objects.create(
        contrato=contrato, descripcion="Arriendo", monto=Decimal("25.00")
    )
    PersonalAdministrativo.objects.create(
        nombre="Analista caja", documento="251", salario_mensual=Decimal("50.00"), contrato=contrato
    )
    FacturaGasto.objects.create(
        proveedor=proveedor,
        contrato=contrato,
        numero_documento="G-251",
        fecha=timezone.localdate(),
        concepto="Servicio",
        categoria="Servicios",
        subtotal=Decimal("40.00"),
        total=Decimal("40.00"),
        estado=FacturaGasto.Estado.PENDIENTE_PAGO,
    )
    CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        numero_factura="I-251",
        fecha_factura=timezone.localdate(),
        total=Decimal("200.00"),
        monto_pagado=Decimal("20.00"),
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    return contrato


@pytest.mark.django_db
class TestB3FlujoCaja:
    def test_B3_caja_configurable(self, caja_proyecto):
        flujo = proyectar_flujo_caja(
            contrato=caja_proyecto, horizonte_dias=30, porcentaje_cobro=Decimal("90")
        )
        assert flujo["saldo_inicial"] == Decimal("100.00")
        assert flujo["ingresos_proyectados"] == Decimal("162.00")
        assert flujo["egresos_proyectados"] == Decimal("115.00")
        assert flujo["saldo_proyectado"] == Decimal("147.00")

    def test_B3_deficit_visible(self, caja_proyecto):
        flujo = proyectar_flujo_caja(
            contrato=caja_proyecto,
            horizonte_dias=30,
            porcentaje_cobro=Decimal("0"),
            escenario="estres",
        )
        assert flujo["hay_deficit"] is True
        assert any("Déficit" in alerta for alerta in flujo["alertas"])

    def test_B3_export_csv(self, caja_proyecto, admin_user):
        request = RequestFactory().get(
            f"/financiero/flujo-caja/exportar/?contrato={caja_proyecto.pk}&horizonte_dias=30&porcentaje_cobro=90"
        )
        request.user = admin_user
        response = ExportarFlujoCajaCsvView.as_view()(request)
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert "Saldo proyectado" in response.content.decode("utf-8-sig")

    def test_B3_horizonte_largo_alerta(self, caja_proyecto):
        flujo = proyectar_flujo_caja(contrato=caja_proyecto, horizonte_dias=181)
        assert any("Horizontes largos" in alerta for alerta in flujo["alertas"])

    def test_dato_legacy_preservado(self, caja_proyecto):
        legacy = CajaProyecto.objects.get(contrato=caja_proyecto)
        legacy.refresh_from_db()
        assert legacy.saldo_inicial == Decimal("100.00")
