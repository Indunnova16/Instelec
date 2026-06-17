"""
B2 (#122) — Funciones puras para los indicadores del Dashboard Financiero v2.

Reemplaza los KPIs secundarios del dashboard (Costos Variables/Fijos, % Utilidad)
por:

1. **6 indicadores tecnico-financieros** calculados sobre los ``resumen_planeado``
   / ``resumen_real`` que ya arma ``DashboardFinancieroView`` (dicts con
   ``ingreso``, ``total_variables``, ``total_fijos``, ``total_gastos``,
   ``resultado``, ``utilidad_pct``):

   - Meta de Facturacion General  ((Fact.Real / Meta) x 100)
   - Margen Operativo del Proyecto (meta 20 %)
   - Desviacion Presupuestal (meta +-5 %)
   - Ejecucion Presupuestal (meta >= 95 %)
   - Produccion Cuadrillas Costo Fijo (meta >= 95 %)
   - Rentabilidad Costo Fijo (meta 12 %)

2. **Seccion ANS** (9 filas + total ponderado) reutilizando el modelo ya
   existente ``apps.indicadores.models_b4_mantenimiento_detallado.IndicadorANSContractual``
   (5 componentes ponderados, ``puntaje_total_ans`` / ``estado_ans`` calculados
   en ``save()``) y el helper ``serie_componentes_ans`` de ``calculators_b4``.

Estas funciones son **puras** (no tocan ``request``/``self``): toman insumos y
devuelven dicts/list listos para el contexto. Manejan division por cero. El
mixin ``DashboardFinancieroMixinV2`` (views_finv2_dashboard.py) las orquesta.
"""
from decimal import Decimal, InvalidOperation

# Metas oficiales (issue #122). Se reusan las constantes del modelo B4 cuando
# existen para no duplicar la fuente de verdad.
try:
    from apps.indicadores.models_b4_mantenimiento_detallado import (
        META_MARGEN_OPERATIVO,
        META_RENTABILIDAD_COSTO_FIJO,
    )
except Exception:  # pragma: no cover - fallback si B4 aun no migrado
    META_MARGEN_OPERATIVO = Decimal("20")
    META_RENTABILIDAD_COSTO_FIJO = Decimal("12")

# Metas propias de B2 (no existen como constante en B4).
META_FACTURACION = Decimal("100")          # >= 100 % (la fila "Meta facturacion general")
META_DESVIACION_PRESUPUESTAL = Decimal("5")  # +-5 % aceptable
META_EJECUCION_PRESUPUESTAL = Decimal("95")  # >= 95 %
META_PRODUCCION_CUADRILLAS = Decimal("95")   # >= 95 %

# Umbrales de coloreo (issue #122: verde cumple, amarillo 80-99 %, rojo < 80 %).
UMBRAL_AMARILLO = Decimal("80")

ESTADO_VERDE = "verde"
ESTADO_AMARILLO = "amarillo"
ESTADO_ROJO = "rojo"


def _to_decimal(valor) -> Decimal:
    """Convierte cualquier numerico (int/float/Decimal/str) a Decimal de forma segura."""
    if isinstance(valor, Decimal):
        return valor
    if valor is None:
        return Decimal("0")
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _safe_div(num, den) -> Decimal:
    """Division protegida: den 0/None -> Decimal('0')."""
    num = _to_decimal(num)
    den = _to_decimal(den)
    if den == 0:
        return Decimal("0")
    return num / den


def _q2(valor: Decimal) -> Decimal:
    """Redondea a 2 decimales."""
    return _to_decimal(valor).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Estado / coloreo
# ---------------------------------------------------------------------------
def _estado_por_cumplimiento(pct_cumplimiento: Decimal) -> str:
    """
    Mapea un % de cumplimiento (valor/meta x 100) al estado de color del issue:
    - >= 100 %      -> verde (cumple o supera)
    - 80 % .. 99 %  -> amarillo (cumple parcial)
    - < 80 %        -> rojo (no cumple)
    """
    pct = _to_decimal(pct_cumplimiento)
    if pct >= Decimal("100"):
        return ESTADO_VERDE
    if pct >= UMBRAL_AMARILLO:
        return ESTADO_AMARILLO
    return ESTADO_ROJO


