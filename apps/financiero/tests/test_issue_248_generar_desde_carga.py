"""Generación de Facturas de Gasto 1:1 desde Carga Financiera (#248, corrección
post-rechazo 22-sep -- ver
SPRINTS/PLAN_2026-09-23_248_facturas_gasto_desde_carga_financiera.md).

Reemplaza el flujo anterior (`test_issue_248_gastos_v1.py`, tests de upload
CSV con columnas inventadas): ahora las facturas se generan a partir de
`LineaCargaFinanciera` (tipo=REAL), ya cargada y homologada por #246/#268.

Nota sobre los fixtures: `datos_origen`/`referencia` reproducen EXACTAMENTE
la forma que persiste `importers_finv2_carga.py::_lineas_reales` (sólo
lectura para esta sub-feature) -- no el esquema que describía el plan
original. Concretamente:
- El "Docto." de la fila queda en `LineaCargaFinanciera.referencia`, NO en
  `datos_origen` (que sólo trae 'fecha'/'periodo'/'tipo_operacional').
- `datos_origen['fecha']` es el resultado de `str()` sobre lo que entregó
  Excel/openpyxl: si la celda es una fecha real, eso es
  "AAAA-MM-DD HH:MM:SS" (ver `test_finv2_carga.py::_libro`, usa
  `datetime(2026, 1, 31)`), no "DD/MM/AAAA" como asumía el plan. Usar la
  forma real evita el mismatch fixtures-propias-vs-dato-real que ya causó
  reprocesos en este portafolio (Instelec#220, Homologación).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.contratos.models import Contrato
from apps.financiero.models import (
    AuditoriaFacturaGasto,
    CargaFacturaGasto,
    FacturaGasto,
    HomologacionProjectsContable,
    Proveedor,
)
from apps.financiero.models_finv2_carga import CargaFinanciera, LineaCargaFinanciera
from apps.financiero.services_finv2_gastos import (
    UMBRAL_APROBACION,
    generar_facturas_gasto_desde_carga,
)


@pytest.fixture
def proyecto(db):
    return Contrato.objects.create(
        codigo="TRAN-248",
        nombre="Transelca 248",
        unidad_negocio=Contrato.UnidadNegocio.MANTENIMIENTO,
    )


@pytest.fixture
def proveedor(db):
    return Proveedor.objects.create(nombre="SANMARTIN BLANCO", nit="98687561", activo=True)


@pytest.fixture
def homologacion(db):
    return HomologacionProjectsContable.objects.create(
        tipo="REAL",
        concepto="Materiales 248",
        codigo_contable="5110",
        centro_costo="CC-248",
        activo=True,
    )


@pytest.fixture
def carga_procesada(db, proyecto):
    return CargaFinanciera.objects.create(
        proyecto=proyecto,
        anio=2026,
        mes=1,
        estado=CargaFinanciera.Estado.PROCESADA,
    )


def _linea_real(
    carga,
    *,
    proveedor=None,
    homologacion=None,
    valor=Decimal("500000"),
    docto="DOC-1",
    fecha_texto="2026-01-15 00:00:00",
    centro_costo="CC-248",
    cdec_equiv="",
    concepto="Compra de materiales",
    grupo="Materiales",
    rubro="Insumos",
    fila_origen=2,
    tipo=LineaCargaFinanciera.Tipo.REAL,
):
    return LineaCargaFinanciera.objects.create(
        carga=carga,
        proveedor=proveedor,
        homologacion=homologacion,
        tipo=tipo,
        concepto=concepto,
        grupo=grupo,
        rubro=rubro,
        valor=valor,
        referencia=docto,
        centro_costo=centro_costo,
        cdec_equiv=cdec_equiv,
        fila_origen=fila_origen,
        periodo=202601,
        datos_origen={"fecha": fecha_texto, "periodo": "202601", "tipo_operacional": {}},
    )


# ---------------------------------------------------------------------------
# Línea con proveedor real -> factura con todos los campos mapeados
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_linea_con_proveedor_genera_factura_con_campos_mapeados(
    carga_procesada, proveedor, homologacion
):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        valor=Decimal("500000"),
        docto="DOC-100",
        fecha_texto="2026-01-15 00:00:00",
        concepto="Compra de cable",
        grupo="Materiales",
        rubro="Cables",
        centro_costo="CC-248",
    )
    resultado = generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)

    assert resultado.total_creadas == 1
    assert resultado.total_actualizadas == 0
    assert resultado.total_omitidas == 0

    factura = FacturaGasto.objects.get(proveedor=proveedor, numero_documento="DOC-100")
    assert factura.contrato_id == carga_procesada.proyecto_id
    assert factura.homologacion_id == homologacion.pk
    assert factura.fecha == date(2026, 1, 15)
    assert factura.concepto == "Compra de cable"
    assert factura.categoria == "Cables"  # rubro tiene prioridad sobre grupo
    assert factura.centro_costo == "CC-248"
    assert factura.subtotal == Decimal("500000.00")
    # No se recalcula IVA: el Neto del archivo real ya es el valor ejecutado.
    assert factura.iva == Decimal("0.00")
    assert factura.total == Decimal("500000.00")
    assert factura.estado == FacturaGasto.Estado.PENDIENTE_PAGO


# ---------------------------------------------------------------------------
# Línea sin proveedor (nómina auto-generada) -> omitida, no revienta el lote
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_linea_sin_proveedor_omitida_no_bloquea_lote(carga_procesada, proveedor, homologacion):
    _linea_real(  # sin proveedor -- ej. nómina auto-generada
        carga_procesada,
        proveedor=None,
        homologacion=homologacion,
        docto="DOC-NOMINA",
        concepto="Nómina",
        fila_origen=2,
    )
    _linea_real(  # con proveedor -- debe procesarse igual
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        docto="DOC-101",
        concepto="Compra normal",
        fila_origen=3,
    )
    resultado = generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)

    assert resultado.total_creadas == 1
    assert resultado.total_omitidas == 1
    assert resultado.omitidas[0].motivo == "sin proveedor identificable"
    assert resultado.omitidas[0].fila_origen == 2
    assert not FacturaGasto.objects.filter(numero_documento="DOC-NOMINA").exists()
    assert FacturaGasto.objects.filter(numero_documento="DOC-101").exists()


# ---------------------------------------------------------------------------
# Línea sin Docto. -> omitida con motivo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_linea_sin_numero_documento_omitida(carga_procesada, proveedor, homologacion):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        docto="",  # columna 'Docto.' vacía en el archivo real
        concepto="Compra sin documento",
    )
    resultado = generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)

    assert resultado.total_creadas == 0
    assert resultado.total_omitidas == 1
    assert resultado.omitidas[0].motivo == "sin número de documento"
    assert not FacturaGasto.objects.exists()


# ---------------------------------------------------------------------------
# Umbral de aprobación: > $1.000.000 -> PENDIENTE_APROBACION; si no, PENDIENTE_PAGO
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_umbral_aprobacion_por_total(carga_procesada, proveedor, homologacion):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        valor=Decimal("1500000"),
        docto="DOC-GRANDE",
        fila_origen=2,
    )
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        valor=Decimal("50000"),
        docto="DOC-PEQUENA",
        fila_origen=3,
    )
    generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)

    grande = FacturaGasto.objects.get(numero_documento="DOC-GRANDE")
    pequena = FacturaGasto.objects.get(numero_documento="DOC-PEQUENA")
    assert grande.total > UMBRAL_APROBACION
    assert grande.estado == FacturaGasto.Estado.PENDIENTE_APROBACION
    assert pequena.total <= UMBRAL_APROBACION
    assert pequena.estado == FacturaGasto.Estado.PENDIENTE_PAGO


# ---------------------------------------------------------------------------
# Re-generar la MISMA carga dos veces -> UPSERT, no duplica
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_regenerar_misma_carga_no_duplica(carga_procesada, proveedor, homologacion):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        valor=Decimal("300000"),
        docto="DOC-UPSERT",
        concepto="Concepto original",
    )
    primer = generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)
    assert primer.total_creadas == 1

    # La línea se corrige/actualiza (ej. re-homologación) y se regenera.
    linea = LineaCargaFinanciera.objects.get(carga=carga_procesada, referencia="DOC-UPSERT")
    linea.concepto = "Concepto corregido"
    linea.valor = Decimal("350000")
    linea.save(update_fields=["concepto", "valor", "updated_at"])

    segundo = generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)
    assert segundo.total_creadas == 0
    assert segundo.total_actualizadas == 1

    assert (
        FacturaGasto.objects.filter(proveedor=proveedor, numero_documento="DOC-UPSERT").count() == 1
    )
    factura = FacturaGasto.objects.get(proveedor=proveedor, numero_documento="DOC-UPSERT")
    assert factura.concepto == "Concepto corregido"
    assert factura.subtotal == Decimal("350000.00")


# ---------------------------------------------------------------------------
# centro_costo se resuelve desde cdec_equiv cuando viene vacío en la línea
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_centro_costo_resuelve_desde_cdec_equiv(carga_procesada, proveedor, homologacion):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        docto="DOC-CDEC",
        centro_costo="",
        cdec_equiv="TRANSELCA",
    )
    generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)
    factura = FacturaGasto.objects.get(numero_documento="DOC-CDEC")
    assert factura.centro_costo == "TRANSELCA"


# ---------------------------------------------------------------------------
# Fecha ausente/no parseable -> fallback al primer día del período de la carga
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fecha_ausente_usa_primer_dia_del_periodo(carga_procesada, proveedor, homologacion):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        docto="DOC-SINFECHA",
        fecha_texto="",
    )
    generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)
    factura = FacturaGasto.objects.get(numero_documento="DOC-SINFECHA")
    assert factura.fecha == date(carga_procesada.anio, carga_procesada.mes, 1)


# ---------------------------------------------------------------------------
# Caso legacy/edge: carga sin ninguna línea REAL (sólo PRESUPUESTO)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_carga_sin_lineas_reales_no_genera_nada_sin_error(carga_procesada, proveedor, homologacion):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        docto="DOC-PPTO",
        tipo=LineaCargaFinanciera.Tipo.PRESUPUESTO,
    )
    resultado = generar_facturas_gasto_desde_carga(carga_procesada, usuario="tester", commit=True)
    assert resultado.total_creadas == 0
    assert resultado.total_actualizadas == 0
    assert resultado.total_omitidas == 0
    assert not FacturaGasto.objects.exists()


# ---------------------------------------------------------------------------
# Flujo HTTP de dos pasos: seleccionar carga -> preview -> confirmar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_flujo_http_seleccionar_preview_confirmar(
    client, admin_user, carga_procesada, proveedor, homologacion
):
    _linea_real(
        carga_procesada,
        proveedor=proveedor,
        homologacion=homologacion,
        valor=Decimal("500000"),
        docto="DOC-HTTP-1",
        concepto="Compra vía HTTP",
    )
    client.force_login(admin_user)

    # Paso 1: seleccionar la carga financiera elegible.
    seleccionar = client.post(
        "/financiero/facturas-gastos/importar/",
        {"carga_financiera": str(carga_procesada.pk)},
    )
    assert seleccionar.status_code == 302
    assert seleccionar.url == "/financiero/facturas-gastos/importar/preview/"

    # Paso 2 (GET): preview sin persistir.
    preview = client.get("/financiero/facturas-gastos/importar/preview/")
    assert preview.status_code == 200
    assert not FacturaGasto.objects.exists()
    assert b"DOC-HTTP-1" in preview.content

    # Paso 2 (POST confirmar): persiste.
    confirmar = client.post("/financiero/facturas-gastos/importar/preview/", {"confirmar": "1"})
    assert confirmar.status_code == 302
    factura = FacturaGasto.objects.get(proveedor=proveedor, numero_documento="DOC-HTTP-1")
    assert factura.subtotal == Decimal("500000.00")
    assert AuditoriaFacturaGasto.objects.filter(factura=factura, campo="generacion").exists()

    carga_registro = CargaFacturaGasto.objects.latest("created_at")
    assert carga_registro.resultado == "CONFIRMADA"
    assert carga_registro.filas_creadas == 1

    # Historial y export siguen funcionando (mismo consumidor de siempre).
    historial = client.get("/financiero/facturas-gastos/cargas/")
    assert historial.status_code == 200
    csv_resp = client.get(f"/financiero/facturas-gastos/cargas/{carga_registro.pk}/csv/")
    assert csv_resp.status_code == 200
    assert b"DOC-HTTP-1" in csv_resp.content
