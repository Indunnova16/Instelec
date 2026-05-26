"""
B2.1 — Importer de la tabla del issue #102 que mapea Línea → conteos por Semestre.

La tabla en el body del issue tiene la forma (markdown-like, dentro de un bloque ```):

    LÍNEA          | S1 Total | S2 Total | Todo Año | Total
    LN 5114        |   104    |   104    |    0     |  104
    LN 733         |    18    |     8    |    0     |   18
    ...

Notas
- Filas como "LN 5156/5157" usan el código Transelca (codigo_transelca o codigo).
- "TOTALES" se ignora.
- "-" se trata como 0.
- Para cada conteo `n` mayor a cero, se asignan los primeros `n` vanos de la
  línea (orden por numero) al semestre correspondiente. Si la línea tiene
  MENOS vanos que el conteo, se asignan todos y se reporta warning.
- Si la línea no se encuentra (codigo ni codigo_transelca), se reporta y
  continúa (no error fatal).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from django.db import transaction

logger = logging.getLogger(__name__)


# Regex para detectar filas de la tabla del issue. Tolera espacios variables
# y permite "-" como valor.
_ROW_RE = re.compile(
    r'^\s*(?P<linea>LN\s*[\w/]+?)\s*\|'
    r'\s*(?P<s1>[\d\-]+)\s*\|'
    r'\s*(?P<s2>[\d\-]+)\s*\|'
    r'\s*(?P<ta>[\d\-]+)\s*\|'
    r'\s*(?P<total>[\d\-,]+)\s*$',
    re.MULTILINE,
)


@dataclass
class FilaTabla:
    """Una fila parseada de la tabla del issue #102."""
    codigo_linea: str
    s1: int
    s2: int
    ta: int
    total: int


@dataclass
class ResultadoImportacion:
    filas_parseadas: int = 0
    lineas_no_encontradas: list = field(default_factory=list)
    vano_semestres_creados: int = 0
    vano_semestres_existentes: int = 0
    vanos_faltantes_por_linea: dict = field(default_factory=dict)  # codigo → (faltan, semestre)
    errores: list = field(default_factory=list)

    def __str__(self):
        parts = [
            f"filas={self.filas_parseadas}",
            f"creados={self.vano_semestres_creados}",
            f"existentes={self.vano_semestres_existentes}",
            f"no_encontradas={len(self.lineas_no_encontradas)}",
        ]
        if self.vanos_faltantes_por_linea:
            parts.append(f"vanos_insuficientes={len(self.vanos_faltantes_por_linea)}")
        if self.errores:
            parts.append(f"errores={len(self.errores)}")
        return ", ".join(parts)


def _to_int(val: str) -> int:
    val = val.strip().replace(',', '')
    if val in ('-', ''):
        return 0
    try:
        return int(val)
    except ValueError:
        return 0


def parse_tabla(texto: str) -> list[FilaTabla]:
    """Parsea el bloque de tabla del issue #102."""
    filas = []
    for m in _ROW_RE.finditer(texto):
        codigo = m.group('linea').strip()
        # Saltar fila TOTALES (no debería matchear pero defensivo)
        if 'TOTAL' in codigo.upper():
            continue
        filas.append(FilaTabla(
            codigo_linea=codigo,
            s1=_to_int(m.group('s1')),
            s2=_to_int(m.group('s2')),
            ta=_to_int(m.group('ta')),
            total=_to_int(m.group('total')),
        ))
    return filas


def _resolver_linea(codigo: str):
    """
    Resuelve una línea desde su código o codigo_transelca.
    Acepta variantes: "LN 805" → "L-805", "L805", o codigo_transelca "805".
    """
    from .models import Linea

    # Normalizar codigo entrante
    raw = codigo.strip()
    sin_prefix = re.sub(r'^LN\s*', '', raw, flags=re.IGNORECASE).strip()

    # Estrategia 1: match exacto contra codigo_transelca
    qs = Linea.objects.filter(codigo_transelca=sin_prefix)
    if qs.exists():
        return qs.first()

    # Estrategia 2: codigo normalizado L-NNN o LNNN
    candidatos = [
        f"L-{sin_prefix}",
        f"L{sin_prefix}",
        sin_prefix,
        raw,
    ]
    for c in candidatos:
        qs = Linea.objects.filter(codigo__iexact=c)
        if qs.exists():
            return qs.first()

    # Estrategia 3: si tiene "/", probar primera parte ("801/802" → "801")
    if '/' in sin_prefix:
        primera = sin_prefix.split('/')[0].strip()
        qs = Linea.objects.filter(codigo_transelca__startswith=primera)
        if qs.exists():
            return qs.first()
        qs = Linea.objects.filter(codigo__icontains=primera)
        if qs.exists():
            return qs.first()

    return None