def _estado_desviacion(desviacion_pct: Decimal, tolerancia: Decimal) -> str:
    """
    Para Desviacion Presupuestal la meta es una BANDA (+-tolerancia), no un piso.
    - |desv| <= tolerancia        -> verde
    - tolerancia < |desv| <= 2x    -> amarillo
    - |desv| > 2x tolerancia       -> rojo
    """
    desv = abs(_to_decimal(desviacion_pct))
    tol = _to_decimal(tolerancia)
    if tol == 0:
        return ESTADO_VERDE if desv == 0 else ESTADO_ROJO
    if desv <= tol:
        return ESTADO_VERDE
    if desv <= tol * 2:
        return ESTADO_AMARILLO
    return ESTADO_ROJO


def _pct_progreso(valor: Decimal, meta: Decimal) -> int:
    """
    % de avance de la barra de progreso (0..100, clamp). Para metas tipo piso.
    Si meta es 0 devuelve 0.
    """
    if _to_decimal(meta) == 0:
        return 0
    raw = _safe_div(valor, meta) * Decimal("100")
    raw = max(Decimal("0"), min(raw, Decimal("100")))
    return int(raw)


# ---------------------------------------------------------------------------
# 6 indicadores tecnico-financieros
# ---------------------------------------------------------------------------
def calcular_indicadores_tecnico_financieros(resumen_planeado, resumen_real, extras=None):
    """
    Construye la lista de los 6 indicadores tecnico-financieros (#122).

    Args:
        resumen_planeado: dict con keys ingreso, total_variables, total_fijos,
            total_gastos (presupuesto PLANEADO del periodo).
        resumen_real: idem para REAL (ejecutado).
        extras: dict opcional con insumos finos que el dashboard no calcula:
            - ``meta_facturacion`` (override de la meta de ingresos; default usa
              ``resumen_planeado['ingreso']``).
            - ``produccion_real`` / ``meta_produccion`` para Produccion Cuadrillas;
              si no vienen, se cae al proxy facturacion (mismo que indicador 1).

    Returns:
        list[dict] con keys: tipo, nombre, formula, meta, valor (str display),
        valor_num (Decimal), estado (verde/amarillo/rojo), progreso (0..100 int),
        unidad.
    """
    extras = extras or {}
    rp = resumen_planeado or {}
    rr = resumen_real or {}

    ingreso_real = _to_decimal(rr.get("ingreso"))
    ingreso_plan = _to_decimal(rp.get("ingreso"))
    meta_fact = _to_decimal(extras.get("meta_facturacion")) or ingreso_plan

    costos_directos_real = _to_decimal(rr.get("total_variables"))
    gastos_real = _to_decimal(rr.get("total_fijos"))
    total_gastos_real = _to_decimal(rr.get("total_gastos"))
    total_gastos_plan = _to_decimal(rp.get("total_gastos"))

    indicadores = []

    # --- 1. Meta de Facturacion General ------------------------------------
    meta_fact_pct = _safe_div(ingreso_real, meta_fact) * Decimal("100")
    indicadores.append({
        "tipo": "TECNICO",
        "nombre": "Meta de facturación general",
        "formula": "(Facturación Real / Meta de Facturación) × 100",
        "meta": "≥ 100%",
        "valor": f"{_q2(meta_fact_pct)}%",
        "valor_num": _q2(meta_fact_pct),
        "estado": _estado_por_cumplimiento(_safe_div(meta_fact_pct, META_FACTURACION) * Decimal("100")),
        "progreso": _pct_progreso(meta_fact_pct, META_FACTURACION),
        "unidad": "%",
    })

    # --- 2. Margen Operativo del Proyecto (meta 20 %) ----------------------
    margen = _calcular_margen_operativo(ingreso_real, costos_directos_real, gastos_real)
    indicadores.append({
        "tipo": "FINANCIERO",
        "nombre": "Margen Operativo del Proyecto",
        "formula": "((Ingresos Ejecutados − (Costos Directos + Gastos)) / Ingresos Ejecutados) × 100",
        "meta": f"{_q2(META_MARGEN_OPERATIVO)}%",
        "valor": f"{_q2(margen)}%",
        "valor_num": _q2(margen),
        # cumplimiento = margen / meta (margen puede ser negativo -> rojo)
        "estado": _estado_por_cumplimiento(_safe_div(margen, META_MARGEN_OPERATIVO) * Decimal("100")),
        "progreso": _pct_progreso(margen, META_MARGEN_OPERATIVO),
        "unidad": "%",
    })

    # --- 3. Desviacion Presupuestal (meta +-5 %) ---------------------------
    desviacion = _calcular_desviacion_presupuestal(total_gastos_real, total_gastos_plan)
    indicadores.append({
        "tipo": "FINANCIERO",
        "nombre": "Desviación Presupuestal",
        "formula": "((Costo Real − Costo Presupuestado) / Costo Presupuestado) × 100",
        "meta": f"±{_q2(META_DESVIACION_PRESUPUESTAL)}%",
        "valor": f"{'+' if _q2(desviacion) >= 0 else ''}{_q2(desviacion)}%",
        "valor_num": _q2(desviacion),
        "estado": _estado_desviacion(desviacion, META_DESVIACION_PRESUPUESTAL),
        # progreso: 100 cuando dentro de banda, decae con |desv|
        "progreso": _progreso_desviacion(desviacion, META_DESVIACION_PRESUPUESTAL),
        "unidad": "%",
    })

    # --- 4. Ejecucion Presupuestal (meta >= 95 %) --------------------------
    # % ejecutado = costo_real / total_gastos_real_estimado.  En el dashboard el
    # "total presupuesto" del periodo es total_gastos (plan vs real). Usamos
    # ejecucion = (gasto_real / gasto_plan) x 100 como % de presupuesto ejecutado
    # contra planeado — equivalente a (%ejec / %plan) x 100 cuando ambos
    # comparten denominador.
    ejecucion = _safe_div(total_gastos_real, total_gastos_plan) * Decimal("100")
    indicadores.append({
        "tipo": "TECNICO",
        "nombre": "Ejecución presupuestal",
        "formula": "(% Presupuesto Ejecutado / % Presupuesto Planeado) × 100",
        "meta": "≥ 95%",
        "valor": f"{_q2(ejecucion)}%",
        "valor_num": _q2(ejecucion),
        "estado": _estado_por_cumplimiento(_safe_div(ejecucion, META_EJECUCION_PRESUPUESTAL) * Decimal("100")),
        "progreso": _pct_progreso(ejecucion, META_EJECUCION_PRESUPUESTAL),
        "unidad": "%",
    })

    # --- 5. Produccion Cuadrillas Costo Fijo (meta >= 95 %) ----------------
    produccion_real = extras.get("produccion_real")
    meta_produccion = extras.get("meta_produccion")
    if produccion_real is not None and meta_produccion is not None:
        produccion = _safe_div(produccion_real, meta_produccion) * Decimal("100")
    else:
        # Proxy: misma logica que Meta Facturacion (issue: "similar al indicador 1").
        produccion = meta_fact_pct
    indicadores.append({
        "tipo": "TECNICO",
        "nombre": "Producción cuadrillas costo fijo",
        "formula": "(Facturación Real / Meta de Facturación) × 100",
        "meta": "≥ 95% (diario/período)",
        "valor": f"{_q2(produccion)}%",
        "valor_num": _q2(produccion),
        "estado": _estado_por_cumplimiento(_safe_div(produccion, META_PRODUCCION_CUADRILLAS) * Decimal("100")),
        "progreso": _pct_progreso(produccion, META_PRODUCCION_CUADRILLAS),
        "unidad": "%",
    })

    # --- 6. Rentabilidad Costo Fijo (meta 12 %) ----------------------------
    # Margen de Utilidad = Ingresos Ejecutados − Costos de Cuadrilla (fijos).
    # Costo de la Cuadrilla = costos directos + costos fijos atribuibles.
    margen_utilidad = ingreso_real - (costos_directos_real + gastos_real)
    costo_cuadrilla = costos_directos_real + gastos_real
    rentabilidad = _safe_div(margen_utilidad, costo_cuadrilla) * Decimal("100")
    indicadores.append({
        "tipo": "TECNICO",
        "nombre": "Rentabilidad costo fijo",
        "formula": "(Margen de Utilidad / Costo de la Cuadrilla) × 100",
        "meta": f"{_q2(META_RENTABILIDAD_COSTO_FIJO)}%",
        "valor": f"{_q2(rentabilidad)}%",
        "valor_num": _q2(rentabilidad),
        "estado": _estado_por_cumplimiento(_safe_div(rentabilidad, META_RENTABILIDAD_COSTO_FIJO) * Decimal("100")),
        "progreso": _pct_progreso(rentabilidad, META_RENTABILIDAD_COSTO_FIJO),
        "unidad": "%",
    })

    return indicadores


