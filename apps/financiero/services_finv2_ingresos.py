"""Reglas de negocio de facturas de ingreso (#249)."""

from datetime import date

from django.db.models import Max, Sum

from .models import CicloFacturacion


def generar_numero_factura(fecha_emision) -> str:
    """Devuelve el siguiente consecutivo GLOBAL sin persistirlo.

    #249 (regla de negocio confirmada con Miguel): la numeración es
    secuencial GLOBAL, no reinicia por año -- consistente con
    `CicloFacturacion.numero_secuencial` siendo `unique=True` a nivel BD
    (`models_finv2_facturas.py`). La versión anterior calculaba el máximo
    filtrado por año (`fecha_factura__year=...`), lo que reiniciaba el
    consecutivo cada 1 de enero y habría producido un `IntegrityError` en la
    primera factura de cualquier año posterior al primero (numero_secuencial
    duplicado contra el mismo número ya usado en un año previo) -- bug real
    encontrado al verificar el gap 4 contra el código, no una reconstrucción
    gratuita del modelo.

    El año que aparece en el folio (`FI-<año>-<consecutivo>`) sigue siendo el
    de la fecha de emisión -- solo el consecutivo numérico deja de resetear.
    La vista lo invoca dentro de una transacción y vuelve a intentar ante una
    colisión del índice único, de modo que dos emisiones simultáneas no
    puedan entregar el mismo número definitivo.
    """
    if not isinstance(fecha_emision, date):
        raise ValueError("La fecha de emisión es obligatoria.")
    ultimo = (
        CicloFacturacion.objects.filter(
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
