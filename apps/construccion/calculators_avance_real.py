"""Backbone de cálculo de avance REAL para los Dashboards de fase (#139).

Funciones PURAS (sin efectos colaterales, sin request) reutilizadas por las
sub-features B1 (Obra Civil) · B2 (Montaje) · B3 (Tendido) · B4 (vista torres
consolidada) · B5 (general). Cablean el avance real que YA se calcula en los
modelos (``ObraCivilTorreDetalle.avance_ponderado``,
``MontajeEstructuraTorreDetalle.avance_ponderado``,
``TendidoTorre.avance_conductor/avance_fibra``,
``ProyectoConstruccion.porcentaje_avance_civil_ponderado``) a la Curva S y a
las tarjetas — que hoy salen en 0% porque cuelgan de ``DashboardAvanceSemanal``
(solo 2 filas en prod).

Contrato (ver BLUEPRINT — Contratos de integración):
  - serie_curva_s_real(proyecto, fase)  -> {'labels':[iso], 'ejecutado':[float]}
  - serie_planeado(proyecto, fase)      -> {'labels':[iso], 'planeado':[float]}
  - avance_por_etapa(proyecto, fase)    -> [{'etapa','label','pct','completas','totales'}]
  - vista_por_torre(proyecto, fase)     -> [{'torre_id','numero','pct','completa','pendientes':[...]}]
  - avance_general(proyecto)            -> {'fases':[{'seccion','label','pct','peso'}], 'global_pct':float}
  - fecha_avance_oc/montaje/tendido(instancia) -> datetime.date  (cascada, NUNCA None)

Anclaje temporal (hallazgo crítico de datos): ``vac_fecha_vaciado`` es NULL en
los 257 oc_detalle de prod. El "avance respecto al tiempo" NO puede depender de
ese campo. Cada ``fecha_avance_*`` usa la cascada:
    vac_fecha_vaciado / *_fecha_fin  ->  updated_at  ->  created_at
``created_at`` / ``updated_at`` son NOT NULL (BaseModel) → la fecha nunca es
None. Esto permite distribuir el avance acumulado a lo largo del tiempo.

Las fases del contrato son las de ``DashboardAvanceSemanal.Fase``:
``OOCC`` (Obra Civil), ``MONTAJE``, ``TENDIDO``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

# Etiquetas canónicas de fase (alineadas con DashboardAvanceSemanal.Fase).
FASE_OOCC = 'OOCC'
FASE_MONTAJE = 'MONTAJE'
FASE_TENDIDO = 'TENDIDO'
FASES_VALIDAS = (FASE_OOCC, FASE_MONTAJE, FASE_TENDIDO)


# ==========================================================================
# Pesos de etapas — leídos de los campos editables del proyecto con default
# a los valores canónicos del Excel del cliente.
# ==========================================================================

#: Obra Civil — 6 etapas (incluye Cerramiento, ausente en calculators.ETAPAS_OC).
#: (codigo, label, campo_en_oc_detalle, atributo_peso_en_proyecto, default, es_bool)
ETAPAS_OC_PESOS = [
    ('CERRAMIENTO', 'Cerramiento', 'cerr_finalizado_ok', 'peso_cerramiento_pct', 5, True),
    ('EXCAVACION', 'Excavación', 'exc_ejecutada_pct', 'peso_excavacion_pct', 30, False),
    ('SOLADO', 'Solado', 'sol_ejecutado_pct', 'peso_solado_pct', 5, False),
    ('ACERO', 'Acero', 'ace_instalacion_pct', 'peso_acero_pct', 15, False),
    ('VACIADO', 'Vaciado', 'vac_ejecutado_pct', 'peso_vaciado_pct', 30, False),
    ('COMPACTACION', 'Compactación', 'com_finalizada_pct', 'peso_compactacion_pct', 15, False),
]

#: Montaje — 4 etapas (booleanas).
#: (codigo, label, campo_en_mont_detalle, atributo_peso_en_proyecto, default)
ETAPAS_MONTAJE_PESOS = [
    ('ESTRUCTURA_SITIO', 'Estructura en sitio', 'estructura_en_sitio_ok', 'peso_mont_estructura_sitio_pct', 10),
    ('PREARMADA', 'Prearmada', 'prearmada_ok', 'peso_mont_prearamada_pct', 20),
    ('TORRE_MONTADA', 'Torre montada', 'torre_montada_ok', 'peso_mont_torre_montada_pct', 45),
    ('REVISADA', 'Revisada', 'revisada_ok', 'peso_mont_revisada_pct', 25),
]

#: Tendido Conductor — 6 etapas booleanas (paridad TendidoTorre.COLUMNAS_CONDUCTOR).
#: (codigo, label, campo, atributo_peso, default)
ETAPAS_TENDIDO_CONDUCTOR_PESOS = [
    ('RIEGA_MANILA', 'Riega manila', 'riega_manila_conductor', 'peso_tend_riega_manila_pct', 10),
    ('RIEGA_GUAYA', 'Riega guaya', 'riega_guaya_conductor', 'peso_tend_riega_guaya_pct', 30),
    ('TENDIDO_CONDUCTOR', 'Tendido conductor', 'tendido_conductor', 'peso_tend_tendido_conductor_pct', 30),
    ('GRAPADO', 'Grapado', 'grapado_amarre_conductor', 'peso_tend_grapado_pct', 10),
    ('ACCESORIOS', 'Accesorios', 'accesorios_puentes', 'peso_tend_accesorios_pct', 10),
    ('BALIZAS', 'Balizas', 'balizas_desviadores', 'peso_tend_balizas_pct', 10),
]

#: Tendido Fibra OPGW — 5 etapas booleanas (paridad TendidoTorre.COLUMNAS_FIBRA).
ETAPAS_TENDIDO_FIBRA_PESOS = [
    ('RIEGA_MANILA_FIBRA', 'Riega manila fibra', 'riega_manila_fibra', 'peso_tend_riega_manila_fibra_pct', 10),
    ('RIEGA_GUAYA_OPGW', 'Riega guaya OPGW', 'riega_guaya_opgw', 'peso_tend_riega_guaya_opgw_pct', 20),
    ('TENDIDO_OPGW', 'Tendido OPGW', 'tendido_opgw', 'peso_tend_tendido_opgw_pct', 40),
    ('GRAPADO_FIBRA', 'Grapado fibra', 'grapado_amarre_fibra', 'peso_tend_grapado_fibra_pct', 20),
    ('EMPALMES_OPGW', 'Empalmes OPGW', 'empalmes_opgw', 'peso_tend_empalmes_opgw_pct', 10),
]

#: Mapeo sección ProgramacionFase -> (fase dashboard, label) para serie_planeado
#: y avance_general. Las 9 secciones de ProgramacionFase.Seccion.
FASE_DASHBOARD_POR_SECCION = {
    'OBRA_CIVIL': FASE_OOCC,
    'MONTAJE': FASE_MONTAJE,
    'TENDIDO': FASE_TENDIDO,
}


# ==========================================================================
# Helpers internos
# ==========================================================================

def _peso(proyecto, atributo, default) -> int:
    """Lee un peso editable del proyecto; cae al default si es None/0-falsy."""
    valor = getattr(proyecto, atributo, None)
    if valor is None:
        return int(default)
    return int(valor)


def _to_float(value) -> float:
    """Convierte Decimal/None/str a float; None -> 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ==========================================================================