def _calcular_margen_operativo(ingreso_real, costos_directos, gastos) -> Decimal:
    """((Ingresos − (Costos Directos + Gastos)) / Ingresos) × 100. 0 si ingreso 0."""
    ingreso_real = _to_decimal(ingreso_real)
    if ingreso_real == 0:
        return Decimal("0")
    return ((ingreso_real - (_to_decimal(costos_directos) + _to_decimal(gastos))) / ingreso_real) * Decimal("100")


def _calcular_desviacion_presupuestal(costo_real, costo_presupuestado) -> Decimal:
    """((Costo Real − Costo Presupuestado) / Costo Presupuestado) × 100. 0 si presupuesto 0."""
    costo_presupuestado = _to_decimal(costo_presupuestado)
    if costo_presupuestado == 0:
        return Decimal("0")
    return ((_to_decimal(costo_real) - costo_presupuestado) / costo_presupuestado) * Decimal("100")


def _progreso_desviacion(desviacion_pct, tolerancia) -> int:
    """Barra de progreso para desviacion: 100 si dentro de banda, decae a 0 en 2x."""
    desv = abs(_to_decimal(desviacion_pct))
    tol = _to_decimal(tolerancia)
    if tol == 0:
        return 100 if desv == 0 else 0
    if desv <= tol:
        return 100
    if desv >= tol * 2:
        return 0
    # Interpolacion lineal entre tol (100) y 2*tol (0).
    frac = (desv - tol) / tol
    return int((Decimal("1") - frac) * Decimal("100"))


