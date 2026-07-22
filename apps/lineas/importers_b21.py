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


class VanoParseError(Exception):
    """#102 — ``parse_vano_list`` no pudo interpretar el texto de vanos de
    una fila del Excel real del cliente (att_01.xlsx, columna "Torres /
    Vanos"). Fail-loud por diseño (F2 parser_spec): la función NUNCA debe
    devolver un set vacío en silencio ni continuar con datos parciales sin
    loggear — mejor romper ruidoso y que la migración capture el error por
    fila que cargar datos incompletos sin que nadie se entere."""


# #102 — Overrides manuales para filas irresolubles por regex puro (F2,
# investigación BD prod). Único caso real detectado: LN 807/808 S1, texto
# literal "Torre 5 (propiedad EEB) a la 42 y de la 42 a la 148" (~144 vanos
# si se tomara literal) pero el Total declarado en el Excel es 108. F2
# adoptó el rango 5-112 (108 vanos EXACTOS: 112-5+1=108) porque 112 coincide
# EXACTO con el conteo real de torres de LN807 en BD (fuerte evidencia de
# que "148" es un error de trascripción por "112"). Se aplica el mismo
# rango numérico a LN808 también (113 torres reales, 1 de más, tolerable).
CASOS_ESPECIALES: dict[tuple[str, str], set[int]] = {
    ('LN 807/808', 'S1'): set(range(5, 113)),  # 108 vanos exactos
}


