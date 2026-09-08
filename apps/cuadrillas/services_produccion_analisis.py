"""Cálculos para el análisis comparativo de Producción Diaria (#252, #225)."""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Avg, Sum

from .models_pc import EjecucionSemanalCuadrilla
from .models_produccion_diaria import (
    ActividadProduccion,
    ProduccionDiaria,
    RegistroPersonalProduccion,
)

ESTADO_SIN_DATO = "SIN_DATO"
ESTADO_SIN_BASE = "SIN_BASE"
ESTADO_DISPONIBLE = "DISPONIBLE"


def calcular_varianza_pct(real, programado):
    """Calcula ``(real - programado) / programado`` sin dividir por cero."""
    if programado is None or Decimal(str(programado)) <= 0:
        return None
    real = Decimal(str(real or 0))
    programado = Decimal(str(programado))
    return ((real - programado) / programado * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def construir_analisis(programacion):
    """Resume programación, ejecución y producción diaria de una cuadrilla.

    La programación es la única base para comparar torres. Si todavía no existe
    una ejecución semanal, se expone explícitamente ``SIN_DATO``: un promedio de
    avances de actividades no equivale a cantidad de torres y no se usa para
    inventar una varianza.
    """
    producciones = ProduccionDiaria.objects.filter(programacion=programacion)
    # ``count()`` conserva semántica cero para un queryset vacío en todos los
    # backends que soporta el proyecto.
    dias_reportados = producciones.count()
    actividades = ActividadProduccion.objects.filter(produccion__programacion=programacion)
    personal = RegistroPersonalProduccion.objects.filter(produccion__programacion=programacion)
    avance_real = actividades.aggregate(valor=Avg("avance_pct"))["valor"]
    horas_reales = personal.aggregate(valor=Sum("horas_trabajadas"))["valor"]

    ejecucion = (
        EjecucionSemanalCuadrilla.objects.filter(programacion=programacion)
        .only("torres_ejecutadas")
        .first()
    )
    torres_programadas = programacion.torres_programadas or 0
    if torres_programadas <= 0:
        estado_torres = ESTADO_SIN_BASE
        torres_ejecutadas = None
        varianza_torres = None
    elif ejecucion is None:
        estado_torres = ESTADO_SIN_DATO
        torres_ejecutadas = None
        varianza_torres = None
    else:
        estado_torres = ESTADO_DISPONIBLE
        torres_ejecutadas = ejecucion.torres_ejecutadas
        varianza_torres = calcular_varianza_pct(torres_ejecutadas, torres_programadas)

    return {
        "programacion": programacion,
        "estado_torres": estado_torres,
        "torres_programadas": torres_programadas,
        "torres_ejecutadas": torres_ejecutadas,
        "varianza_torres_pct": varianza_torres,
        "dias_reportados": dias_reportados,
        "horas_reales": horas_reales or Decimal("0"),
        "avance_promedio_pct": avance_real,
        "actividades_reportadas": actividades.count(),
    }