# ---------------------------------------------------------------------------
# Seccion ANS (9 filas + total ponderado)
# ---------------------------------------------------------------------------
def calcular_resumen_ans(linea=None, anio=None, mes=None):
    """
    Construye la tabla ANS de 9 filas + el total ponderado, reutilizando el
    modelo ``IndicadorANSContractual`` y su property ``componentes`` (5 base).

    El issue #122 lista 9 filas (5 componentes + 4 "Alt" repetidos). Mapeamos
    las 9 filas declaradas a los 5 componentes del modelo (los "Alt" toman el
    mismo valor del componente base correspondiente, como indica el screenshot
    de especificacion). El total ponderado proviene de ``puntaje_total_ans``,
    fuente unica de verdad del modelo (calculado en ``save()``).

    Returns:
        dict con:
        - ``filas``: list[dict] (9) con ans (#), descripcion, peso, meta, valor,
          estado (verde/amarillo/rojo).
        - ``total_ponderado``: str display del puntaje total.
        - ``total_num``: Decimal.
        - ``estado_general``: CUMPLE / PARCIAL / NO_CUMPLE (display).
        - ``estado_color``: verde/amarillo/rojo.
        - ``sin_datos``: bool (True si no hay registro ANS para el periodo).
    """
    registro = _obtener_ans(linea, anio, mes)

    if registro is None:
        return {
            "filas": _filas_ans_vacias(),
            "total_ponderado": "—",
            "total_num": Decimal("0"),
            "estado_general": "Sin datos",
            "estado_color": ESTADO_ROJO,
            "sin_datos": True,
        }

    # Mapa key->componente del modelo (programacion, ejecucion, info_contractual,
    # info_ambiental, disponibilidad).
    comp = {c["key"]: c for c in registro.componentes}

    # Definicion de las 9 filas del issue #122 (orden y pesos del screenshot).
    spec_filas = [
        ("programacion", "% de Cumplimiento de la programación del mantenimiento (30%)", "30%", "≥ 95%"),
        ("ejecucion", "% de Cumplimiento de la ejecución del mantenimiento", "—", "≥ 98%"),
        ("info_contractual", "% de Cumplimiento de la gestión de la información", "—", "100%"),
        ("info_ambiental", "% de Cumplimiento de la Información Ambiental (15%)", "15%", "100%"),
        ("disponibilidad", "% de Cumplimiento de la meta de disponibilidad de los equipos", "—", "≥ 99%"),
        ("programacion", "% de Cumplimiento de la programación del mantenimiento (30%)", "30%", "≥ 95%"),
        ("ejecucion", "% de Cumplimiento de la ejecución del mantenimiento", "—", "≥ 98%"),
        ("info_ambiental", "% de Cumplimiento de la Información Ambiental (15%)", "15%", "100%"),
        ("disponibilidad", "% de Cumplimiento de la meta de disponibilidad de los equipos", "—", "≥ 99%"),
    ]

    filas = []
    for idx, (key, descripcion, peso, meta) in enumerate(spec_filas, start=1):
        c = comp.get(key)
        if c is None:
            valor = Decimal("0")
            ok = False
            meta_num = Decimal("0")
        else:
            valor = _to_decimal(c["valor"])
            meta_num = _to_decimal(c["meta"])
            ok = bool(c["ok"])
        filas.append({
            "ans": idx,
            "descripcion": descripcion,
            "peso": peso,
            "meta": meta,
            "valor": f"{_q2(valor)}%",
            "valor_num": _q2(valor),
            "estado": _estado_ans_fila(valor, meta_num, ok),
        })

    total = _to_decimal(registro.puntaje_total_ans)
    return {
        "filas": filas,
        "total_ponderado": f"{_q2(total)}%",
        "total_num": _q2(total),
        "estado_general": registro.get_estado_ans_display(),
        "estado_color": _color_estado_ans(registro.estado_ans),
        "sin_datos": False,
    }