# Fechas de avance — cascada que NUNCA devuelve None
# ==========================================================================

def _cascada_fecha(*candidatos) -> Optional[date]:
    """Devuelve el primer candidato no-None, normalizado a ``date``.

    Acepta ``date`` o ``datetime`` (los ``created_at``/``updated_at`` de
    BaseModel son ``DateTimeField``). Devuelve None solo si TODOS son None
    (no debería ocurrir porque created_at es NOT NULL).
    """
    for c in candidatos:
        if c is None:
            continue
        # datetime tiene .date(); date no.
        return c.date() if hasattr(c, 'date') else c
    return None


def fecha_avance_oc(detalle) -> date:
    """Fecha de avance de un ``ObraCivilTorreDetalle`` (pata).

    Cascada: vac_fecha_vaciado -> updated_at -> created_at. NUNCA None
    (created_at NOT NULL). Si por algún motivo todo fuera None, cae a hoy.
    """
    return _cascada_fecha(
        getattr(detalle, 'vac_fecha_vaciado', None),
        getattr(detalle, 'updated_at', None),
        getattr(detalle, 'created_at', None),
    ) or date.today()


def fecha_avance_montaje(d) -> date:
    """Fecha de avance de un ``MontajeEstructuraTorreDetalle``.

    Cascada: montaje_fecha_fin -> prearmado_fecha_fin -> updated_at ->
    created_at. NUNCA None.
    """
    return _cascada_fecha(
        getattr(d, 'montaje_fecha_fin', None),
        getattr(d, 'prearmado_fecha_fin', None),
        getattr(d, 'updated_at', None),
        getattr(d, 'created_at', None),
    ) or date.today()


