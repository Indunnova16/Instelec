"""Reglas de negocio para importar y conciliar extractos bancarios (#250)."""

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import TextIOWrapper

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Banco, ConciliacionBancaria, FacturaGasto, MovimientoBancario
from .models_base import CicloFacturacion

CSV_COLUMNS = ("Fecha", "Referencia", "Descripción", "Monto", "Tipo", "Banco")


def _parse_fecha(value):
    for format_string in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), format_string).date()
        except ValueError:
            continue
    raise ValidationError("Fecha inválida: use AAAA-MM-DD o DD/MM/AAAA.")


def _parse_monto(value):
    normalized = value.strip().replace("$", "").replace(" ", "")
    if "," in normalized and "." in normalized:
        decimal_separator = "," if normalized.rfind(",") > normalized.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        normalized = normalized.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")
    try:
        monto = Decimal(normalized)
    except InvalidOperation as error:
        raise ValidationError("Monto inválido en el CSV.") from error
    if monto <= 0:
        raise ValidationError("El monto debe ser mayor que cero.")
    return monto.quantize(Decimal("0.01"))


def _parse_tipo(value):
    normalized = value.strip().upper().replace("Ó", "O")
    mapping = {
        "DEPOSITO": MovimientoBancario.Tipo.DEPOSITO,
        "TRANSFERENCIA": MovimientoBancario.Tipo.TRANSFERENCIA,
    }
    try:
        return mapping[normalized]
    except KeyError as error:
        raise ValidationError("Tipo inválido: use Depósito o Transferencia.") from error


def _documento_para_referencia(referencia):
    gasto = FacturaGasto.objects.filter(numero_documento=referencia).first()
    if gasto:
        return gasto, None, gasto.total
    ingreso = CicloFacturacion.objects.filter(numero_factura=referencia).first()
    if ingreso:
        return None, ingreso, ingreso.total
    return None, None, None


@transaction.atomic
def conciliar_automaticamente(movimiento):
    """Crea o actualiza la conciliación automática basada en la referencia real."""
    gasto, ingreso, monto_documento = _documento_para_referencia(movimiento.referencia)
    conciliacion, _ = ConciliacionBancaria.objects.get_or_create(movimiento=movimiento)
    conciliacion.factura_gasto = gasto
    conciliacion.ciclo_ingreso = ingreso
    conciliacion.monto_documento = monto_documento
    conciliacion.es_override = False
    conciliacion.motivo_override = ""
    conciliacion.usuario_override = None
    conciliacion.fecha_override = None
    if monto_documento is None:
        conciliacion.estado = ConciliacionBancaria.Estado.PENDIENTE
        conciliacion.diferencia = Decimal("0.00")
    else:
        conciliacion.diferencia = movimiento.monto - monto_documento
        conciliacion.estado = (
            ConciliacionBancaria.Estado.CONCILIADA
            if conciliacion.diferencia == 0
            else ConciliacionBancaria.Estado.DIFERENCIA
        )
    conciliacion.save()
    return conciliacion


def importar_movimientos_csv(archivo):
    """Importa un CSV contractual sin duplicar movimientos ya persistidos."""
    try:
        reader = csv.DictReader(TextIOWrapper(archivo.file, encoding="utf-8-sig", newline=""))
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise ValidationError("El CSV debe tener exactamente: " + ", ".join(CSV_COLUMNS) + ".")
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise ValidationError("El CSV debe estar codificado en UTF-8.") from error
    if not rows:
        raise ValidationError("El archivo CSV no contiene movimientos.")

    resultado = {"creados": 0, "duplicados": 0, "conciliaciones": []}
    for number, row in enumerate(rows, start=2):
        if not all((row.get(column) or "").strip() for column in CSV_COLUMNS):
            raise ValidationError(f"Fila {number}: las seis columnas son obligatorias.")
        try:
            banco = Banco.objects.get(nombre__iexact=row["Banco"].strip(), activo=True)
        except Banco.DoesNotExist as error:
            raise ValidationError(
                f"Fila {number}: el banco indicado no existe o está inactivo."
            ) from error
        movimiento, created = MovimientoBancario.objects.get_or_create(
            banco=banco,
            fecha=_parse_fecha(row["Fecha"]),
            referencia=row["Referencia"].strip(),
            monto=_parse_monto(row["Monto"]),
            tipo=_parse_tipo(row["Tipo"]),
            defaults={
                "descripcion": row["Descripción"].strip(),
                "origen_importacion": archivo.name,
            },
        )
        if created:
            resultado["creados"] += 1
            resultado["conciliaciones"].append(conciliar_automaticamente(movimiento))
        else:
            resultado["duplicados"] += 1
    return resultado