def _estado_ans_fila(valor: Decimal, meta: Decimal, ok: bool) -> str:
    """Color de una fila ANS: verde si ok; amarillo si >=80% de meta; rojo si menos."""
    if ok:
        return ESTADO_VERDE
    if meta and meta > 0:
        pct = _safe_div(valor, meta) * Decimal("100")
        if pct >= UMBRAL_AMARILLO:
            return ESTADO_AMARILLO
    return ESTADO_ROJO


def _color_estado_ans(estado_ans: str) -> str:
    """Mapea el estado_ans del modelo (CUMPLE/PARCIAL/NO_CUMPLE) al color."""
    return {
        "CUMPLE": ESTADO_VERDE,
        "PARCIAL": ESTADO_AMARILLO,
        "NO_CUMPLE": ESTADO_ROJO,
    }.get(estado_ans, ESTADO_ROJO)


def _filas_ans_vacias():
    """9 filas placeholder cuando no hay registro ANS del periodo."""
    descripciones = [
        ("% de Cumplimiento de la programación del mantenimiento (30%)", "30%", "≥ 95%"),
        ("% de Cumplimiento de la ejecución del mantenimiento", "—", "≥ 98%"),
        ("% de Cumplimiento de la gestión de la información", "—", "100%"),
        ("% de Cumplimiento de la Información Ambiental (15%)", "15%", "100%"),
        ("% de Cumplimiento de la meta de disponibilidad de los equipos", "—", "≥ 99%"),
        ("% de Cumplimiento de la programación del mantenimiento (30%)", "30%", "≥ 95%"),
        ("% de Cumplimiento de la ejecución del mantenimiento", "—", "≥ 98%"),
        ("% de Cumplimiento de la Información Ambiental (15%)", "15%", "100%"),
        ("% de Cumplimiento de la meta de disponibilidad de los equipos", "—", "≥ 99%"),
    ]
    return [
        {
            "ans": idx,
            "descripcion": desc,
            "peso": peso,
            "meta": meta,
            "valor": "—",
            "valor_num": Decimal("0"),
            "estado": ESTADO_ROJO,
        }
        for idx, (desc, peso, meta) in enumerate(descripciones, start=1)
    ]


