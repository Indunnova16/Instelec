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
import time
import unicodedata
from zipfile import BadZipFile

from django.db import transaction
from openpyxl import load_workbook

from .models_finv2_carga import (
    CargaFinanciera,
    HomologacionProjectsContable,
    LineaCargaFinanciera,
    VersionHomologacionProjectsContable,
)


HOJAS_REQUERIDAS = ('BD Real', 'BD Ppto', 'Homologacion')
HOJAS_TABLA_MAESTRA = ('INGRESOS', 'GASTOS')


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
    # Los encabezados TRANSELCA mezclan puntuación (``Desc. C.O. movto.``),
    # mayúsculas, acentos y espacios finales. La clave de contrato no depende
    # de ninguna de esas presentaciones.
    return ' '.join(''.join(' ' if not c.isalnum() else c for c in texto).split())


def _texto(valor) -> str:
    return '' if valor is None else str(valor).strip()


def _decimal(valor, *, hoja: str, fila: int, columna: str) -> Decimal:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ValueError(f"{hoja}, fila {fila}, columna '{columna}': es obligatorio.")
    try:
        return Decimal(str(valor).replace(',', '').strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, AttributeError):
        raise ValueError(
            f"{hoja}, fila {fila}, columna '{columna}': debe ser un valor numérico válido."
        ) from None


def resolver_periodo_flexible(fila, columnas: dict[str, int], *, hoja: str, fila_numero: int) -> tuple[int, int]:
    """Resuelve ``Periodo`` YYYYMM o la pareja real ``mes`` + ``año``.

    El error incluye siempre el libro lógico, fila de Excel y columna implicada
    para que el usuario pueda corregir el archivo sin inspección técnica.
    """
    periodo = _valor(fila, columnas, 'periodo')
    fecha = _valor(fila, columnas, 'fecha')
    if periodo is not None and _texto(periodo):
        digits = ''.join(ch for ch in _texto(periodo) if ch.isdigit())
        if len(digits) >= 6:
            anio, mes = int(digits[:4]), int(digits[4:6])
            if 1 <= mes <= 12:
                return anio, mes
        raise ValueError(f"{hoja}, fila {fila_numero}, columna 'Periodo': debe identificar YYYYMM válido.")
    if 'mes' in columnas and 'ano' in columnas:
        try:
            anio, mes = int(_valor(fila, columnas, 'ano')), int(_valor(fila, columnas, 'mes'))
        except (TypeError, ValueError):
            raise ValueError(f"{hoja}, fila {fila_numero}, columnas 'año'/'mes': deben ser enteros válidos.") from None
        if 1 <= mes <= 12:
            return anio, mes
        raise ValueError(f"{hoja}, fila {fila_numero}, columna 'mes': debe estar entre 1 y 12.")
    if isinstance(fecha, datetime):
        return fecha.year, fecha.month
    if isinstance(fecha, date):
        return fecha.year, fecha.month
    raise ValueError(f"{hoja}, fila {fila_numero}, columna 'Periodo' o 'Fecha': debe identificar un mes válido.")


# Matriz explícita de etiquetas vistas en TRANSELCA y en el contrato anterior.
# Todas pasan además por _normalizar: caso, tilde, puntos y espacios son inocuos.
SINONIMOS_HEADERS = {
    'cuenta equiv': {'cuenta equiv', 'cta equivalente'},
    'cdec equiv': {'cdec equiv', 'c de c equiv'},
    'desc auxiliar': {'desc auxiliar', 'descripcion auxiliar'},
    'desc c o movto': {'desc c o movto'},
    'docto': {'docto', 'documento'},
    'ano': {'ano'},
    # Gap 2 (validador-cierre round-1, Instelec#247): el issue documentó al
    # cliente el esquema real de la Tabla Maestra -'Concepto Projects' /
    # 'Código' / 'Cuenta Contable' / 'Descripción'- que NO coincide con el
    # esquema técnico viejo ('concepto'/'codigo contable'/'grupo'/'tipo'
    # exactos). Mismo patrón que el parser TRANSELCA: sinónimos
    # case/acento-insensitive, no un check exacto de string.
    'concepto': {'concepto', 'concepto projects'},
    'codigo contable': {'codigo contable', 'cuenta contable', 'codigo'},
    'descripcion': {'descripcion'},
}


