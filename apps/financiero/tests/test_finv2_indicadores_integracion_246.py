"""E2E de #246 Sprint C: `construir_contexto_dashboard_integrado` (B3).

Nota sobre datos legacy (protocolo de issues, paso 5): consultado
``psql instelec_db`` vía el proxy de sólo lectura (127.0.0.1:5434) antes de
escribir estos tests --

- ``produccion_diaria``: 2 filas reales en prod (evidencia de que la fuente
  de nómina SÍ tiene tráfico real).
- ``financiero_clientes``: filas reales en prod, incluyendo un cliente activo
  real ("Energía del Caribe S.A.").
- ``financiero_facturas_gasto`` y ``ciclos_facturacion`` (con
  ``numero_secuencial`` no nulo): **0 filas** -- todavía no existe ninguna
  factura de gasto ni de ingreso emitida en prod. No hay registro legacy real
  posible para esas 2 fuentes porque el módulo apenas se está integrando acá;
  los fixtures de gasto/ingreso reproducen exactamente el esquema real
  confirmado por Read de ``models_finv2_facturas.py`` (mismos campos, mismas
  constraints), no datos inventados.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.construccion.models import ProyectoConstruccion
from apps.contratos.models import Contrato
from apps.cuadrillas.models import Cargo, Cuadrilla, PersonalCuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import (
    ProduccionDiaria,
    RegistroPersonalProduccion,
)
from apps.financiero.models_finv2_facturas import (
    CicloFacturacion,
    Cliente,
    FacturaGasto,
    LineaFacturaIngreso,
    Proveedor,
)
from apps.financiero.services_finv2_indicadores_integracion import (
    construir_contexto_dashboard_integrado,
)


@pytest.fixture
def contrato_construccion(db):
    contrato = Contrato.objects.create(
        codigo="INT246-CONS",
        nombre="Contrato construcción #246",
        unidad_negocio="CONSTRUCCION",
    )
    ProyectoConstruccion.objects.create(contrato=contrato, nombre="Proyecto construcción #246")
    return contrato


@pytest.fixture
def produccion_legacy(contrato_construccion):
    """Reproduce la forma real de los 2 registros legacy de `produccion_diaria`
    (mismo patrón de fixture que apps/construccion/tests/test_issue_225_sprintA.py,
    que ya ejercía este mismo agregador de #252)."""
    cargo = Cargo.objects.create(
        codigo="INT246-CARGO", nombre="Cargo #246", salario_base=Decimal("3000.00")
    )
    personal = PersonalCuadrilla.objects.create(
        nombre="Operario #246",
        documento="INT246-DOC-1",
        rol_cuadrilla=cargo,
        salario_base=Decimal("2400.00"),
        area="CONSTRUCCION",
    )
    cuadrilla = Cuadrilla.objects.create(codigo="INT246-CUAD", nombre="Cuadrilla #246")
    proyecto_construccion = contrato_construccion.proyecto_construccion
    programacion = ProgramacionSemanalCuadrilla.objects.create(
        cuadrilla=cuadrilla,
        proyecto=proyecto_construccion,
        anio=2026,
        semana=38,
    )
    produccion = ProduccionDiaria.objects.create(programacion=programacion, fecha=date(2026, 9, 10))
    RegistroPersonalProduccion.objects.create(
        produccion=produccion,
        personal=personal,
        horas_trabajadas=Decimal("8.00"),
    )
    return produccion


@pytest.fixture
def gasto_legacy(contrato_construccion):
    proveedor = Proveedor.objects.create(nombre="Proveedor #246", nit="900246001")
    return FacturaGasto.objects.create(
        proveedor=proveedor,
        contrato=contrato_construccion,
        numero_documento="FG-246-1",
        fecha=date(2026, 9, 12),
        concepto="Materiales",
        categoria="Materiales",
        subtotal=Decimal("500.00"),
        iva=Decimal("95.00"),
        total=Decimal("595.00"),
        estado=FacturaGasto.Estado.PAGADA,
    )


@pytest.fixture
def ingreso_legacy(contrato_construccion):
    cliente = Cliente.objects.create(nombre="Cliente legado #246", nit="900246002")
    ciclo = CicloFacturacion.objects.create(
        cliente=cliente,
        proyecto=contrato_construccion,
        numero_secuencial=1,
        numero_factura="FI-2026-00001",
        fecha_factura=date(2026, 9, 15),
        subtotal=Decimal("1000.00"),
        iva=Decimal("190.00"),
        total=Decimal("1190.00"),
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    LineaFacturaIngreso.objects.create(
        ciclo=ciclo,
        descripcion="Servicio de mantenimiento",
        cantidad=Decimal("1"),
        valor_unitario=Decimal("1000.00"),
        total=Decimal("1000.00"),
    )
    return ciclo


@pytest.mark.django_db
def test_dashboard_agrega_produccion_diaria_legacy_sin_duplicar(
    contrato_construccion, produccion_legacy
):
    contexto = construir_contexto_dashboard_integrado(2026, 9, contrato=contrato_construccion)
    nomina = contexto["integracion_nomina"]
    assert nomina["con_datos"] is True
    assert nomina["cantidad_producciones"] == 1
    assert nomina["horas_trabajadas"] == Decimal("8.00")
    # 8h * (2400/240) = 80.00 -- calculado por `agregado_financiero_produccion`
    # (#252, ya en main), no reimplementado acá.
    assert nomina["costo_nomina"] == Decimal("80.00")

    # Llamar 2 veces con los mismos parámetros no debe duplicar (la función es
    # de sólo lectura e idempotente, igual que su dependencia de #252).
    contexto_repetido = construir_contexto_dashboard_integrado(
        2026, 9, contrato=contrato_construccion
    )
    assert contexto_repetido["integracion_nomina"]["costo_nomina"] == Decimal("80.00")
    assert contexto_repetido["integracion_nomina"]["cantidad_producciones"] == 1


@pytest.mark.django_db
def test_dashboard_agrega_gasto_e_ingreso_legacy_con_procedencia(
    contrato_construccion,
    gasto_legacy,
    ingreso_legacy,
):
    contexto = construir_contexto_dashboard_integrado(2026, 9, contrato=contrato_construccion)

    gastos = contexto["integracion_gastos"]
    assert gastos["con_datos"] is True
    assert gastos["total"] == Decimal("595.00")
    assert gastos["pendiente_pago"] == Decimal("0.00")  # ya está PAGADA
    assert gastos["detalle"][0]["numero_documento"] == "FG-246-1"
    assert gastos["detalle"][0]["proveedor"] == "Proveedor #246"

    ingresos = contexto["integracion_ingresos"]
    assert ingresos["con_datos"] is True
    assert ingresos["total"] == Decimal("1190.00")
    assert ingresos["detalle"][0]["numero_factura"] == "FI-2026-00001"
    assert ingresos["detalle"][0]["cliente"] == "Cliente legado #246"
    # Procedencia: la línea de la factura de ingreso viaja en el detalle sin
    # volver a sumarse en el total (el total ya viene de CicloFacturacion.total).
    assert ingresos["detalle"][0]["lineas"][0]["descripcion"] == "Servicio de mantenimiento"

    clientes = contexto["integracion_clientes"]
    assert clientes["con_datos"] is True
    assert clientes["facturados_periodo"] == 1
    assert clientes["detalle"][0]["cliente"] == "Cliente legado #246"
    assert clientes["detalle"][0]["total_facturado"] == Decimal("1190.00")
    # No hay doble conteo: el total agrupado por cliente reconcilia EXACTO
    # con el total general de ingresos del período.
    assert clientes["detalle"][0]["total_facturado"] == ingresos["total"]


@pytest.mark.django_db
def test_periodo_sin_datos_no_rompe_y_queda_claramente_vacio(contrato_construccion):
    """Edge case: mes sin ninguna de las 4 fuentes -- no debe lanzar, debe
    devolver ceros/listas vacías con `con_datos=False` explícito."""
    contexto = construir_contexto_dashboard_integrado(2026, 1, contrato=contrato_construccion)
    assert contexto["integracion_nomina"] == {
        "costo_nomina": Decimal("0.00"),
        "horas_trabajadas": Decimal("0"),
        "cantidad_producciones": 0,
        "producciones": [],
        "con_datos": False,
    }
    assert contexto["integracion_gastos"]["con_datos"] is False
    assert contexto["integracion_gastos"]["total"] == Decimal("0.00")
    assert contexto["integracion_ingresos"]["con_datos"] is False
    assert contexto["integracion_clientes"]["con_datos"] is False
    assert contexto["integracion_clientes"]["facturados_periodo"] == 0


@pytest.mark.django_db
def test_contrato_mantenimiento_sin_proyecto_construccion_no_rompe_nomina(gasto_legacy):
    """Edge case: un contrato de MANTENIMIENTO no tiene `ProyectoConstruccion`
    (OneToOne limitado a CONSTRUCCION) -- no debe lanzar AttributeError, debe
    devolver nómina vacía con causa clara (no es un error de datos)."""
    contrato_mantenimiento = Contrato.objects.create(
        codigo="INT246-MANT",
        nombre="Contrato mantenimiento #246",
        unidad_negocio="MANTENIMIENTO",
    )
    contexto = construir_contexto_dashboard_integrado(2026, 9, contrato=contrato_mantenimiento)
    assert contexto["integracion_nomina"]["con_datos"] is False
    assert contexto["integracion_nomina"]["costo_nomina"] == Decimal("0.00")
    # El gasto de OTRO contrato (fixture `gasto_legacy`, CONSTRUCCION) no debe
    # aparecer al filtrar por este contrato de MANTENIMIENTO -- sin doble conteo
    # entre contratos.
    assert contexto["integracion_gastos"]["con_datos"] is False


@pytest.mark.django_db
def test_dashboard_sin_filtro_de_contrato_agrega_todos(
    contrato_construccion,
    produccion_legacy,
    gasto_legacy,
    ingreso_legacy,
):
    """`contrato=None` agrega todos los contratos del período (vista de
    portafolio) -- mismo criterio que `contexto_indicadores_finv2` cuando no
    recibe `contrato`."""
    contexto = construir_contexto_dashboard_integrado(2026, 9, contrato=None)
    assert contexto["integracion_nomina"]["con_datos"] is True
    assert contexto["integracion_gastos"]["total"] == Decimal("595.00")
    assert contexto["integracion_ingresos"]["total"] == Decimal("1190.00")


@pytest.mark.django_db
def test_view_carga_financiera_expone_claves_de_integracion_sin_romper_existentes(
    client,
    admin_user,
    contrato_construccion,
    gasto_legacy,
):
    """Integración con `CargaFinancieraView`: las claves nuevas conviven con
    `indicadores`/`resumen_totales` ya existentes (#246 Sprint B), sin que la
    vista rompa cuando no hay `CargaFinanciera` cargada para el período."""
    client.force_login(admin_user)
    respuesta = client.get(
        "/financiero/carga-financiera/",
        {"proyecto": contrato_construccion.pk, "anio": 2026, "mes": 9},
    )
    assert respuesta.status_code == 200
    assert respuesta.context["integracion_gastos"]["con_datos"] is True
    assert respuesta.context["integracion_gastos"]["total"] == Decimal("595.00")
    assert "integracion-dashboard" in respuesta.content.decode()