@transaction.atomic
def aplicar_override(
    conciliacion, *, accion, usuario, factura_gasto=None, ciclo_ingreso=None, motivo=""
):
    """Confirma, deshace o redirige conservando trazabilidad de la decisión."""
    if accion == "deshacer":
        conciliacion.factura_gasto = None
        conciliacion.ciclo_ingreso = None
        conciliacion.monto_documento = None
        conciliacion.diferencia = Decimal("0.00")
        conciliacion.estado = ConciliacionBancaria.Estado.PENDIENTE
    elif accion == "confirmar":
        if not conciliacion.factura_gasto and not conciliacion.ciclo_ingreso:
            raise ValidationError("No existe un documento para confirmar el match.")
        conciliacion.estado = (
            ConciliacionBancaria.Estado.CONCILIADA
            if conciliacion.diferencia == 0
            else ConciliacionBancaria.Estado.DIFERENCIA
        )
    elif accion == "redirigir":
        if bool(factura_gasto) == bool(ciclo_ingreso) or not motivo.strip():
            raise ValidationError("La redirección exige un único documento y un motivo.")
        conciliacion.factura_gasto = factura_gasto
        conciliacion.ciclo_ingreso = ciclo_ingreso
        conciliacion.monto_documento = factura_gasto.total if factura_gasto else ciclo_ingreso.total
        conciliacion.diferencia = conciliacion.movimiento.monto - conciliacion.monto_documento
        conciliacion.estado = (
            ConciliacionBancaria.Estado.CONCILIADA
            if conciliacion.diferencia == 0
            else ConciliacionBancaria.Estado.DIFERENCIA
        )
    else:
        raise ValidationError("Acción de conciliación inválida.")
    conciliacion.es_override = True
    conciliacion.motivo_override = motivo.strip()
    conciliacion.usuario_override = usuario
    conciliacion.fecha_override = timezone.now()
    conciliacion.save()
    return conciliacion


def resumen_conciliacion(*, fecha_inicio=None, fecha_fin=None, banco_id=None) -> dict[str, Decimal]:
    """Resumen contractual consumido por B2 y B3, sin reglas de matching duplicadas."""
    queryset = ConciliacionBancaria.objects.select_related("movimiento")
    if fecha_inicio:
        queryset = queryset.filter(movimiento__fecha__gte=fecha_inicio)
    if fecha_fin:
        queryset = queryset.filter(movimiento__fecha__lte=fecha_fin)
    if banco_id:
        queryset = queryset.filter(movimiento__banco_id=banco_id)
    states = {
        row["estado"]: row["cantidad"]
        for row in queryset.values("estado").annotate(cantidad=Count("id"))
    }
    return {
        "total": Decimal(queryset.count()),
        "conciliadas": Decimal(states.get(ConciliacionBancaria.Estado.CONCILIADA, 0)),
        "pendientes": Decimal(states.get(ConciliacionBancaria.Estado.PENDIENTE, 0)),
        "diferencias": Decimal(states.get(ConciliacionBancaria.Estado.DIFERENCIA, 0)),
        "monto_diferencias": queryset.filter(
            estado=ConciliacionBancaria.Estado.DIFERENCIA
        ).aggregate(total=Sum("diferencia"))["total"]
        or Decimal("0.00"),
    }