def fecha_avance_tendido(t) -> date:
    """Fecha de avance de un ``TendidoTorre``.

    TendidoTorre no tiene fechas de etapa → cascada updated_at -> created_at.
    NUNCA None.
    """
    return _cascada_fecha(
        getattr(t, 'updated_at', None),
        getattr(t, 'created_at', None),
    ) or date.today()


# ==========================================================================
# Avance real por instancia (0..1) — reusa las properties de los modelos
# ==========================================================================

def _avance_oc_torre(detalles_pata) -> float:
    """Avance OC (0..1) de UNA torre = promedio de avance_ponderado de sus patas.

    ``ObraCivilTorreDetalle`` es por-pata (hasta 4 por torre). El % de la torre
    es el promedio del avance ponderado de las patas registradas.
    """
    patas = list(detalles_pata)
    if not patas:
        return 0.0
    suma = sum(_to_float(p.avance_ponderado) for p in patas)
    return suma / len(patas)


# ==========================================================================
# Carga de instancias por fase (queries) — encapsulado para reuso
# ==========================================================================

def _detalles_oc_por_torre(proyecto):
    """Dict torre_id -> lista de ObraCivilTorreDetalle (patas)."""
    from collections import defaultdict
    from .models_b3_oc_detalle import ObraCivilTorreDetalle
    by_torre = defaultdict(list)
    qs = (ObraCivilTorreDetalle.objects
          .filter(proyecto=proyecto, torre__aplica=True)  # #160: excluir torres no-aplica
          .select_related('torre', 'proyecto'))
    for det in qs:
        by_torre[det.torre_id].append(det)
    return by_torre


def _detalles_montaje(proyecto):
    """QuerySet de MontajeEstructuraTorreDetalle del proyecto (uno por torre)."""
    from .models_b3_mont_detalle import MontajeEstructuraTorreDetalle
    return (MontajeEstructuraTorreDetalle.objects
            .filter(proyecto=proyecto, torre__aplica=True)  # #160
            .select_related('torre', 'proyecto'))


def _tendido_torres(proyecto):
    """QuerySet de TendidoTorre del proyecto (uno por torre)."""
    from .models import TendidoTorre
    return (TendidoTorre.objects
            .filter(proyecto=proyecto, torre__aplica=True)  # #160
            .select_related('torre', 'proyecto'))


# ==========================================================================
# serie_curva_s_real — núcleo del punto 1
# ==========================================================================

def _acumular_por_fecha(pares_fecha_pct, n_torres) -> dict:
    """Construye la curva acumulada a partir de pares (fecha, avance_torre_0..1).

    Cada torre aporta ``avance_torre / n_torres * 100`` al % global del
    proyecto, anclado en su ``fecha_avance``. La serie es el acumulado del
    avance por fecha (curva S real: monótona creciente).

    Retorna {'labels':[iso], 'ejecutado':[float redondeado a 2]}.
    """
    if n_torres <= 0 or not pares_fecha_pct:
        return {'labels': [], 'ejecutado': []}
    from collections import defaultdict
    aporte_por_fecha = defaultdict(float)
    for fecha, avance in pares_fecha_pct:
        aporte_por_fecha[fecha] += (avance / n_torres) * 100.0
    fechas_ordenadas = sorted(aporte_por_fecha.keys())
    labels = []
    ejecutado = []
    acum = 0.0
    for f in fechas_ordenadas:
        acum += aporte_por_fecha[f]
        labels.append(f.isoformat())
        ejecutado.append(round(acum, 2))
    return {'labels': labels, 'ejecutado': ejecutado}


