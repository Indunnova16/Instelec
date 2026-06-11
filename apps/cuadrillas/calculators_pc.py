"""
Calculadores de rendimiento de programación de cuadrillas (#155).

Sub-feature B4 del bloque `programacion_cuadrillas`. Funciones PURAS y
testeables que agregan `ProgramacionSemanalCuadrilla` (+ su `EjecucionSemanal`
1:1) en filas cuadrilla × semana con su rendimiento.

Reglas de diseño (memorias del portafolio):
  - `rendimiento_pct` NO se denormaliza: es una propiedad derivada en
    `EjecucionSemanalCuadrilla`. Acá se recalcula a nivel agregado
    (ejecutadas/programadas × 100) para que un cambio en programadas se refleje
    sin migración.
  - Guard div/0: una fila sin torres programadas → rendimiento 0.0 (no error,
    no NaN, no fila fantasma).
  - Función pura: recibe un queryset, devuelve `list[dict]`. No toca request,
    no localiza números (eso es del template). Reusa `models_pc`, no
    re-implementa el modelo.
"""
from __future__ import annotations

from typing import Iterable

from .models_pc import ProgramacionSemanalCuadrilla


def _rendimiento(programadas: int, ejecutadas: int) -> float:
    """Rendimiento ejecutadas/programadas × 100, con guard div/0."""
    programadas = programadas or 0
    if programadas <= 0:
        return 0.0
    return round((ejecutadas or 0) / programadas * 100, 1)


def rendimiento_por_cuadrilla(qs: Iterable[ProgramacionSemanalCuadrilla] | None) -> list[dict]:
    """Agrega un queryset de programaciones en filas cuadrilla × semana.

    Cada fila::

        {
            'cuadrilla_id':  <uuid str>,
            'cuadrilla':     'CUA-001 - Tendido A',   # codigo - nombre
            'anio':          2026,
            'semana':        23,
            'periodo':       '2026-S23',
            'torres_programadas': 10,
            'torres_ejecutadas':  8,
            'rendimiento_pct':    80.0,               # derivado, guard div/0
        }

    Orden: cuadrilla (codigo), luego semana descendente (más reciente primero
    dentro de cada cuadrilla). Una programación sin ejecución registrada cuenta
    como 0 torres ejecutadas (programó pero no ejecutó → rendimiento bajo, que
    es justo lo que el dashboard debe evidenciar).

    Edge cases cubiertos:
      - qs vacío / None → [] (no error).
      - programación sin ejecución 1:1 → torres_ejecutadas=0, rendimiento_pct=0.0.
      - torres_programadas=0 → rendimiento_pct=0.0 (div/0 guard), no NaN.
    """
    if qs is None:
        return []

    # select_related para no disparar N+1 sobre cuadrilla y la ejecución 1:1.
    try:
        qs = qs.select_related('cuadrilla', 'ejecucion')
    except AttributeError:
        # Ya es un iterable materializado (p.ej. una lista en tests). Lo usamos
        # tal cual — la función debe ser tolerante a inputs no-queryset.
        pass

    filas: list[dict] = []
    for prog in qs:
        ejecucion = getattr(prog, 'ejecucion', None)
        torres_prog = prog.torres_programadas or 0
        torres_ejec = getattr(ejecucion, 'torres_ejecutadas', 0) or 0

        cuadrilla = prog.cuadrilla
        cuadrilla_label = (
            f"{cuadrilla.codigo} - {cuadrilla.nombre}"
            if cuadrilla else 'Sin cuadrilla'
        )

        filas.append({
            'cuadrilla_id': str(prog.cuadrilla_id),
            'cuadrilla': cuadrilla_label,
            'anio': prog.anio,
            'semana': prog.semana,
            'periodo': f"{prog.anio}-S{prog.semana:02d}",
            'torres_programadas': torres_prog,
            'torres_ejecutadas': torres_ejec,
            'rendimiento_pct': _rendimiento(torres_prog, torres_ejec),
        })

    # Orden estable: por etiqueta de cuadrilla asc, luego periodo desc.
    filas.sort(key=lambda f: (f['cuadrilla'], -f['anio'], -f['semana']))
    return filas


def resumen_por_cuadrilla(filas: list[dict]) -> list[dict]:
    """Colapsa las filas cuadrilla × semana a un agregado por cuadrilla.

    Útil para la gráfica/cabecera del dashboard: total programadas, total
    ejecutadas y rendimiento agregado del periodo por cuadrilla.

    Cada item::

        {
            'cuadrilla_id', 'cuadrilla',
            'torres_programadas', 'torres_ejecutadas',
            'rendimiento_pct',     # agregado del periodo (sum/sum), guard div/0
            'semanas': <n filas>,
        }

    Orden: rendimiento descendente (mejor cuadrilla primero), luego nombre.
    """
    acc: dict[str, dict] = {}
    for fila in filas:
        cid = fila['cuadrilla_id']
        item = acc.setdefault(cid, {
            'cuadrilla_id': cid,
            'cuadrilla': fila['cuadrilla'],
            'torres_programadas': 0,
            'torres_ejecutadas': 0,
            'semanas': 0,
        })
        item['torres_programadas'] += fila['torres_programadas']
        item['torres_ejecutadas'] += fila['torres_ejecutadas']
        item['semanas'] += 1

    resumen = list(acc.values())
    for item in resumen:
        item['rendimiento_pct'] = _rendimiento(
            item['torres_programadas'], item['torres_ejecutadas']
        )

    resumen.sort(key=lambda i: (-i['rendimiento_pct'], i['cuadrilla']))
    return resumen
