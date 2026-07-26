"""Helpers de semana ISO compartidos entre vistas del módulo Cuadrillas.

Issue Indunnova16/Instelec#178 (F1): ``_prefijo`` vivía como función privada
de ``views_semanal.py``. Se extrae acá (solo mover, SIN lógica nueva) para
que ``views.py`` (``MapaCuadrillasPartialView``, filtro de semana del Mapa)
pueda reusar el MISMO criterio ``codigo`` ``WW-YYYY-`` que ya usa todo el
resto del módulo (``_bloques_qs``, ``CuadrillaListView._parse_semana``) sin
tener que importar una función privada de otro módulo de vistas — mismo
espíritu de extracción que ``services.py`` (issue #188, A5).
"""


def _prefijo(anio, semana):
    """Prefijo de código que identifica una semana: ``WW-YYYY-``."""
    return f"{int(semana):02d}-{int(anio)}-"