def serie_curva_s_real(proyecto, fase) -> dict:
    """Serie "Ejecutado" de la Curva S a partir del avance REAL por torre.

    El avance real ponderado por torre se distribuye en el tiempo según la
    ``fecha_avance_*`` de cada instancia y se acumula (curva S). Cada torre
    pesa 1/n_torres del 100% del proyecto.

    fase ∈ {OOCC, MONTAJE, TENDIDO}. Devuelve {'labels', 'ejecutado'}.
    Para TENDIDO el avance por torre = promedio(avance_conductor, avance_fibra).
    """
    fase = (fase or '').upper()
    n_torres = proyecto.torres.filter(aplica=True).count() or 0
    pares = []

    if fase == FASE_OOCC:
        for torre_id, patas in _detalles_oc_por_torre(proyecto).items():
            avance = _avance_oc_torre(patas)
            # Ancla en la fecha más reciente entre las patas de la torre.
            fecha = max(fecha_avance_oc(p) for p in patas)
            pares.append((fecha, avance))
    elif fase == FASE_MONTAJE:
        for d in _detalles_montaje(proyecto):
            pares.append((fecha_avance_montaje(d), _to_float(d.avance_ponderado)))
    elif fase == FASE_TENDIDO:
        for t in _tendido_torres(proyecto):
            avance = (_to_float(t.avance_conductor) + _to_float(t.avance_fibra)) / 2.0
            pares.append((fecha_avance_tendido(t), avance))
    else:
        return {'labels': [], 'ejecutado': []}

    return _acumular_por_fecha(pares, n_torres)


# ==========================================================================
# serie_planeado — del cronograma ProgramacionFase; NO inventa datos
# ==========================================================================

def serie_planeado(proyecto, fase) -> dict:
    """Serie "Planeado" de la Curva S desde el cronograma ``ProgramacionFase``.

    Interpolación lineal del ``peso_pct`` de la sección entre
    ``fecha_inicio_planeada`` y ``fecha_fin_planeada`` (mismo patrón que
    ``ProyectoConstruccion.curva_s_data``), normalizado a 0..100. Si la fase no
    tiene fechas/peso en el cronograma, cae al ``pct_programado`` del último
    ``DashboardAvanceSemanal`` de esa fase (dato manual). NO inventa datos: si
    no hay ninguno de los dos, devuelve serie vacía.

    fase ∈ {OOCC, MONTAJE, TENDIDO}. Devuelve {'labels', 'planeado'}.
    """
    fase = (fase or '').upper()
    from .models import ProgramacionFase, DashboardAvanceSemanal

    seccion = {v: k for k, v in FASE_DASHBOARD_POR_SECCION.items()}.get(fase)
    prog = None
    if seccion:
        prog = ProgramacionFase.objects.filter(proyecto=proyecto, seccion=seccion).first()

    if prog and prog.fecha_inicio_planeada and prog.fecha_fin_planeada and prog.peso_pct:
        inicio = prog.fecha_inicio_planeada
        fin = prog.fecha_fin_planeada
        total_dias = (fin - inicio).days
        # Normaliza a 0..100 dentro de la fase (la fase completa = 100).
        labels = [inicio.isoformat(), fin.isoformat()]
        planeado = [0.0, 100.0]
        if total_dias > 0:
            # Punto intermedio "hoy" si cae dentro del rango, para una curva más fiel.
            hoy = date.today()
            if inicio < hoy < fin:
                pct_hoy = round(((hoy - inicio).days / total_dias) * 100.0, 2)
                labels = [inicio.isoformat(), hoy.isoformat(), fin.isoformat()]
                planeado = [0.0, pct_hoy, 100.0]
        return {'labels': labels, 'planeado': planeado}

    # Fallback: dato manual del semanal.
    semanas = list(DashboardAvanceSemanal.objects
                   .filter(proyecto=proyecto, fase=fase)
                   .order_by('semana'))
    if semanas:
        return {
            'labels': [s.semana.isoformat() for s in semanas],
            'planeado': [round(_to_float(s.pct_programado), 2) for s in semanas],
        }
    return {'labels': [], 'planeado': []}