def parse_vano_list(
    texto: str,
    etiqueta_excel: str = '',
    semestre: str = '',
):
    """
    #102 — Parsea texto libre en español (columna "Torres / Vanos" del
    Excel real del cliente, att_01.xlsx) a un ``set[int]`` de números de
    vano — o, para el único caso de sub-grupos etiquetados del dataset, a
    un ``dict[str, set[int]]`` (ver paso de sub-grupos abajo).

    Reemplaza la heurística vieja de "primeros N vanos" (``_asignar_semestre``
    original, issue #101/#102 bounce): ahora se consume la LISTA REAL de
    vanos que el cliente reportó por semestre, no solo un conteo.

    Fallback ordenado (parser_spec, F2 — el chequeo de sub-grupos etiquetados
    se hace ANTES que el de lista explícita aunque el spec los enumere 3→4:
    el único texto del dataset con sub-grupos también tiene comas DENTRO de
    cada sub-grupo, así que si el split-por-coma corriera primero
    fragmentaría los sub-grupos en vez de detectarlos):

      1. Quitar sufijo de unidad conocido ("postes", case-insensitive).
      2. RANGO SIMPLE: ``"1 al 104"``, ``"3 a 11"``, ``"1 a la 35"``,
         ``"141 a la 240"`` (incluye rangos con offset que no arrancan en 1).
      3. SUB-GRUPOS ETIQUETADOS: si el texto contiene ``";"`` Y ``"("`` (único
         caso real del dataset: fila S2 de "LN 821/822, LN 821/826, LN
         838/826, LN 822/826") → split por ``";"``, cada segmento matchea
         ``r'^\\(([\\w/]+)\\)\\s*(.+)$'`` → ``{sub_etiqueta: parse_vano_list(resto)}``
         recursivo. Devuelve ``dict[str, set[int]]`` — el caller (la
         migración) decide a qué Línea(s) mapear cada sub-etiqueta según
         ``MAPEO_EXCEL_A_LINEAS``.
      4. LISTA EXPLÍCITA: normaliza ``" y "`` → ``", "``, split por coma,
         cada token se intenta ``int()``; tokens no-numéricos (ej. "S/E
         Sabana Portico", "Torre 5 (propiedad EEB)") se DESCARTAN de la
         lista de números pero se registran en un log de warning (no
         fatal — el resto de números válidos de la fila SÍ se cargan).
      5. CASOS_ESPECIALES: override manual hardcodeado para overrides de
         filas irresolubles por regex (ver arriba). Si ninguno de los pasos
         2-5 matchea, la función FALLA RUIDOSO con ``VanoParseError``.
    """
    original = texto
    if texto is None or not str(texto).strip():
        raise VanoParseError(
            f"texto vacío para línea={etiqueta_excel!r} semestre={semestre!r}"
        )
    t = str(texto).strip()

    # (1) Sufijo de unidad conocido.
    t = re.sub(r'\bpostes\b', '', t, flags=re.IGNORECASE).strip().rstrip('.').strip()

    # (2) Rango simple (incluye offsets que no arrancan en 1, ej. "141 a la 240").
    m = re.match(r'^(\d+)\s*al?\s*(?:la\s*)?(\d+)$', t, flags=re.IGNORECASE)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if start > end:
            start, end = end, start
        return set(range(start, end + 1))

    # (3) Sub-grupos etiquetados ";" + "(...)" — chequeado ANTES de la lista
    # explícita, ver docstring.
    if ';' in t and '(' in t:
        subgrupos: dict[str, set[int]] = {}
        for segmento in t.split(';'):
            segmento = segmento.strip()
            if not segmento:
                continue
            sm = re.match(r'^\(([\w/]+)\)\s*(.+)$', segmento)
            if not sm:
                raise VanoParseError(
                    f"sub-grupo no reconocido {segmento!r} en línea={etiqueta_excel!r} "
                    f"semestre={semestre!r}: texto={original!r}"
                )
            sub_etiqueta, resto = sm.group(1), sm.group(2)
            subgrupos[sub_etiqueta] = parse_vano_list(
                resto,
                etiqueta_excel=f"{etiqueta_excel} ({sub_etiqueta})",
                semestre=semestre,
            )
        return subgrupos

    # (4) Lista explícita: normalizar " y " -> ", ", descartar no-numéricos.
    normalizado = re.sub(r'\s+y\s+', ', ', t, flags=re.IGNORECASE)
    numeros: set[int] = set()
    descartados: list[str] = []
    for tok in normalizado.split(','):
        tok = tok.strip()
        if not tok:
            continue
        try:
            numeros.add(int(tok))
        except ValueError:
            descartados.append(tok)
    if descartados:
        logger.warning(
            "parse_vano_list: tokens no numéricos descartados en línea=%r "
            "semestre=%r: %s (texto=%r)",
            etiqueta_excel, semestre, descartados, original,
        )
    if numeros:
        return numeros

    # (5) CASOS_ESPECIALES — override manual final antes de fallar.
    key = (etiqueta_excel, semestre)
    if key in CASOS_ESPECIALES:
        return CASOS_ESPECIALES[key]

    raise VanoParseError(
        f"no se pudo parsear vanos para línea={etiqueta_excel!r} "
        f"semestre={semestre!r}: texto={original!r}"
    )