def _asignar_semestre(linea, semestre: str, cantidad: int, resultado: ResultadoImportacion):
    """
    Crea/actualiza VanoSemestre para los primeros `cantidad` vanos de `linea`
    en `semestre`. Si la línea tiene menos vanos, asigna lo que haya.
    """
    if cantidad <= 0:
        return

    from .models import Vano
    from .models_b21 import VanoSemestre

    vanos = list(Vano.objects.filter(linea=linea).order_by('numero')[:cantidad])
    if len(vanos) < cantidad:
        resultado.vanos_faltantes_por_linea.setdefault(linea.codigo, []).append({
            'semestre': semestre,
            'pedidos': cantidad,
            'disponibles': len(vanos),
        })

    for v in vanos:
        _, created = VanoSemestre.objects.get_or_create(
            vano=v,
            semestre=semestre,
            defaults={'estado': VanoSemestre.Estado.PENDIENTE},
        )
        if created:
            resultado.vano_semestres_creados += 1
        else:
            resultado.vano_semestres_existentes += 1


@transaction.atomic
def importar_tabla(texto: str, dry_run: bool = False) -> ResultadoImportacion:
    """
    Importa la tabla del issue #102 y crea VanoSemestre rows.

    Args:
        texto: contenido literal del bloque tabla del issue.
        dry_run: si True, hace rollback al final. Útil para validar.

    Returns: ResultadoImportacion
    """
    resultado = ResultadoImportacion()
    filas = parse_tabla(texto)
    resultado.filas_parseadas = len(filas)

    sid = transaction.savepoint()
    try:
        for fila in filas:
            linea = _resolver_linea(fila.codigo_linea)
            if not linea:
                resultado.lineas_no_encontradas.append(fila.codigo_linea)
                continue
            _asignar_semestre(linea, 'S1', fila.s1, resultado)
            _asignar_semestre(linea, 'S2', fila.s2, resultado)
            _asignar_semestre(linea, 'TA', fila.ta, resultado)
    except Exception as exc:
        resultado.errores.append(str(exc))
        transaction.savepoint_rollback(sid)
        raise

    if dry_run:
        transaction.savepoint_rollback(sid)
    else:
        transaction.savepoint_commit(sid)

    return resultado


# Tabla embebida del issue #102 (snapshot mayo 2026). Persistida acá para que
# el management command funcione offline. Si Sofi actualiza el issue, el
# command acepta `--from-issue` para refrescar via gh.
TABLA_ISSUE_102 = """
LÍNEA          | S1 Total | S2 Total | Todo Año | Total
LN 5114        |   104    |   104    |    0     |  104
LN 733         |    18    |     8    |    0     |   18
LN 734         |    35    |    29    |    0     |   35
LN 764/765     |    33    |    33    |    0     |   33
LN 801/802     |    87    |    49    |    0     |   87
LN 803/804     |     9    |     2    |    0     |    9
LN 805         |   246    |   129    |    0     |  246
LN 806/816     |   200    |    96    |    0     |   200
LN 839/840     |    41    |    21    |   13     |   41
LN 807/808     |   108    |    71    |   28     |  108
LN 809         |   124    |    30    |    0     |  124
LN 810         |   204    |   157    |    0     |  204
LN 811/812     |   178    |   120    |    0     |  178
LN 814/815     |   175    |   121    |    0     |  175
LN 817/818     |   175    |    43    |    0     |  175
LN 819         |   140    |     4    |    0     |  140
LN 842         |   100    |     7    |    0     |  100
LN 821/822     |   123    |    56    |    0     |  123
LN 824/825     |    46    |     9    |    0     |   46
LN 827/828     |   123    |    22    |    0     |  123
LN 829/830     |     7    |     6    |    0     |    7
LN 5156/5157   |   264    |     -    |    -     |  264
LN 792         |    21    |    21    |    -     |   21
"""