# ==========================================================================
# avance_por_etapa — genérico para las 3 fases (G2 universal)
# ==========================================================================

def _etapas_def_por_fase(fase):
    """Devuelve la lista de definiciones de etapa para la fase (o conductor de
    tendido). Para TENDIDO retorna conductor; usar ``avance_por_etapa_tendido``
    para conductor+fibra por separado."""
    fase = (fase or '').upper()
    if fase == FASE_OOCC:
        return ETAPAS_OC_PESOS
    if fase == FASE_MONTAJE:
        # normaliza al formato de 6 columnas (sin es_bool extra): añade es_bool=True
        return [(c, l, campo, peso_attr, default, True)
                for (c, l, campo, peso_attr, default) in ETAPAS_MONTAJE_PESOS]
    if fase == FASE_TENDIDO:
        return [(c, l, campo, peso_attr, default, True)
                for (c, l, campo, peso_attr, default) in ETAPAS_TENDIDO_CONDUCTOR_PESOS]
    return []


def avance_por_etapa(proyecto, fase) -> list:
    """% de torres COMPLETAS por etapa de la fase (G2 genérico).

    Una torre cuenta como "completa" en una etapa cuando su valor de etapa
    está al 100% (booleano True, o pct >= 1.0 para los campos 0..1 de OC).
    Para OC se agrega a nivel torre (todas las patas deben tener la etapa).

    Devuelve [{'etapa','label','pct','completas','totales'}] en el orden de la
    definición. Para TENDIDO devuelve solo conductor (usar
    ``avance_por_etapa_tendido`` para ambos sets).
    """
    fase = (fase or '').upper()
    etapas = _etapas_def_por_fase(fase)
    if not etapas:
        return []

    if fase == FASE_OOCC:
        by_torre = _detalles_oc_por_torre(proyecto)
        resultado = []
        for codigo, label, campo, _peso_attr, _default, es_bool in etapas:
            totales = len(by_torre)
            completas = 0
            for _torre_id, patas in by_torre.items():
                if es_bool:
                    ok = all(bool(getattr(p, campo, False)) for p in patas)
                else:
                    ok = all(_to_float(getattr(p, campo, 0)) >= 1.0 for p in patas)
                if ok:
                    completas += 1
            pct = round((completas / totales) * 100, 2) if totales else 0.0
            resultado.append({'etapa': codigo, 'label': label, 'pct': pct,
                              'completas': completas, 'totales': totales})
        return resultado

    if fase == FASE_MONTAJE:
        detalles = list(_detalles_montaje(proyecto))
    else:  # TENDIDO conductor
        detalles = list(_tendido_torres(proyecto))

    resultado = []
    for codigo, label, campo, _peso_attr, _default, _es_bool in etapas:
        totales = len(detalles)
        completas = sum(1 for d in detalles if bool(getattr(d, campo, False)))
        pct = round((completas / totales) * 100, 2) if totales else 0.0
        resultado.append({'etapa': codigo, 'label': label, 'pct': pct,
                          'completas': completas, 'totales': totales})
    return resultado


def avance_por_etapa_tendido(proyecto) -> dict:
    """Avance por etapa de Tendido en dos sets: conductor (6) + fibra (5).

    Devuelve {'conductor':[...], 'fibra':[...]} con el mismo formato que
    ``avance_por_etapa``. Helper específico para B3 (2 gráficas).
    """
    detalles = list(_tendido_torres(proyecto))
    totales = len(detalles)

    def _build(defs):
        out = []
        for codigo, label, campo, _peso_attr, _default in defs:
            completas = sum(1 for d in detalles if bool(getattr(d, campo, False)))
            pct = round((completas / totales) * 100, 2) if totales else 0.0
            out.append({'etapa': codigo, 'label': label, 'pct': pct,
                       'completas': completas, 'totales': totales})
        return out

    return {
        'conductor': _build(ETAPAS_TENDIDO_CONDUCTOR_PESOS),
        'fibra': _build(ETAPAS_TENDIDO_FIBRA_PESOS),
    }


# ==========================================================================
# vista_por_torre — punto 3
# ==========================================================================

