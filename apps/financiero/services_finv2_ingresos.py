"""Reglas de negocio de facturas de ingreso (#249)."""

from datetime import date

from django.db.models import Max, Sum

from .models import CicloFacturacion


def generar_numero_factura(fecha_emision) -> str:
    """Devuelve el siguiente consecutivo anual sin persistirlo.

    La vista lo invoca dentro de una transacción y vuelve a intentar ante una
    colisión del índice único, de modo que dos emisiones simultáneas no puedan
    entregar el mismo número definitivo.
    """
    if not isinstance(fecha_emision, date):
        raise ValueError("La fecha de emisión es obligatoria.")
    ultimo = (
        CicloFacturacion.objects.filter(
            fecha_factura__year=fecha_emision.year,
            numero_secuencial__isnull=False,
        ).aggregate(Max("numero_secuencial"))["numero_secuencial__max"]
        or 0
    )
    return f"FI-{fecha_emision.year}-{ultimo + 1:05d}"


def facturacion_real_vs_meta(presupuesto):
    """Resume la facturación emitida asociada a un presupuesto sin bloquearla."""
    real = presupuesto.ciclos_facturacion.filter(numero_secuencial__isnull=False).aggregate(
        total=Sum("total")
    )["total"] or 0
    meta = presupuesto.facturacion_esperada
    return {"presupuesto": presupuesto, "real": real, "meta": meta, "supera_meta": bool(meta and real > meta)}
