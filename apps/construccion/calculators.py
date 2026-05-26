"""Calculators puros para indicadores de construcción (B2).

Funciones puras: reciben primitivas, retornan primitivas o None.
No dependen de Django ORM — fácilmente testeables y reusables desde
otros módulos (Celery tasks, REST API, signals).

Cada función protege contra división por cero retornando None.
Los modelos B2 invocan estos calculators desde save() para auto-llenar
los campos derivados.
"""
from decimal import Decimal, InvalidOperation
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_decimal(value) -> Optional[Decimal]:
    """Convierte a Decimal si es posible, None en caso contrario."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _safe_pct(numerador, denominador) -> Optional[float]:
    """Calcula (n/d) * 100 protegido. Si d es 0 o None, retorna None."""
    n = _to_decimal(numerador)
    d = _to_decimal(denominador)
    if n is None or d is None or d == 0:
        return None
    return float((n / d) * Decimal('100'))


# ---------------------------------------------------------------------------
# INDICADORES FINANCIEROS
# ---------------------------------------------------------------------------

def calcular_margen_operativo(ingresos_ejecutados, costos_directos, gastos) -> Optional[float]:
    """Margen Operativo = (IE - (CD + G)) / IE * 100.

    Meta: ≥ 15%. Retorna None si ingresos_ejecutados es 0 o None.
    """
    ie = _to_decimal(ingresos_ejecutados)
    cd = _to_decimal(costos_directos) or Decimal('0')
    g = _to_decimal(gastos) or Decimal('0')
    if ie is None or ie == 0:
        return None
    return float(((ie - (cd + g)) / ie) * Decimal('100'))


def calcular_desviacion_presupuestal(costo_real, costo_presupuestado) -> Optional[float]:
    """Desviación Presupuestal = (CR - CP) / CP * 100.

    Meta: ≤ 15%. Retorna None si costo_presupuestado es 0 o None.
    """
    cr = _to_decimal(costo_real)
    cp = _to_decimal(costo_presupuestado)
    if cr is None or cp is None or cp == 0:
        return None
    return float(((cr - cp) / cp) * Decimal('100'))


# ---------------------------------------------------------------------------
# INDICADORES TÉCNICOS — 11 campos derivados
# ---------------------------------------------------------------------------

def calcular_ejecucion_presupuestal(presupuesto_ejecutado_pct, presupuesto_planeado_pct) -> Optional[float]:
    """Ejecución Presupuestal = %PE / %PP * 100. Meta ≥ 100%."""
    return _safe_pct(presupuesto_ejecutado_pct, presupuesto_planeado_pct)


def calcular_avance_obra(obra_ejecutada, obra_programada) -> Optional[float]:
    """Avance de Obra = OE / OP * 100. Meta según plan."""
    return _safe_pct(obra_ejecutada, obra_programada)


def calcular_cumplimiento_cronograma(actividades_completadas, actividades_planificadas) -> Optional[float]:
    """Cumplimiento Cronograma = AC / AP * 100. Meta ≥ 95%."""
    return _safe_pct(actividades_completadas, actividades_planificadas)


def calcular_productividad(cantidad_ejecutada, horas_hombre) -> Optional[float]:
    """Productividad = CE / HH * 100. Meta ≥ 100%."""
    return _safe_pct(cantidad_ejecutada, horas_hombre)


def calcular_rendimiento_cuadrillas(cantidad_ejecutada, horas_hombre) -> Optional[float]:
    """Rendimiento Cuadrillas = CE / HH * 100. Meta ≥ 3.95%.
    Misma fórmula que productividad pero meta distinta y semántica de cuadrillas.
    """
    return _safe_pct(cantidad_ejecutada, horas_hombre)


# ---------------------------------------------------------------------------
# DESEMPEÑO LÍNEA — clasificación de estado
# ---------------------------------------------------------------------------

# Tolerancia: ±5% se considera "en meta"
TOLERANCIA_ESTADO = Decimal('0.05')


def clasificar_estado_desempeno(actual, meta) -> str:
    """Clasifica el desempeño según actual vs meta.

    Retorna uno de: 'EN_META', 'BAJO_META', 'SOBRE_META', 'SIN_DATOS'.

    Reglas:
    - Si meta o actual es None/0 → SIN_DATOS.
    - Si |actual/meta - 1| <= 5% → EN_META.
    - Si actual < meta * 0.95 → BAJO_META.
    - Si actual > meta * 1.05 → SOBRE_META.
    """
    a = _to_decimal(actual)
    m = _to_decimal(meta)
    if a is None or m is None or m == 0:
        return 'SIN_DATOS'
    ratio = a / m
    diff = abs(ratio - Decimal('1'))
    if diff <= TOLERANCIA_ESTADO:
        return 'EN_META'
    if ratio < Decimal('1'):
        return 'BAJO_META'
    return 'SOBRE_META'


# ---------------------------------------------------------------------------
# Helpers para clasificación semáforo (usado en dashboard B3)
# ---------------------------------------------------------------------------

def clasificar_margen_operativo(margen: Optional[float]) -> str:
    """Margen ≥15% → EN_META; 12-15% → BAJO_META; <12% → CRITICO."""
    if margen is None:
        return 'SIN_DATOS'
    if margen >= 15:
        return 'EN_META'
    if margen >= 12:
        return 'BAJO_META'
    return 'CRITICO'


def clasificar_desviacion_presupuestal(desviacion: Optional[float]) -> str:
    """Desviación ≤15% → EN_META; 15-20% → BAJO_META; >20% → CRITICO."""
    if desviacion is None:
        return 'SIN_DATOS'
    if desviacion <= 15:
        return 'EN_META'
    if desviacion <= 20:
        return 'BAJO_META'
    return 'CRITICO'


def clasificar_cumplimiento(pct: Optional[float], meta: float = 95.0) -> str:
    """Clasificación genérica % vs meta (default 95%)."""
    if pct is None:
        return 'SIN_DATOS'
    if pct >= meta:
        return 'EN_META'
    if pct >= meta * 0.8:
        return 'BAJO_META'
    return 'CRITICO'
