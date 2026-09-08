"""Carga trazable del libro TRANSELCA por proyecto y período (#246).

El importador conserva el flujo #120 y materializa, en cambio, las líneas del
libro de carga en ``CargaFinanciera``.  Una recarga reemplaza atómicamente el
conjunto completo del mismo proyecto/período; nunca intenta deducir duplicados
por fila.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import BinaryIO
import unicodedata
from zipfile import BadZipFile

from django.db import transaction
from openpyxl import load_workbook

from .models_finv2_carga import (
    CargaFinanciera,
    HomologacionProjectsContable,
    LineaCargaFinanciera,
)


HOJAS_REQUERIDAS = ('BD Real', 'BD Ppto', 'Homologacion')


@dataclass
class ResultadoCargaFinanciera:
    """Respuesta estable para la vista B2, incluso cuando la validación falla."""

    exito: bool
    carga: CargaFinanciera | None = None
    error: str | None = None
    resumen: dict = field(default_factory=dict)

    @property
    def errores(self):
        return [self.error] if self.error else []


def _normalizar(valor) -> str:
    texto = '' if valor is None else str(valor).strip().lower()
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return ' '.join(texto.replace('_', ' ').split())


def _texto(valor) -> str:
    return '' if valor is None else str(valor).strip()


def _decimal(valor, *, hoja: str, fila: int, columna: str) -> Decimal:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ValueError(f"{hoja}, fila {fila}: '{columna}' es obligatorio.")
    try:
        return Decimal(str(valor).replace(',', '').strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, AttributeError):
        raise ValueError(
            f"{hoja}, fila {fila}: '{columna}' debe ser un valor numérico válido."
        ) from None


def _periodo_real(valor_periodo, valor_fecha, *, hoja: str, fila: int) -> tuple[int, int]:
    if isinstance(valor_fecha, datetime):
        return valor_fecha.year, valor_fecha.month
    if isinstance(valor_fecha, date):
        return valor_fecha.year, valor_fecha.month
    digits = ''.join(ch for ch in _texto(valor_periodo) if ch.isdigit())
    if len(digits) >= 6:
        anio, mes = int(digits[:4]), int(digits[4:6])
        if 1 <= mes <= 12:
            return anio, mes
    raise ValueError(
        f"{hoja}, fila {fila}: 'Periodo' o 'Fecha' debe identificar un mes válido."
    )


def _hoja(libro, nombre):
    buscada = _normalizar(nombre)
    return next((libro[n] for n in libro.sheetnames if _normalizar(n) == buscada), None)


def _columnas(hoja, requeridas: set[str]) -> dict[str, int]:
    encabezados = {
        _normalizar(celda.value): indice
        for indice, celda in enumerate(hoja[1], start=1)
        if _normalizar(celda.value)
    }
    # El libro TRANSELCA usa ``Cuenta Equiv``; el contrato #120 documentó
    # ``Cta equivalente``. Ambos designan exactamente la misma columna.
    if 'cta equivalente' in encabezados and 'cuenta equiv' not in encabezados:
        encabezados['cuenta equiv'] = encabezados['cta equivalente']
    faltantes = sorted(requeridas - encabezados.keys())
    if faltantes:
        raise ValueError(
            f"La hoja '{hoja.title}' no tiene las columnas requeridas: "
            f"{', '.join(faltantes)}."
        )
    return encabezados


def _valor(fila, columnas, nombre):
    indice = columnas.get(_normalizar(nombre))
    return fila[indice - 1] if indice else None


def _catalogo_homologaciones():
    """Carga el catálogo una vez: el oráculo tiene más de 14 mil filas."""
    return {
        (_normalizar(h.tipo), _normalizar(h.grupo), _normalizar(h.concepto), _normalizar(h.rubro)): h
        for h in HomologacionProjectsContable.objects.filter(activo=True)
    }


def _buscar_homologacion(catalogo, tipo, grupo, concepto, rubro):
    """Busca sólo catálogo vigente; el Excel no altera decisiones internas."""
    return catalogo.get(
        (_normalizar(tipo), _normalizar(grupo), _normalizar(concepto), _normalizar(rubro))
    )


def _lineas_reales(hoja, anio, mes, catalogo):
    columnas = _columnas(hoja, {'neto', 'fecha', 'periodo', 'cuenta equiv', 'cdec equiv'})
    lineas = []
    for numero, fila in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
        if not any(valor is not None and _texto(valor) for valor in fila):
            continue
        fila_anio, fila_mes = _periodo_real(
            _valor(fila, columnas, 'periodo'), _valor(fila, columnas, 'fecha'),
            hoja=hoja.title, fila=numero,
        )
        if (fila_anio, fila_mes) != (anio, mes):
            continue
        concepto = _texto(_valor(fila, columnas, 'desc. auxiliar')) or _texto(
            _valor(fila, columnas, 'cuenta equiv')
        )
        grupo = _texto(_valor(fila, columnas, 'cuenta equiv'))
        rubro = _texto(_valor(fila, columnas, 'cdec equiv'))
        if not concepto or not grupo:
            raise ValueError(f"{hoja.title}, fila {numero}: falta cuenta o concepto contable.")
        homologacion = _buscar_homologacion(catalogo, 'REAL', grupo, concepto, rubro)
        lineas.append({
            'tipo': LineaCargaFinanciera.Tipo.REAL,
            'grupo': grupo,
            'concepto': concepto,
            'rubro': rubro,
            'valor': _decimal(_valor(fila, columnas, 'neto'), hoja=hoja.title, fila=numero, columna='Neto'),
            'referencia': _texto(_valor(fila, columnas, 'docto.')),
            'fila_origen': numero,
            'homologacion': homologacion,
            'datos_origen': {'fecha': _texto(_valor(fila, columnas, 'fecha')), 'periodo': _texto(_valor(fila, columnas, 'periodo'))},
        })
    return lineas


def _lineas_presupuesto(hoja, proyecto, anio, mes, catalogo):
    columnas = _columnas(hoja, {'proyecto', 'rubro', 'clasificacion', 'valor', 'mes', 'ano'})
    lineas = []
    nombre_proyecto = _normalizar(proyecto.nombre)
    for numero, fila in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
        if not any(valor is not None and _texto(valor) for valor in fila):
            continue
        try:
            fila_anio, fila_mes = int(_valor(fila, columnas, 'ano')), int(_valor(fila, columnas, 'mes'))
        except (TypeError, ValueError):
            raise ValueError(f"{hoja.title}, fila {numero}: 'año' y 'mes' deben ser enteros válidos.") from None
        if not 1 <= fila_mes <= 12:
            raise ValueError(f"{hoja.title}, fila {numero}: 'mes' debe estar entre 1 y 12.")
        if (fila_anio, fila_mes) != (anio, mes):
            continue
        origen = _texto(_valor(fila, columnas, 'proyecto'))
        if _normalizar(origen) != nombre_proyecto:
            continue
        concepto = _texto(_valor(fila, columnas, 'rubro'))
        grupo = _texto(_valor(fila, columnas, 'clasificacion'))
        if not concepto:
            raise ValueError(f"{hoja.title}, fila {numero}: 'Rubro' es obligatorio.")
        homologacion = _buscar_homologacion(catalogo, 'PRESUPUESTO', grupo, concepto, concepto)
        lineas.append({
            'tipo': LineaCargaFinanciera.Tipo.PRESUPUESTO,
            'grupo': grupo,
            'concepto': concepto,
            'rubro': concepto,
            'valor': _decimal(_valor(fila, columnas, 'valor'), hoja=hoja.title, fila=numero, columna='Valor'),
            'referencia': origen,
            'fila_origen': numero,
            'homologacion': homologacion,
            'datos_origen': {'clasificacion': grupo, 'proyecto': origen},
        })
    return lineas


def _validar_homologacion(hoja):
    """El libro debe traer la hoja; sus filas se preservan como conteo de origen."""
    _columnas(hoja, {'tipo', 'grupo', 'concepto', 'rubro'})
    return sum(1 for fila in hoja.iter_rows(min_row=2, values_only=True) if any(_texto(v) for v in fila))


def procesar_carga_financiera(archivo: BinaryIO, *, proyecto, anio, mes, usuario) -> ResultadoCargaFinanciera:
    """Valida y materializa un Excel TRANSELCA para un período seleccionado."""
    if not 1 <= int(mes) <= 12:
        return ResultadoCargaFinanciera(False, error='El mes debe estar entre 1 y 12.')
    try:
        libro = load_workbook(archivo, read_only=True, data_only=True)
        hojas = {nombre: _hoja(libro, nombre) for nombre in HOJAS_REQUERIDAS}
        faltantes = [nombre for nombre, hoja in hojas.items() if hoja is None]
        if faltantes:
            return ResultadoCargaFinanciera(
                False, error=f"Faltan hojas requeridas: {', '.join(faltantes)}."
            )
        catalogo = _catalogo_homologaciones()
        reales = _lineas_reales(hojas['BD Real'], int(anio), int(mes), catalogo)
        presupuestos = _lineas_presupuesto(hojas['BD Ppto'], proyecto, int(anio), int(mes), catalogo)
        homologaciones = _validar_homologacion(hojas['Homologacion'])
        if not reales and not presupuestos:
            return ResultadoCargaFinanciera(
                False, error=f'El libro no contiene líneas para {int(mes):02d}/{anio} y el proyecto seleccionado.'
            )
    except (ValueError, OSError, KeyError, BadZipFile) as exc:
        return ResultadoCargaFinanciera(False, error=str(exc))

    resumen = {
        'lineas_reales': len(reales),
        'lineas_presupuesto': len(presupuestos),
        'lineas_homologacion_origen': homologaciones,
        'total_real': str(sum((l['valor'] for l in reales), Decimal('0.00'))),
        'total_presupuesto': str(sum((l['valor'] for l in presupuestos), Decimal('0.00'))),
    }
    with transaction.atomic():
        # Eliminar sólo este período/proyecto; las cascadas eliminan sus líneas.
        CargaFinanciera.objects.filter(proyecto=proyecto, anio=anio, mes=mes).delete()
        carga = CargaFinanciera.objects.create(
            proyecto=proyecto, anio=anio, mes=mes, usuario=usuario,
            estado=CargaFinanciera.Estado.PROCESADA,
            nombre_archivo=_texto(getattr(archivo, 'name', '')),
            resumen=resumen,
        )
        LineaCargaFinanciera.objects.bulk_create([
            LineaCargaFinanciera(carga=carga, **linea) for linea in [*reales, *presupuestos]
        ], batch_size=1000)
    return ResultadoCargaFinanciera(True, carga=carga, resumen=resumen)