# #102 — Mapeo etiqueta-del-Excel-real -> códigos de Línea reales en BD.
# Hardcodeado (``codigo_transelca`` está VACÍO en las 40 filas de BD, no
# sirve como mecanismo de resolución — ver F2 causa_raiz). Confianza y
# exclusiones documentadas por fila (mismo detalle en la migración 0017 y
# en el JSON de salida de F2/F3). Etiquetas con lista vacía = Línea NO
# EXISTE en BD (bloqueada, ver ``bloqueos`` en el output de F3) — NO se
# crea ningún stub (violaría "nunca inventar evidencia").
MAPEO_EXCEL_A_LINEAS: dict[str, list[str]] = {
    'LN 5114': ['LN5114'],                            # alta
    'LN 733': ['LN733'],                              # alta
    'LN 734': ['LN734'],                              # alta
    'LN 764/765': ['LN764', 'LN765'],                 # alta — doble circuito 33/33 EXACTO
    'LN 801/802': ['LN801', 'LN802'],                 # alta — doble circuito 91/91
    'LN 803/804': ['LN803', 'LN804'],                 # alta — doble circuito 14/16
    'LN 805': ['LN805'],                              # alta
    'LN 806/816': ['LN806', 'LN816'],                 # alta — doble circuito 201/202
    'LN 839/840': ['LN839', 'LN840'],                 # alta — doble circuito 46/47
    'LN 807/808': ['LN807', 'LN808'],                 # media — S1 requiere CASOS_ESPECIALES
    'LN 809': ['LN809'],                              # alta
    'LN 810': ['LN810'],                              # alta
    'LN 811/812 y LN 812/813': ['LN811', 'LN812'],    # media/alta — LN813 EXCLUIDA (69 torres vs 178 pedidos, desproporción severa)
    'LN 814/815 y LN 834/815': ['LN815', 'LN834'],    # alta/media — LN814 EXCLUIDA (23 torres vs 171 pedidos)
    'LN 817/818': ['LN817', 'LN818'],                 # alta — doble circuito 177/177 EXACTO
    'LN 819': ['LN819'],                              # alta
    'LN 842': [],                                     # BLOQUEADA — Línea no existe en BD
    'LN 821/822, LN 821/826, LN 838/826, LN 822/826': ['LN826', 'LN838'],  # ver reglas S1/S2 especiales en migración 0017 — LN821/LN822 EXCLUIDAS (torres≈0)
    'LN 824/825': ['LN824', 'LN825'],                 # alta — doble circuito 50/50 EXACTO
    'LN 827/828': ['LN827', 'LN828'],                 # alta — doble circuito 125/125 EXACTO
    'LN 829/830': ['LN829', 'LN830'],                 # alta — doble circuito 13/11
    'LN 5156/5157': ['LN5156', 'LN5157'],             # alta — doble circuito de POSTES 264/264 EXACTO
    'LN 792': [],                                     # BLOQUEADA — Línea no existe en BD
}


def _resolver_lineas(etiqueta_excel: str) -> list:
    """
    #102 — Resuelve 1 etiqueta del Excel real a la lista de ``Linea`` reales
    que representa (0, 1 o varias — patrón "doble circuito": misma
    estructura física compartida por 2-4 líneas). Usa ``MAPEO_EXCEL_A_LINEAS``
    (hardcodeado, ver arriba) en vez del split-by-"/" heurístico de
    ``_resolver_linea`` (que estructuralmente sólo podía devolver 1 sola
    Línea — incapaz de distribuir datos a las líneas adicionales de un
    grupo "doble circuito").

    NO lanza excepción si la etiqueta está bloqueada o no mapeada — el
    caller decide cómo reportarlo (devuelve lista vacía).
    """
    from .models import Linea

    lineas = []
    for codigo in MAPEO_EXCEL_A_LINEAS.get(etiqueta_excel, []):
        try:
            lineas.append(Linea.objects.get(codigo=codigo))
        except Linea.DoesNotExist:
            logger.warning(
                "_resolver_lineas: código %r (etiqueta=%r) no existe en BD",
                codigo, etiqueta_excel,
            )
    return lineas


# Tabla embebida del issue #102 (snapshot mayo 2026, formato conteo-por-
# semestre). Persistida acá para que el management command
# ``cargar_semestres_vanos`` funcione offline con el formato ORIGINAL de la
# tabla del cuerpo del issue. Si Sofi actualiza el issue, el command acepta
# `--from-issue` para refrescar via gh.
#
# NOTA (F2, jul-2026): esta tabla es un snapshot APROXIMADO de mayo 2026 —
# solo tiene CONTEOS por semestre, no la lista real de qué vanos van en cada
# uno (esa granularidad solo la trajo el Excel real del cliente, att_01.xlsx,
# en julio). La carga masiva real de datos de #102 usa la migración
# ``0017_carga_vanos_semestre_completa`` (parser ``parse_vano_list`` +
# ``MAPEO_EXCEL_A_LINEAS`` arriba), NO esta tabla ni ``importar_tabla``.
# Se conserva sin cambios (con sus tests existentes) como herramienta manual
# de datafix aproximado para cuando no se tiene el Excel real a mano.
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