def vista_por_torre(proyecto, fase) -> list:
    """Lista por torre con % de avance, si está completa y etapas pendientes.

    Devuelve [{'torre_id','numero','pct','completa','pendientes':[labels]}]
    ordenado por número de torre. fase ∈ {OOCC, MONTAJE, TENDIDO}.
    Para TENDIDO el % = promedio(conductor, fibra) y las pendientes combinan
    ambos sets.
    """
    fase = (fase or '').upper()
    resultado = []

    if fase == FASE_OOCC:
        by_torre = _detalles_oc_por_torre(proyecto)
        # Necesitamos numero por torre.
        from .models import TorreConstruccion
        numeros = {t.id: t.numero for t in
                   TorreConstruccion.objects.filter(proyecto=proyecto, aplica=True)}
        for torre_id, patas in by_torre.items():
            pct = round(_avance_oc_torre(patas) * 100, 2)
            pendientes = []
            for codigo, label, campo, _pa, _d, es_bool in ETAPAS_OC_PESOS:
                if es_bool:
                    ok = all(bool(getattr(p, campo, False)) for p in patas)
                else:
                    ok = all(_to_float(getattr(p, campo, 0)) >= 1.0 for p in patas)
                if not ok:
                    pendientes.append(label)
            resultado.append({
                'torre_id': torre_id,
                'numero': numeros.get(torre_id, ''),
                'pct': pct,
                'completa': pct >= 100.0,
                'pendientes': pendientes,
            })
    elif fase == FASE_MONTAJE:
        for d in _detalles_montaje(proyecto):
            pct = round(_to_float(d.avance_ponderado) * 100, 2)
            pendientes = [label for (_c, label, campo, _pa, _df) in ETAPAS_MONTAJE_PESOS
                          if not bool(getattr(d, campo, False))]
            resultado.append({
                'torre_id': d.torre_id,
                'numero': getattr(d.torre, 'numero', ''),
                'pct': pct,
                'completa': pct >= 100.0,
                'pendientes': pendientes,
            })
    elif fase == FASE_TENDIDO:
        for t in _tendido_torres(proyecto):
            pct = round(((_to_float(t.avance_conductor) + _to_float(t.avance_fibra)) / 2.0) * 100, 2)
            pendientes = []
            for _c, label, campo, _pa, _df in ETAPAS_TENDIDO_CONDUCTOR_PESOS:
                if not bool(getattr(t, campo, False)):
                    pendientes.append(label)
            for _c, label, campo, _pa, _df in ETAPAS_TENDIDO_FIBRA_PESOS:
                if not bool(getattr(t, campo, False)):
                    pendientes.append(label)
            resultado.append({
                'torre_id': t.torre_id,
                'numero': getattr(t.torre, 'numero', ''),
                'pct': pct,
                'completa': pct >= 100.0,
                'pendientes': pendientes,
            })

    # #161: una torre al 100% no tiene nada pendiente — limpiar la lista para que
    # el dashboard no muestre etapas "pendientes" en torres completas.
    for r in resultado:
        if r['completa']:
            r['pendientes'] = []
    # #159: orden NUMÉRICO natural de torres (E1, E2, …, E10, E11), no lexicográfico
    # de string (que daba E1, E10, E11, E2). Clave: trozos texto/número alternados.
    import re as _re

    def _natkey(numero):
        return [int(ch) if ch.isdigit() else ch.lower()
                for ch in _re.split(r'(\d+)', str(numero or ''))]
    resultado.sort(key=lambda r: _natkey(r['numero']))
    return resultado


# ==========================================================================
# avance_general — punto 4 (7 fases visibles + global ponderado)
# ==========================================================================

#: Las 7 fases del dashboard general -> (seccion ProgramacionFase, label,
#: callable que devuelve el % real 0..100 dado el proyecto).
def _pct_ingenieria(proyecto):
    # Sin modelo de ejecución dedicado: usa peso/avance esperado del cronograma.
    from .models import ProgramacionFase
    f = ProgramacionFase.objects.filter(proyecto=proyecto, seccion='INGENIERIA').first()
    return float(f.pct_avance_esperado_hoy or 0) if f else 0.0


