"""
B4 — Calculadoras / agregadores para el dashboard de mantenimiento detallado.

Provee:
- ``tendencia_ans_6_meses(linea=None, hasta=None)``: serie temporal del puntaje
  total ANS para el line chart de Chart.js.
- ``serie_componentes_ans(linea, anio, mes)``: barras progress por componente.
- ``resumen_mensual(linea, anio, mes)``: dict con los 3 indicadores listos
  para el dashboard.

Todas las funciones tolerantes a ausencia de datos: devuelven estructuras
vacias en vez de fallar.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from django.utils import timezone

from .models_b4_mantenimiento_detallado import (
    IndicadorANSContractual,
    IndicadorMantenimientoFinanciero,
    IndicadorMantenimientoTecnico,
)


def _periodo_anterior(anio: int, mes: int) -> tuple[int, int]:
    if mes == 1:
        return anio - 1, 12
    return anio, mes - 1


def tendencia_ans_6_meses(
    linea=None, hasta: Optional[date] = None
) -> dict:
    """
    Devuelve serie temporal de los ultimos 6 meses (incluyendo el actual).

    Output shape (compatible Chart.js):
        {
          "labels": ["12/2025", "01/2026", ...],
          "puntaje_total": [82.5, 88.1, ...],
          "programacion": [...],
          "ejecucion": [...],
          "info_contractual": [...],
          "info_ambiental": [...],
          "disponibilidad": [...],
        }

    Edge case: cuando no hay registro para un periodo, se inyecta ``None``
    para que Chart.js dibuje un gap en la serie en vez de extrapolar.
    """
    if hasta is None:
        hasta = timezone.localdate()

    labels: list[str] = []
    series_keys = [
        "puntaje_total",
        "programacion",
        "ejecucion",
        "info_contractual",
        "info_ambiental",
        "disponibilidad",
    ]
    series: dict[str, list] = {k: [] for k in series_keys}

    anio, mes = hasta.year, hasta.month
    periodos: list[tuple[int, int]] = []
    for _ in range(6):
        periodos.append((anio, mes))
        anio, mes = _periodo_anterior(anio, mes)
    periodos.reverse()  # cronologico ascendente

    qs = IndicadorANSContractual.objects.all()
    if linea is not None:
        qs = qs.filter(linea=linea)
    else:
        qs = qs.filter(linea__isnull=True)

    by_periodo = {(r.anio, r.mes): r for r in qs.filter(
        anio__gte=periodos[0][0]
    )}

    for (a, m) in periodos:
        labels.append(f"{m:02d}/{a}")
        r = by_periodo.get((a, m))
        if r is None:
            for k in series_keys:
                series[k].append(None)
        else:
            series["puntaje_total"].append(float(r.puntaje_total_ans))
            series["programacion"].append(float(r.cumplimiento_programacion))
            series["ejecucion"].append(float(r.cumplimiento_ejecucion))
            series["info_contractual"].append(
                float(r.cumplimiento_informacion_contractual)
            )
            series["info_ambiental"].append(
                float(r.cumplimiento_informacion_ambiental)
            )
            series["disponibilidad"].append(
                float(r.cumplimiento_disponibilidad_circuitos)
            )

    return {"labels": labels, **series}


def serie_componentes_ans(
    linea=None, anio: Optional[int] = None, mes: Optional[int] = None
) -> Optional[IndicadorANSContractual]:
    """
    Devuelve el ANS del periodo solicitado (o el mas reciente disponible).

    Edge case: si no hay ningun registro, devuelve None — la vista renderiza
    un placeholder "sin datos".
    """
    qs = IndicadorANSContractual.objects.all()
    if linea is not None:
        qs = qs.filter(linea=linea)
    else:
        qs = qs.filter(linea__isnull=True)
    if anio is not None:
        qs = qs.filter(anio=anio)
    if mes is not None:
        qs = qs.filter(mes=mes)
    return qs.order_by("-anio", "-mes").first()


def resumen_mensual(
    linea=None, anio: Optional[int] = None, mes: Optional[int] = None
) -> dict:
    """
    Dict completo para el dashboard del mes. Tolerante a None en cualquier
    seccion.
    """
    hoy = timezone.localdate()
    anio = anio or hoy.year
    mes = mes or hoy.month

    fin_qs = IndicadorMantenimientoFinanciero.objects.all()
    tec_qs = IndicadorMantenimientoTecnico.objects.all()
    ans_qs = IndicadorANSContractual.objects.all()
    if linea is not None:
        fin_qs = fin_qs.filter(linea=linea)
        tec_qs = tec_qs.filter(linea=linea)
        ans_qs = ans_qs.filter(linea=linea)
    else:
        fin_qs = fin_qs.filter(linea__isnull=True)
        tec_qs = tec_qs.filter(linea__isnull=True)
        ans_qs = ans_qs.filter(linea__isnull=True)

    financiero = fin_qs.filter(anio=anio, mes=mes).first()
    tecnico = tec_qs.filter(anio=anio, mes=mes).first()
    ans = ans_qs.filter(anio=anio, mes=mes).first()

    return {
        "anio": anio,
        "mes": mes,
        "financiero": financiero,
        "tecnico": tecnico,
        "ans": ans,
        "has_data": any([financiero, tecnico, ans]),
    }