def normalizar_headers(hoja) -> dict[str, int]:
    """Devuelve columnas canónicas del Excel, con aliases TRANSELCA."""
    encabezados = {
        _normalizar(celda.value): indice
        for indice, celda in enumerate(hoja[1], start=1)
        if _normalizar(celda.value)
    }
    for canonico, aliases in SINONIMOS_HEADERS.items():
        for alias in aliases:
            if alias in encabezados:
                encabezados.setdefault(canonico, encabezados[alias])
                break
    return encabezados


def _hoja(libro, nombre):
    buscada = _normalizar(nombre)
    return next((libro[n] for n in libro.sheetnames if _normalizar(n) == buscada), None)


def _columnas(hoja, requeridas: set[str]) -> dict[str, int]:
    encabezados = normalizar_headers(hoja)
    faltantes = sorted(requeridas - encabezados.keys())
    if faltantes:
        raise ValueError(
            f"{hoja.title}, fila 1, columna de encabezados: faltan {', '.join(faltantes)}."
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


def _tipo_operacional_real(fila, columnas, *, hoja: str, fila_numero: int) -> tuple[str, dict]:
    """Clasifica sólo cuando la descripción operacional lo sustenta."""
    columna = 'desc c o movto'
    valor_fuente = _texto(_valor(fila, columnas, columna))
    normalizado = _normalizar(valor_fuente)
    if 'mantenimiento' in normalizado:
        valor = LineaCargaFinanciera.TipoOperacional.MANTENIMIENTO
    elif 'construccion' in normalizado:
        valor = LineaCargaFinanciera.TipoOperacional.CONSTRUCCION
    else:
        valor = LineaCargaFinanciera.TipoOperacional.SIN_CLASIFICAR
    return valor, {
        'valor_fuente': valor_fuente or None,
        'columna_fuente': 'Desc. C.O. movto.',
        'hoja_fuente': hoja,
        'fila_fuente': fila_numero,
        'regla': 'descripcion_operacional',
    }


def _lineas_reales(hoja, anio, mes, catalogo):
    columnas = _columnas(hoja, {'neto', 'periodo', 'cuenta equiv', 'cdec equiv'})
    lineas = []
    for numero, fila in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
        if not any(valor is not None and _texto(valor) for valor in fila):
            continue
        fila_anio, fila_mes = resolver_periodo_flexible(
            fila, columnas, hoja=hoja.title, fila_numero=numero,
        )
        if (fila_anio, fila_mes) != (anio, mes):
            continue
        concepto = _texto(_valor(fila, columnas, 'desc. auxiliar')) or _texto(
            _valor(fila, columnas, 'cuenta equiv')
        )
        grupo = _texto(_valor(fila, columnas, 'cuenta equiv'))
        rubro = _texto(_valor(fila, columnas, 'cdec equiv'))
        if not grupo:
            raise ValueError(f"{hoja.title}, fila {numero}, columna 'Cuenta Equiv': es obligatorio.")
        if not concepto:
            raise ValueError(
                f"{hoja.title}, fila {numero}, columna 'Desc. auxiliar' o 'Cuenta Equiv': es obligatorio."
            )
        homologacion = _buscar_homologacion(catalogo, 'REAL', grupo, concepto, rubro)
        tipo_operacional, trazabilidad_tipo = _tipo_operacional_real(
            fila, columnas, hoja=hoja.title, fila_numero=numero,
        )
        lineas.append({
            'tipo': LineaCargaFinanciera.Tipo.REAL,
            'grupo': grupo,
            'concepto': concepto,
            'rubro': rubro,
            'valor': _decimal(_valor(fila, columnas, 'neto'), hoja=hoja.title, fila=numero, columna='Neto'),
            'referencia': _texto(_valor(fila, columnas, 'docto.')),
            'fila_origen': numero,
            'homologacion': homologacion,
            'tipo_operacional': tipo_operacional,
            'periodo': fila_anio * 100 + fila_mes,
            'cdec_equiv': rubro,
            'centro_costo': _texto(_valor(fila, columnas, 'c costo')),
            'datos_origen': {
                'fecha': _texto(_valor(fila, columnas, 'fecha')),
                'periodo': _texto(_valor(fila, columnas, 'periodo')),
                'tipo_operacional': trazabilidad_tipo,
            },
        })
    return lineas


def _lineas_presupuesto(hoja, anio, mes, catalogo):
    """Extrae las líneas de BD Ppto del período seleccionado.

    Gap 1 (validador-cierre round-1, Instelec#247): antes se exigía que la
    columna 'Proyecto' del Excel coincidiera EXACTO (normalizado) con
    ``Contrato.nombre``. El archivo real del cliente dice 'Transelca' en esa
    columna pero ningún Contrato del sistema se llama así -> la comparación
    quedaba estructuralmente inalcanzable. `_lineas_reales` (la función
    hermana para BD Real) NUNCA verificó `proyecto` -sólo filtra por
    período- porque la app ya confía en que el usuario eligió el Contrato
    correcto vía el `<select>` del formulario. Aplicamos el mismo criterio
    acá: dejamos de usar el texto libre de la columna 'Proyecto' como FILTRO
    de rechazo. Ese texto se sigue guardando en `referencia`/
    `datos_origen.proyecto` como trazabilidad del origen del dato.
    """
    columnas = _columnas(hoja, {'tipo', 'proyecto', 'rubro', 'clasificacion', 'valor', 'mes', 'ano'})
    lineas = []
    for numero, fila in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
        if not any(valor is not None and _texto(valor) for valor in fila):
            continue
        fila_anio, fila_mes = resolver_periodo_flexible(
            fila, columnas, hoja=hoja.title, fila_numero=numero,
        )
        if (fila_anio, fila_mes) != (anio, mes):
            continue
        origen = _texto(_valor(fila, columnas, 'proyecto'))
        concepto = _texto(_valor(fila, columnas, 'rubro'))
        grupo = _texto(_valor(fila, columnas, 'clasificacion'))
        if not concepto:
            raise ValueError(f"{hoja.title}, fila {numero}, columna 'Rubro': es obligatorio.")
        homologacion = _buscar_homologacion(catalogo, 'PRESUPUESTO', grupo, concepto, concepto)
        tipo_operacional_fuente = _texto(_valor(fila, columnas, 'tipo'))
        lineas.append({
            'tipo': LineaCargaFinanciera.Tipo.PRESUPUESTO,
            'grupo': grupo,
            'concepto': concepto,
            'rubro': concepto,
            'valor': _decimal(_valor(fila, columnas, 'valor'), hoja=hoja.title, fila=numero, columna='Valor'),
            'referencia': origen,
            'fila_origen': numero,
            'homologacion': homologacion,
            'tipo_operacional': tipo_operacional_fuente or LineaCargaFinanciera.TipoOperacional.SIN_CLASIFICAR,
            'periodo': fila_anio * 100 + fila_mes,
            'cdec_equiv': _texto(_valor(fila, columnas, 'cdec equiv')),
            'centro_costo': _texto(_valor(fila, columnas, 'c costo')),
            'datos_origen': {
                'clasificacion': grupo,
                'proyecto': origen,
                'tipo_operacional': {
                    'valor_fuente': tipo_operacional_fuente or None,
                    'columna_fuente': 'Tipo',
                    'hoja_fuente': hoja.title,
                    'fila_fuente': numero,
                    'regla': 'columna_tipo_directa',
                },
            },
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
    inicio = time.monotonic()
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
        presupuestos = _lineas_presupuesto(hojas['BD Ppto'], int(anio), int(mes), catalogo)
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
        'lineas_no_mapeadas': sum(1 for linea in [*reales, *presupuestos] if not linea['homologacion']),
        'codigos_no_mapeados': sorted({linea['concepto'] for linea in [*reales, *presupuestos] if not linea['homologacion']}),
        'duracion_validacion_segundos': round(time.monotonic() - inicio, 3),
        'legacy_sin_tipo': any(
            linea['tipo_operacional'] == LineaCargaFinanciera.TipoOperacional.SIN_CLASIFICAR
            for linea in reales
        ),
    }
    with transaction.atomic():
        anteriores = CargaFinanciera.objects.select_for_update().filter(
            proyecto=proyecto, anio=anio, mes=mes,
        )
        version = max((carga.version for carga in anteriores), default=0) + 1
        # La nueva carga pasa a ser la vigente, pero las versiones anteriores
        # y sus líneas permanecen disponibles para auditoría.
        anteriores.filter(vigente=True).update(vigente=False)
        carga = CargaFinanciera.objects.create(
            proyecto=proyecto, anio=anio, mes=mes, usuario=usuario,
            estado=CargaFinanciera.Estado.PROCESADA,
            nombre_archivo=_texto(getattr(archivo, 'name', '')),
            resumen={**resumen, 'version': version}, version=version, vigente=True,
        )
        LineaCargaFinanciera.objects.bulk_create([
            LineaCargaFinanciera(carga=carga, **linea) for linea in [*reales, *presupuestos]
        ], batch_size=1000)
    return ResultadoCargaFinanciera(True, carga=carga, resumen=resumen)


def previsualizar_tabla_maestra(archivo: BinaryIO) -> dict:
    """Lee el XLSX de catálogo sin tocar la BD; cada error conserva hoja/fila.

    Gap 2 (validador-cierre round-1, Instelec#247): el issue (comentario del
    cliente, 2026-09-12) documentó estas columnas exactas:
      INGRESOS (4, SIN Tipo): Concepto Projects | Código | Cuenta Contable | Descripción
      GASTOS   (5, CON Tipo): Concepto Projects | Código | Cuenta Contable | Tipo | Descripción
    El código anterior exigía SIEMPRE {grupo, concepto, codigo contable, tipo}
    en AMBAS hojas -pero 'Grupo' no existe en ninguna hoja real y 'Tipo' no
    existe en INGRESOS-, por lo que el 100% de las filas de INGRESOS del
    archivo real fallaban. Decisiones de mapeo (ver HomologacionProjectsContable
    en models_finv2_carga.py):
      - 'Concepto Projects' -> campo `concepto` (obligatorio en el modelo;
        es lo que ya se muestra en el listado/preview y se busca por
        `buscar=`). Sinónimo agregado a SINONIMOS_HEADERS.
      - 'Código'/'Cuenta Contable' -> campo `codigo_contable` (obligatorio
        en el modelo). Sinónimos agregados a SINONIMOS_HEADERS.
      - 'Descripción' es informativa; no tiene campo propio en el modelo
        -no se persiste, sólo se tolera como columna presente-.
      - 'Tipo' (Fijo/Variable) sigue OBLIGATORIO en GASTOS -ya validado-,
        pero es OPCIONAL en INGRESOS: si la columna no existe o la celda
        viene vacía, no se exige y queda como cadena vacía (no se inventa
        un default Fijo/Variable arbitrario).
      - 'Grupo' no viene en ninguna hoja real del cliente -se deriva del
        NOMBRE DE LA HOJA (INGRESOS/GASTOS) en vez de exigirse como columna,
        porque el modelo lo declara `blank=True` (no as no-nulo) pero el
        listado lo usa para agrupar visualmente.
    El rango 5000-6999 para el código contable YA era correcto (ambas hojas
    mezclan 5xxx/6xxx en el archivo real) y no se modifica.
    """
    try:
        libro = load_workbook(archivo, read_only=True, data_only=True)
    except (OSError, BadZipFile) as exc:
        return {'filas': [], 'errores': [str(exc)]}
    hojas = {nombre: _hoja(libro, nombre) for nombre in HOJAS_TABLA_MAESTRA}
    faltantes = [nombre for nombre, hoja in hojas.items() if hoja is None]
    if faltantes:
        return {'filas': [], 'errores': [f"Faltan hojas requeridas: {', '.join(faltantes)}."]}
    filas, errores, codigos = [], [], set()
    requeridas = {'concepto', 'codigo contable'}
    for nombre, hoja in hojas.items():
        try:
            columnas = _columnas(hoja, requeridas)
        except ValueError as exc:
            errores.append(str(exc))
            continue
        tipo_obligatorio = _normalizar(nombre) == _normalizar('GASTOS')
        grupo_derivado = nombre.strip().upper()
        for numero, fila in enumerate(hoja.iter_rows(min_row=2, values_only=True), start=2):
            if not any(_texto(v) for v in fila):
                continue
            dato = {
                'tipo': _texto(_valor(fila, columnas, 'tipo')),
                'grupo': grupo_derivado,
                'concepto': _texto(_valor(fila, columnas, 'concepto')),
                'rubro': _texto(_valor(fila, columnas, 'rubro')),
                'codigo_contable': _texto(_valor(fila, columnas, 'codigo contable')),
                'centro_costo': _texto(_valor(fila, columnas, 'centro de costo')),
                'hoja': nombre, 'fila': numero,
            }
            errores_fila = []
            for campo in ('concepto', 'codigo_contable'):
                if not dato[campo]:
                    errores_fila.append(f'{nombre}, fila {numero}, columna {campo}: es obligatorio.')
            if tipo_obligatorio and not dato['tipo']:
                errores_fila.append(f'{nombre}, fila {numero}, columna Tipo: es obligatorio.')
            if dato['tipo'] and dato['tipo'].lower() not in {'fijo', 'variable'}:
                errores_fila.append(f'{nombre}, fila {numero}, columna Tipo: debe ser Fijo o Variable.')
            codigo = dato['codigo_contable']
            if not (codigo.isdigit() and 5000 <= int(codigo) <= 6999):
                errores_fila.append(f'{nombre}, fila {numero}, columna Código contable: debe estar entre 5XXX y 6XXX.')
            if codigo in codigos:
                errores_fila.append(f'{nombre}, fila {numero}, columna Código contable: está duplicado.')
            else:
                codigos.add(codigo)
            if errores_fila:
                errores.extend(errores_fila)
            else:
                filas.append(dato)
    return {'filas': filas, 'errores': errores}


def confirmar_tabla_maestra(filas: list[dict], *, usuario, origen='IMPORTACION'):
    """Reemplaza el catálogo vigente de manera atómica y preserva snapshots."""
    with transaction.atomic():
        anterior = list(HomologacionProjectsContable.objects.filter(activo=True).values(
            'tipo', 'grupo', 'concepto', 'rubro', 'codigo_contable', 'centro_costo'
        ))
        numero = (VersionHomologacionProjectsContable.objects.order_by('-numero').values_list('numero', flat=True).first() or 0) + 1
        nueva_llaves = {(f['tipo'], f['grupo'], f['concepto'], f['rubro'], f['codigo_contable']) for f in filas}
        anterior_llaves = {(f['tipo'], f['grupo'], f['concepto'], f['rubro'], f['codigo_contable']) for f in anterior}
        version = VersionHomologacionProjectsContable.objects.create(
            numero=numero, autor=usuario, origen=origen,
            diff={'agregadas': len(nueva_llaves - anterior_llaves), 'retiradas': len(anterior_llaves - nueva_llaves)},
        )
        # Sólo se desactiva el catálogo vigente. Registros usados por líneas históricas
        # siguen existiendo y sus FK PROTECT no se ven afectados.
        HomologacionProjectsContable.objects.filter(activo=True).update(activo=False)
        HomologacionProjectsContable.objects.bulk_create([
            HomologacionProjectsContable(
                tipo=f['tipo'], grupo=f['grupo'], concepto=f['concepto'], rubro=f['rubro'],
                codigo_contable=f['codigo_contable'], centro_costo=f['centro_costo'],
                activo=True, version=version,
            ) for f in filas
        ])
    return version