def _pct_preliminares(proyecto):
    from .models import ProgramacionFase
    vals = []
    for sec in ('SOCIOPREDIAL', 'SOCIOAMBIENTAL'):
        f = ProgramacionFase.objects.filter(proyecto=proyecto, seccion=sec).first()
        if f and f.pct_avance_esperado_hoy is not None:
            vals.append(float(f.pct_avance_esperado_hoy))
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def _pct_obra_civil(proyecto):
    # Deriva del oc_detalle real (257 filas en prod) — mismo origen que la Curva
    # S real, NO del porcentaje_avance_civil_ponderado legacy (que cuelga de
    # torre.pata_obra y sale en 0% cuando el avance real está en oc_detalle).
    by_torre = _detalles_oc_por_torre(proyecto)
    n = proyecto.torres.filter(aplica=True).count() or 0
    if n == 0 or not by_torre:
        return 0.0
    suma = sum(_avance_oc_torre(patas) for patas in by_torre.values())
    return round((suma / n) * 100, 2)


def _pct_montaje(proyecto):
    detalles = list(_detalles_montaje(proyecto))
    n = proyecto.torres.filter(aplica=True).count() or 0
    if n == 0 or not detalles:
        return 0.0
    suma = sum(_to_float(d.avance_ponderado) for d in detalles)
    return round((suma / n) * 100, 2)


def _pct_tendido(proyecto):
    torres = list(_tendido_torres(proyecto))
    n = proyecto.torres.filter(aplica=True).count() or 0
    if n == 0 or not torres:
        return 0.0
    suma = sum((_to_float(t.avance_conductor) + _to_float(t.avance_fibra)) / 2.0 for t in torres)
    return round((suma / n) * 100, 2)


def _pct_spt_pintura(proyecto):
    from .models import SPTTorre
    qs = SPTTorre.objects.filter(proyecto=proyecto, torre__aplica=True)  # #160
    vals = [int(s.porcentaje_avance or 0) for s in qs]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def _pct_detalles_finales(proyecto):
    # ActividadFinalTorre se relaciona por torre (no tiene FK proyecto directa).
    from .models_b1_actividades_finales import ActividadFinalTorre
    qs = ActividadFinalTorre.objects.filter(torre__proyecto=proyecto, torre__aplica=True)  # #160
    vals = [float(a.pct_avance) for a in qs]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


#: (seccion, label, fn) — orden de presentación de las 7 fases.
FASES_GENERAL = [
    ('INGENIERIA', 'Ingeniería', _pct_ingenieria),
    ('SOCIOPREDIAL', 'Actividades Preliminares', _pct_preliminares),
    ('OBRA_CIVIL', 'Obra Civil', _pct_obra_civil),
    ('MONTAJE', 'Montaje', _pct_montaje),
    ('TENDIDO', 'Tendido', _pct_tendido),
    ('SPT', 'SPT y Pintura', _pct_spt_pintura),
    ('PRUEBAS', 'Detalles Finales', _pct_detalles_finales),
]


def avance_general(proyecto) -> dict:
    """Dashboard GENERAL: % por cada una de las 7 fases + global ponderado.

    Los pesos salen de ``ProgramacionFase.peso_pct`` por sección; si todos son
    0 (estado actual de prod), cae a equiponderado (1/7 cada una). El
    ``global_pct`` es el promedio ponderado de los % de fase.

    Devuelve {'fases':[{'seccion','label','pct','peso'}], 'global_pct':float}.
    """
    from .models import ProgramacionFase
    pesos_por_seccion = {
        f.seccion: int(f.peso_pct or 0)
        for f in ProgramacionFase.objects.filter(proyecto=proyecto)
    }

    fases_out = []
    for seccion, label, fn in FASES_GENERAL:
        pct = round(float(fn(proyecto)), 2)
        peso = pesos_por_seccion.get(seccion, 0)
        fases_out.append({'seccion': seccion, 'label': label, 'pct': pct, 'peso': peso})

    total_peso = sum(f['peso'] for f in fases_out)
    if total_peso > 0:
        global_pct = sum(f['pct'] * f['peso'] for f in fases_out) / total_peso
    else:
        # Fallback equiponderado (estado actual de prod: peso_pct=0).
        global_pct = sum(f['pct'] for f in fases_out) / len(fases_out) if fases_out else 0.0

    return {'fases': fases_out, 'global_pct': round(global_pct, 2)}
