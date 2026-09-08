"""Reglas de negocio del flujo de facturas de gasto (#248)."""
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from .models_finv2_facturas import FacturaGasto, PagoFacturaGasto


IVA_ESTANDAR = Decimal('0.19')
UMBRAL_APROBACION = Decimal('1000000.00')
CENTAVOS = Decimal('0.01')


def calcular_totales(valor_base, *, tasa_iva=Decimal('0.19')) -> dict:
    """Calcula IVA y total sin introducir errores de coma flotante."""
    try:
        base = Decimal(valor_base)
        tasa = Decimal(tasa_iva)
    except (TypeError, ValueError, ArithmeticError) as error:
        raise ValidationError('El valor base y la tasa de IVA deben ser numéricos.') from error
    if base <= 0:
        raise ValidationError('El subtotal debe ser mayor que cero.')
    if tasa < 0 or tasa > 1:
        raise ValidationError('La tasa de IVA debe estar entre 0 y 1.')
    iva = (base * tasa).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    return {'subtotal': base.quantize(CENTAVOS), 'iva': iva, 'total': base.quantize(CENTAVOS) + iva}


def estado_inicial_gasto(total):
    return (FacturaGasto.Estado.PENDIENTE_APROBACION
            if Decimal(total) > UMBRAL_APROBACION else FacturaGasto.Estado.PENDIENTE_PAGO)


@transaction.atomic
def aprobar_gasto(factura, comentario=''):
    if factura.estado != FacturaGasto.Estado.PENDIENTE_APROBACION:
        raise ValidationError('Solo se pueden aprobar facturas pendientes de aprobación.')
    factura.estado = FacturaGasto.Estado.PENDIENTE_PAGO
    factura.comentario_decision = comentario.strip()
    factura.save(update_fields=['estado', 'comentario_decision', 'updated_at'])
    return factura


@transaction.atomic
def registrar_pago_gasto(factura, *, banco, metodo_pago, fecha, monto, referencia):
    monto = Decimal(monto)
    referencia = (referencia or '').strip()
    if factura.estado != FacturaGasto.Estado.PENDIENTE_PAGO:
        raise ValidationError('La factura debe estar aprobada antes de registrar el pago.')
    if monto != factura.total:
        raise ValidationError('El pago debe cubrir exactamente el total de la factura.')
    if not referencia:
        raise ValidationError('La referencia de pago es obligatoria.')
    pago = PagoFacturaGasto.objects.create(
        factura=factura, banco=banco, metodo_pago=metodo_pago, fecha=fecha,
        monto=monto, referencia=referencia,
    )
    factura.banco = banco
    factura.metodo_pago = metodo_pago
    factura.referencia_pago = referencia
    factura.estado = FacturaGasto.Estado.PAGADA
    factura.save(update_fields=['banco', 'metodo_pago', 'referencia_pago', 'estado', 'updated_at'])
    return pago