def _obtener_ans(linea=None, anio=None, mes=None):
    """
    Trae el ``IndicadorANSContractual`` del periodo. Reutiliza
    ``serie_componentes_ans`` de calculators_b4 cuando esta disponible; si el
    modulo B4 no esta migrado todavia (entorno de scaffolding), devuelve None
    de forma defensiva en vez de romper el dashboard.
    """
    try:
        from apps.indicadores.calculators_b4 import serie_componentes_ans
    except Exception:
        return None
    try:
        return serie_componentes_ans(linea=linea, anio=anio, mes=mes)
    except Exception:
        return None


def contexto_indicadores_finv2(anio, mes=0, contrato=None, linea=None):
    """#122: contexto reutilizable de los 6 KPIs técnico-financieros + ANS.

    Permite mostrar las MISMAS tablas en el Dashboard Financiero (/financiero/)
    y en el Dashboard de Indicadores (/indicadores/) — que es el que el cliente
    usa. Si no se pasa ``contrato``, agrega el presupuesto de TODOS los contratos
    del año (vista de proyecto). ``mes==0`` => todo el año.

    Devuelve dict con: indicadores_tecnico_financieros, resumen_ans, indicadores_ans.
    """
    # Import diferido: financiero.views importa este módulo (evita circular).
    from .views import (
        _extract_presupuesto_summary, _build_empty_datos, PresupuestoDetallado,
    )
    mes_indices = list(range(12)) if not mes else [mes - 1]
    _KEYS = ('ingreso', 'total_variables', 'total_fijos', 'total_gastos', 'resultado')

    def _resumen(tipo):
        qs = PresupuestoDetallado.objects.filter(anio=anio, tipo=tipo)
        if contrato is not None:
            qs = qs.filter(contrato=contrato)
        total = {k: 0 for k in _KEYS}
        hubo = False
        for obj in qs:
            r = _extract_presupuesto_summary(obj.datos or {}, mes_indices)
            for k in _KEYS:
                total[k] += r.get(k, 0)
            hubo = True
        if not hubo:
            return _extract_presupuesto_summary(_build_empty_datos(), mes_indices)
        total['utilidad_pct'] = ((total['ingreso'] - total['total_gastos'])
                                 / total['ingreso'] * 100) if total['ingreso'] else 0
        return total

    rp = _resumen('PLANEADO')
    rr = _resumen('REAL')
    resumen_ans = calcular_resumen_ans(linea=linea, anio=anio, mes=(mes or None))
    return {
        'indicadores_tecnico_financieros': calcular_indicadores_tecnico_financieros(rp, rr),
        'resumen_ans': resumen_ans,
        'indicadores_ans': resumen_ans.get('filas', []),
    }
