"""Reglas de negocio de facturas de ingreso (#249)."""

from datetime import date

from django.db.models import Max

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
