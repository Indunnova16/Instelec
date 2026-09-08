"""Servicios puros y persistentes compartidos por Producción Diaria (#252)."""

from decimal import ROUND_HALF_UP, Decimal

from .models_produccion_diaria import AlertaProduccion

UMBRAL_DESVIACION_PCT = Decimal("20")


def calcular_desviacion_pct(real, programado):
    """Retorna la desviación porcentual; sin base programada no inventa un valor."""
    real = Decimal(str(real or 0))
    programado = Decimal(str(programado or 0))
    if programado <= 0:
        return None
    return ((real - programado) / programado * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def sincronizar_alerta_desviacion(produccion, real, programado):
    """Crea/actualiza una alerta solamente cuando la desviación supera 20 %."""
    desviacion = calcular_desviacion_pct(real, programado)
    if desviacion is None or abs(desviacion) <= UMBRAL_DESVIACION_PCT:
        AlertaProduccion.objects.filter(produccion=produccion).delete()
        return None
    return AlertaProduccion.objects.update_or_create(
        produccion=produccion,
        defaults={
            "desviacion_pct": desviacion,
            "mensaje": f"Desviación de {desviacion}% frente a lo programado.",
        },
    )[0]
