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


# ===========================================================================
# DASHBOARD OBRA CIVIL — 3 gráficas de seguimiento gerencial (#141)
# ===========================================================================
#
# Estos agregadores alimentan las 3 gráficas del Dashboard de Obra Civil:
#   G2  avance_por_etapa_oc        -> barras % torres completas por etapa
#   G3  desviacion_materiales_vaciado -> calc vs real + semáforo
#   G1  curva_s_consolidada        -> serie consolidada de la Curva S
#
# Reciben un ``proyecto`` (ProyectoConstruccion) y leen del ORM, igual que
# el patrón ``IndicadoresAggregator`` de views_b3_dashboard_indicadores.py.
# Diseñados para ser robustos ante proyectos sin torres / torres sin vaciado:
# en esos casos devuelven estructuras vacías o materiales en 0, NUNCA lanzan.

#: Las 5 etapas de obra civil que el cliente quiere ver en G2, con su label
#: humano y el campo booleano real en ``PataObra`` (R3 del plan: "Acero" mapea
#: a ``acero_refuerzo_ok`` y "Compactación" a ``relleno_compactacion_ok``).
ETAPAS_OC = [
    ('EXCAVACION', 'Excavación', 'excavacion_ok'),
    ('SOLADO', 'Solado', 'solado_ok'),
    ('ACERO', 'Acero', 'acero_refuerzo_ok'),
    ('VACIADO', 'Vaciado', 'vaciado_ok'),
    ('COMPACTACION', 'Compactación', 'relleno_compactacion_ok'),
]

#: Materiales de vaciado para G3 (label + nombre de campo calc/real en
#: ``VaciadoDetalle``). Agua/arena/grava en m³; cemento en bultos.
MATERIALES_VACIADO = [
    ('agua', 'Agua', 'agua_calc_m3', 'agua_util_m3', 'm³'),
    ('cemento', 'Cemento', 'cemento_calc_bultos', 'cemento_util_bultos', 'bultos'),
    ('arena', 'Arena', 'arena_calc_m3', 'arena_util_m3', 'm³'),
    ('grava', 'Grava', 'grava_calc_m3', 'grava_util_m3', 'm³'),
]

#: Umbral de desviación por defecto para el semáforo rojo de G3 (en %).
UMBRAL_DESVIACION_DEFAULT = 10.0


def desviacion_material_pct(calc, real) -> Optional[float]:
    """Desviación % de un material: (real - calc) / calc * 100.

    Positivo = se usó MÁS de lo calculado (sobreconsumo). Retorna ``None`` si
    ``calc`` es 0/None (no hay base para comparar) — el caller decide cómo
    mostrarlo (ej. "sin dato").
    """
    c = _to_decimal(calc)
    r = _to_decimal(real)
    if c is None or c == 0 or r is None:
        return None
    return float(((r - c) / c) * Decimal('100'))


def semaforo_desviacion(desv_pct: Optional[float], umbral: float = UMBRAL_DESVIACION_DEFAULT) -> str:
    """Clasifica una desviación en semáforo: 'verde' | 'amarillo' | 'rojo' | 'sin_datos'.

    - ``None`` → 'sin_datos'.
    - |desv| > umbral            → 'rojo'  (alerta: revisar/justificar).
    - umbral/2 < |desv| <= umbral → 'amarillo' (atención).
    - |desv| <= umbral/2          → 'verde'  (dentro de tolerancia).
    """
    if desv_pct is None:
        return 'sin_datos'
    abs_desv = abs(desv_pct)
    if abs_desv > umbral:
        return 'rojo'
    if abs_desv > umbral / 2:
        return 'amarillo'
    return 'verde'


def avance_por_etapa_oc(proyecto) -> list:
    """G2 — % de torres COMPLETAS por etapa de obra civil.

    Una torre cuenta como "completa" en una etapa cuando TODAS sus patas
    tienen el booleano de esa etapa en True (misma semántica que el
    ``porcentaje_avance_civil_ponderado``: el bloque aporta solo cuando está
    completo en todas las patas).

    Retorna una lista (orden de ``ETAPAS_OC``) de dicts::

        {'etapa': 'EXCAVACION', 'label': 'Excavación',
         'completas': 66, 'totales': 68, 'pct': 97.06}

    Edge: proyecto sin torres → cada etapa con totales=0, completas=0, pct=0.0
    (lista poblada igual, para que el eje X de la gráfica tenga las 5 etapas).
    """
    torres = list(proyecto.torres.prefetch_related('pata_obra').all())
    resultado = []
    for codigo, label, campo in ETAPAS_OC:
        totales = 0
        completas = 0
        for torre in torres:
            patas = list(torre.pata_obra.all())
            if not patas:
                # Torre sin patas registradas: no cuenta como "completable" en
                # ninguna etapa (no hay datos), pero sí suma al universo de torres.
                totales += 1
                continue
            totales += 1
            if all(getattr(p, campo, False) for p in patas):
                completas += 1
        pct = round((completas / totales) * 100, 2) if totales else 0.0
        resultado.append({
            'etapa': codigo,
            'label': label,
            'completas': completas,
            'totales': totales,
            'pct': pct,
        })
    return resultado


