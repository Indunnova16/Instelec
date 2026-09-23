"""Reglas de negocio del flujo de facturas de gasto (#248)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models_finv2_carga import CargaFinanciera, LineaCargaFinanciera
from .models_finv2_facturas import FacturaGasto, PagoFacturaGasto

IVA_ESTANDAR = Decimal("0.19")
UMBRAL_APROBACION = Decimal("1000000.00")
CENTAVOS = Decimal("0.01")

# Formatos tolerados de `LineaCargaFinanciera.datos_origen['fecha']`. El valor
# real depende de cómo Excel/openpyxl entregó la celda al importador de #246
# (`importers_finv2_carga.py::_lineas_reales`, sólo lectura para esta
# sub-feature): si la celda es una fecha real, `_texto()` aplica `str()` sobre
# un `datetime`/`date` de Python -> "AAAA-MM-DD HH:MM:SS" o "AAAA-MM-DD"; si
# la celda es texto plano, puede venir como "DD/MM/AAAA". Se toleran los tres.
_FORMATOS_FECHA_LINEA = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y")


def calcular_totales(valor_base, *, tasa_iva=Decimal("0.19")) -> dict:
    """Calcula IVA y total sin introducir errores de coma flotante."""
    try:
        base = Decimal(valor_base)
        tasa = Decimal(tasa_iva)
    except (TypeError, ValueError, ArithmeticError) as error:
        raise ValidationError("El valor base y la tasa de IVA deben ser numéricos.") from error
    if base <= 0:
        raise ValidationError("El subtotal debe ser mayor que cero.")
    if tasa < 0 or tasa > 1:
        raise ValidationError("La tasa de IVA debe estar entre 0 y 1.")
    iva = (base * tasa).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    return {"subtotal": base.quantize(CENTAVOS), "iva": iva, "total": base.quantize(CENTAVOS) + iva}


def estado_inicial_gasto(total):
    return (
        FacturaGasto.Estado.PENDIENTE_APROBACION
        if Decimal(total) > UMBRAL_APROBACION
        else FacturaGasto.Estado.PENDIENTE_PAGO
    )


@transaction.atomic
def aprobar_gasto(factura, comentario=""):
    if factura.estado != FacturaGasto.Estado.PENDIENTE_APROBACION:
        raise ValidationError("Solo se pueden aprobar facturas pendientes de aprobación.")
    factura.estado = FacturaGasto.Estado.PENDIENTE_PAGO
    factura.comentario_decision = comentario.strip()
    factura.save(update_fields=["estado", "comentario_decision", "updated_at"])
    return factura


@transaction.atomic
def registrar_pago_gasto(factura, *, banco, metodo_pago, fecha, monto, referencia):
    monto = Decimal(monto)
    referencia = (referencia or "").strip()
    if factura.estado != FacturaGasto.Estado.PENDIENTE_PAGO:
        raise ValidationError("La factura debe estar aprobada antes de registrar el pago.")
    if monto != factura.total:
        raise ValidationError("El pago debe cubrir exactamente el total de la factura.")
    if not referencia:
        raise ValidationError("La referencia de pago es obligatoria.")
    pago = PagoFacturaGasto.objects.create(
        factura=factura,
        banco=banco,
        metodo_pago=metodo_pago,
        fecha=fecha,
        monto=monto,
        referencia=referencia,
    )
    factura.banco = banco
    factura.metodo_pago = metodo_pago
    factura.referencia_pago = referencia
    factura.estado = FacturaGasto.Estado.PAGADA
    factura.save(update_fields=["banco", "metodo_pago", "referencia_pago", "estado", "updated_at"])
    return pago


# ---------------------------------------------------------------------------
# #248 (corrección post-rechazo 22-sep): generar Facturas de Gasto 1:1 desde
# las líneas YA cargadas y homologadas por #246 (`LineaCargaFinanciera`,
# tipo=REAL), en vez de un upload propio con columnas inventadas que nunca
# coincidieron con el archivo real del cliente. Ver
# SPRINTS/PLAN_2026-09-23_248_facturas_gasto_desde_carga_financiera.md.
# ---------------------------------------------------------------------------


def cargas_elegibles_para_generar_gastos():
    """`CargaFinanciera` vigente, PROCESADA, con >=1 línea `tipo=REAL`.

    Única fuente de verdad de la consulta -- la usan tanto el formulario de
    selección (`forms_finv2_gastos.GenerarFacturasGastoForm`) como la vista
    de los dos pasos (`views_finv2_gastos.py`), para no duplicar el criterio
    de elegibilidad en dos lugares.
    """
    return (
        CargaFinanciera.objects.filter(
            vigente=True,
            estado=CargaFinanciera.Estado.PROCESADA,
            lineas__tipo=LineaCargaFinanciera.Tipo.REAL,
        )
        .select_related("proyecto")
        .distinct()
        .order_by("-anio", "-mes", "proyecto__nombre")
    )


@dataclass
class FacturaGeneradaGasto:
    """Una `LineaCargaFinanciera` mapeada a una `FacturaGasto` (#248)."""

    factura: FacturaGasto
    accion: str  # "crear" | "actualizar"
    linea_id: str


@dataclass
class GastoOmitido:
    """Línea de la carga que NO generó factura, con el motivo (#248)."""

    linea_id: str
    fila_origen: int | None
    concepto: str
    motivo: str


@dataclass
class ResultadoGeneracionGastos:
    """Respuesta estable de `generar_facturas_gasto_desde_carga` (#248)."""

    creadas: list = field(default_factory=list)
    actualizadas: list = field(default_factory=list)
    omitidas: list = field(default_factory=list)

    @property
    def procesadas(self):
        return self.creadas + self.actualizadas

    @property
    def total_creadas(self):
        return len(self.creadas)

    @property
    def total_actualizadas(self):
        return len(self.actualizadas)

    @property
    def total_omitidas(self):
        return len(self.omitidas)


def _numero_documento_de_linea(linea):
    """Número de documento real de la fila (columna 'Docto.' del archivo).

    DESVIACIÓN DOCUMENTADA respecto al plan literal: el plan describía este
    valor en `linea.datos_origen.get('Docto.'|'Docto')`, pero el importador
    real de #246 (`importers_finv2_carga.py::_lineas_reales`, sólo lectura
    para esta sub-feature) persiste la columna 'Docto.' en el campo propio
    `LineaCargaFinanciera.referencia` -- `datos_origen` de una línea REAL
    sólo trae las claves 'fecha'/'periodo'/'tipo_operacional'. Se usa el
    campo real que sí existe en la fila, en vez de una clave que nunca se
    persiste.
    """
    return (linea.referencia or "").strip()


def _fecha_de_linea(linea, carga):
    """Fecha real de la fila o el 1° del período de la carga como fallback.

    DESVIACIÓN DOCUMENTADA respecto al plan literal: el plan asumía
    `datos_origen['Fecha']` en formato dd/mm/aaaa exclusivamente. El
    importador real guarda la clave en minúscula (`datos_origen['fecha']`) y
    su formato depende de cómo Excel entregó la celda: si es una fecha real
    de Excel, `str(datetime)` produce "AAAA-MM-DD HH:MM:SS"; si la celda es
    texto plano, puede venir "DD/MM/AAAA". Se toleran ambos formatos (más el
    ISO corto) antes de aplicar el fallback documentado en el plan (primer
    día del período `anio`/`mes` de la `CargaFinanciera`).
    """
    texto = str((linea.datos_origen or {}).get("fecha") or "").strip()
    for formato in _FORMATOS_FECHA_LINEA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return date(carga.anio, carga.mes, 1)


def generar_facturas_gasto_desde_carga(
    carga, *, usuario="", commit=True
) -> ResultadoGeneracionGastos:
    """Genera/actualiza una `FacturaGasto` por cada `LineaCargaFinanciera`
    REAL de `carga` (#248).

    Reglas de negocio (confirmadas por Miguel, 2026-09-23):
    - Línea sin `proveedor` resuelto (ej. nómina auto-generada sin NIT) ->
      se OMITE, no bloquea el resto del lote.
    - Línea sin número de documento identificable -> se OMITE.
    - `homologacion`/`centro_costo` (con fallback a `cdec_equiv`) y
      `categoria` (rubro, o grupo si no hay rubro) se toman directo de la
      línea -- ya vienen resueltos por #246/#268.
    - `Neto` de la línea (`linea.valor`) YA es el valor contable ejecutado
      post-impuestos del export TRANSELCA: NO se recalcula IVA. `iva=0`,
      `total=subtotal`. Esto difiere del IVA-19%-automático que sí aplica a
      `FacturaGastoForm` (creación manual, #248 CRUD original) y a
      #249 (facturas de INGRESO), donde el usuario tipea el neto sin
      impuesto.
    - Estado: `PENDIENTE_APROBACION` si `total > $1.000.000`, si no
      `PENDIENTE_PAGO` (mismo umbral que `estado_inicial_gasto`).
    - UPSERT por `(proveedor, numero_documento)` -- la unique constraint
      real del modelo (`uq_finv2_gasto_proveedor_doc`); re-generar la misma
      carga no duplica, actualiza.

    `commit=False` calcula el mismo resultado SIN persistir nada (usado por
    el paso de preview de la vista); `commit=True` persiste dentro de una
    transacción atómica.
    """
    resultado = ResultadoGeneracionGastos()
    lineas = (
        carga.lineas.filter(tipo=LineaCargaFinanciera.Tipo.REAL)
        .select_related("proveedor", "homologacion")
        .order_by("fila_origen", "created_at")
    )

    def _procesar(linea):
        if linea.proveedor_id is None:
            resultado.omitidas.append(
                GastoOmitido(
                    linea_id=str(linea.pk),
                    fila_origen=linea.fila_origen,
                    concepto=linea.concepto,
                    motivo="sin proveedor identificable",
                )
            )
            return

        numero_documento = _numero_documento_de_linea(linea)
        if not numero_documento:
            resultado.omitidas.append(
                GastoOmitido(
                    linea_id=str(linea.pk),
                    fila_origen=linea.fila_origen,
                    concepto=linea.concepto,
                    motivo="sin número de documento",
                )
            )
            return

        fecha = _fecha_de_linea(linea, carga)
        centro_costo = linea.centro_costo or linea.cdec_equiv
        categoria = linea.rubro or linea.grupo or ""
        subtotal = linea.valor
        estado = estado_inicial_gasto(subtotal)

        defaults = {
            "contrato": carga.proyecto,
            "homologacion": linea.homologacion,
            "fecha": fecha,
            "concepto": linea.concepto,
            "categoria": categoria,
            "centro_costo": centro_costo,
            "subtotal": subtotal,
            "iva": Decimal("0.00"),
            "total": subtotal,
            "estado": estado,
        }
        existente = FacturaGasto.objects.filter(
            proveedor=linea.proveedor, numero_documento=numero_documento
        ).first()
        if existente:
            factura = existente
            for campo, valor in defaults.items():
                setattr(factura, campo, valor)
            if commit:
                factura.save()
            accion = "actualizar"
        else:
            if commit:
                factura = FacturaGasto.objects.create(
                    proveedor=linea.proveedor, numero_documento=numero_documento, **defaults
                )
            else:
                factura = FacturaGasto(
                    proveedor=linea.proveedor, numero_documento=numero_documento, **defaults
                )
            accion = "crear"

        item = FacturaGeneradaGasto(factura=factura, accion=accion, linea_id=str(linea.pk))
        (resultado.actualizadas if accion == "actualizar" else resultado.creadas).append(item)

    if commit:
        with transaction.atomic():
            for linea in lineas:
                _procesar(linea)
    else:
        for linea in lineas:
            _procesar(linea)
    return resultado
