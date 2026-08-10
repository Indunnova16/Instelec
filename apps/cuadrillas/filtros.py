"""
Sistema de filtros ÚNICO de Cuadrillas (issue #218).

Resuelve los filtros activos (semana, línea, actividad, fecha) desde
``request.GET`` UNA sola vez, para reusar el mismo mecanismo tanto en el
listado (``CuadrillaListView``, vía el monkeypatch de ``views_b3.py``) como
en la carga masiva (``CuadrillaUploadView``, ``views_b4.py``) -- contrato
explícito del cliente en el issue: "no debe existir un selector de filtros
aparte solo para la pantalla de importación"; si hay un filtro de línea
activo en pantalla, el Excel que se suba debe acotarse/validarse contra esa
línea.

Antes de este módulo, el filtro de semana vivía reimplementado de forma
independiente en ``views_b3._b3_get_queryset`` y no existían filtros de
línea/actividad/fecha. A6 lo centraliza acá para que agregar un filtro
nuevo no implique tocar 2 lugares (pantalla + import) por separado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FiltrosCuadrilla:
    """Filtros activos, ya parseados y saneados desde el querystring."""

    semana: str = ""  # formato 'WW-YYYY' (ej. '32-2026'), '' = sin filtro
    linea_id: str = ""  # uuid string de lineas.Linea, '' = sin filtro
    actividad_id: str = ""  # uuid string de actividades.TipoActividad, '' = sin filtro
    fecha_desde: str = ""  # 'YYYY-MM-DD'
    fecha_hasta: str = ""  # 'YYYY-MM-DD'

    @property
    def hay_filtro_activo(self) -> bool:
        return bool(
            self.semana
            or self.linea_id
            or self.actividad_id
            or self.fecha_desde
            or self.fecha_hasta
        )

    def querystring_params(self) -> dict:
        """Solo los pares NO vacíos -- para carry-forward vía
        ``<input type="hidden">`` cuando otro filtro/tab cambia (mismo
        patrón que ``_filtro_estado.html`` preserva hoy ``semana``/``codigo``)."""
        out = {}
        if self.semana:
            out["semana"] = self.semana
        if self.linea_id:
            out["linea"] = self.linea_id
        if self.actividad_id:
            out["actividad"] = self.actividad_id
        if self.fecha_desde:
            out["fecha_desde"] = self.fecha_desde
        if self.fecha_hasta:
            out["fecha_hasta"] = self.fecha_hasta
        return out


def resolver_filtros(get_params) -> FiltrosCuadrilla:
    """Lee ``request.GET`` (o cualquier dict/QueryDict con ``.get``) y arma
    un ``FiltrosCuadrilla`` saneado (strip, sin None)."""
    return FiltrosCuadrilla(
        semana=(get_params.get("semana") or "").strip(),
        linea_id=(get_params.get("linea") or "").strip(),
        actividad_id=(get_params.get("actividad") or "").strip(),
        fecha_desde=(get_params.get("fecha_desde") or "").strip(),
        fecha_hasta=(get_params.get("fecha_hasta") or "").strip(),
    )


def _parse_fecha(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def aplicar_filtros_queryset(qs, filtros: FiltrosCuadrilla):
    """Aplica semana + línea + actividad + fecha sobre un queryset de
    ``Cuadrilla``. Los filtros se combinan con AND (intersección), no OR
    (issue #218 A6: "combinación de 2+ filtros simultáneos da la
    intersección correcta, no la unión")."""
    if filtros.semana:
        try:
            partes = filtros.semana.split("-")
            sem = partes[0].zfill(2)
            ano = partes[1]
            qs = qs.filter(codigo__startswith=f"{sem}-{ano}-")
        except (IndexError, ValueError):
            pass

    if filtros.linea_id:
        qs = qs.filter(linea_asignada_id=filtros.linea_id)

    if filtros.actividad_id:
        qs = qs.filter(tipo_actividad_id=filtros.actividad_id)

    fecha_desde = _parse_fecha(filtros.fecha_desde) if filtros.fecha_desde else None
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)

    fecha_hasta = _parse_fecha(filtros.fecha_hasta) if filtros.fecha_hasta else None
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)

    return qs


def linea_permite_fila(filtros: FiltrosCuadrilla, linea_id) -> bool:
    """A7 -- wiring del import: con un filtro de línea activo en pantalla,
    ¿esta fila/bloque del Excel puede crearse/actualizarse? ``True`` si no
    hay filtro de línea activo, o si ``linea_id`` coincide exactamente con
    el filtro. Comparación por string para tolerar UUID vs str indistinto."""
    if not filtros.linea_id:
        return True
    if linea_id is None:
        return False
    return str(linea_id) == str(filtros.linea_id)


def choices_lineas():
    """Líneas activas para poblar el <select> del filtro de línea."""
    from apps.lineas.models import Linea

    return list(
        Linea.objects.filter(activa=True).order_by("codigo").values("id", "codigo", "nombre")
    )


def choices_actividades():
    """Tipos de actividad activos para poblar el <select> del filtro de
    actividad. Nota (F2, data thinness declarada en el PLAN): en prod hoy
    solo 1 Cuadrilla tiene ``tipo_actividad`` seteado -- el dropdown puede
    listar más TipoActividad activos que cuadrillas realmente asignadas,
    eso es esperado, no un bug."""
    from apps.actividades.models import TipoActividad

    return list(
        TipoActividad.objects.filter(activo=True)
        .order_by("nombre")
        .values("id", "codigo", "nombre")
    )