def desviacion_materiales_vaciado(proyecto, umbral: float = UMBRAL_DESVIACION_DEFAULT) -> list:
    """G3 — desviación calc vs real de los 4 materiales de vaciado.

    Suma sobre TODAS las ``VaciadoDetalle`` del proyecto (patas con vaciado
    registrado) el calculado y el utilizado de cada material, y calcula la
    desviación % agregada + el semáforo según ``umbral``.

    Retorna lista (orden de ``MATERIALES_VACIADO``) de dicts::

        {'material': 'cemento', 'label': 'Cemento', 'unidad': 'bultos',
         'calc': 41.0, 'real': 42.0, 'desv_pct': 2.44, 'semaforo': 'verde'}

    Edge: proyecto sin vaciado (ninguna pata con VaciadoDetalle) → cada
    material con calc=real=0, desv_pct=None, semaforo='sin_datos' (la gráfica
    muestra "sin datos de vaciado", no rompe — R4 del plan).
    """
    # Traer todos los VaciadoDetalle del proyecto en una query
    # (pata -> torre -> proyecto).
    try:
        from .models import VaciadoDetalle
        vaciados = list(
            VaciadoDetalle.objects.filter(pata__torre__proyecto=proyecto)
        )
    except Exception:
        vaciados = []

    resultado = []
    for material, label, campo_calc, campo_real, unidad in MATERIALES_VACIADO:
        sum_calc = 0.0
        sum_real = 0.0
        for v in vaciados:
            sum_calc += float(getattr(v, campo_calc, None) or 0.0)
            sum_real += float(getattr(v, campo_real, None) or 0.0)
        desv = desviacion_material_pct(sum_calc, sum_real)
        resultado.append({
            'material': material,
            'label': label,
            'unidad': unidad,
            'calc': round(sum_calc, 2),
            'real': round(sum_real, 2),
            'desv_pct': round(desv, 2) if desv is not None else None,
            'semaforo': semaforo_desviacion(desv, umbral),
        })
    return resultado


def curva_s_consolidada(proyecto) -> dict:
    """G1 — serie CONSOLIDADA de la Curva S (todo el proyecto).

    El cliente pide, además de las curvas por fase (OOCC/Montaje/Tendido), una
    curva consolidada con todo el proyecto. Une las semanas de TODAS las fases
    de ``DashboardAvanceSemanal``: para cada semana presente en cualquier fase,
    suma las torres acumuladas de las fases que ya tienen registro ≤ esa semana
    y recalcula el % contra ``total_torres * n_fases_con_datos``.

    Retorna ``{'labels': [...], 'planeado': [...], 'ejecutado': [...]}`` con el
    % acumulado consolidado por semana.

    Edge: proyecto sin ninguna semana capturada → arreglos vacíos.
    """
    try:
        from .models import DashboardAvanceSemanal
    except Exception:
        return {'labels': [], 'planeado': [], 'ejecutado': []}

    semanas = list(
        DashboardAvanceSemanal.objects.filter(proyecto=proyecto).order_by('semana')
    )
    if not semanas:
        return {'labels': [], 'planeado': [], 'ejecutado': []}

    # Fases que tienen al menos un registro (define el denominador).
    fases_con_datos = sorted({s.fase for s in semanas})
    n_fases = len(fases_con_datos) or 1
    total_torres = proyecto.torres.count() or 0

    # Eje X = todas las fechas-semana distintas, en orden.
    labels = sorted({s.semana for s in semanas})

    # Para cada fase guardamos su serie ordenada para hacer "último ≤ fecha".
    por_fase = {f: [] for f in fases_con_datos}
    for s in semanas:
        por_fase[s.fase].append(s)
    for f in por_fase:
        por_fase[f].sort(key=lambda x: x.semana)

    def _acum_a_fecha(serie, fecha, attr):
        """Último valor acumulado de ``attr`` en ``serie`` con semana ≤ fecha."""
        valor = 0
        for s in serie:
            if s.semana <= fecha:
                valor = int(getattr(s, attr))
            else:
                break
        return valor

    planeado, ejecutado = [], []
    # Denominador consolidado: total de torres por cada fase con datos.
    denom = (total_torres * n_fases) or 1
    for fecha in labels:
        prog_total = sum(
            _acum_a_fecha(por_fase[f], fecha, 'torres_programadas_acum')
            for f in fases_con_datos
        )
        cons_total = sum(
            _acum_a_fecha(por_fase[f], fecha, 'torres_construidas_acum')
            for f in fases_con_datos
        )
        planeado.append(round(prog_total * 100.0 / denom, 2))
        ejecutado.append(round(cons_total * 100.0 / denom, 2))

    return {
        'labels': [d.isoformat() for d in labels],
        'planeado': planeado,
        'ejecutado': ejecutado,
    }
