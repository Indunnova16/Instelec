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
import re

from django.utils import timezone

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
    ('RIEGA_GUAYA_OPGW', 'Riega guaya cable de guarda', 'riega_guaya_opgw', 'peso_tend_riega_guaya_opgw_pct', 20),
    ('TENDIDO_OPGW', 'Tendido cable de guarda', 'tendido_opgw', 'peso_tend_tendido_opgw_pct', 40),
    ('GRAPADO_FIBRA', 'Grapado fibra', 'grapado_amarre_fibra', 'peso_tend_grapado_fibra_pct', 20),
    ('EMPALMES_OPGW', 'Empalmes cable de guarda', 'empalmes_opgw', 'peso_tend_empalmes_opgw_pct', 10),
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


def _clave_natural_torre(numero):
    """Clave estable para ``T-2`` antes de ``T-10`` y datos legacy vacíos.

    Cada fragmento lleva un marcador de tipo para que nombres que empiezan por
    números, letras o están vacíos sigan siendo comparables en Python 3.
    """
    return tuple(
        (0, int(fragment)) if fragment.isdigit() else (1, fragment.casefold())
        for fragment in re.split(r'(\d+)', str(numero or ''))
    )


def ordenar_filas_dashboard(filas, orden='numero', *, clave_torre='torre',
                             clave_fecha='fecha_orden', claves_precedencia=()):
    """Ordena filas de dashboard por torre o por su fecha real rectora.

    ``cronologico`` deja los ``NULL`` al final y, ante la misma fecha, conserva
    un desempate natural por torre. ``claves_precedencia`` permite que un Gantt
    con bloques conserve su agrupación al usar el orden por número.
    """
    filas = list(filas)

    def precedencia(fila):
        return tuple(fila.get(clave) for clave in claves_precedencia)

    if orden == 'cronologico':
        return sorted(
            filas,
            key=lambda fila: (
                fila.get(clave_fecha) is None,
                fila.get(clave_fecha),
                _clave_natural_torre(fila.get(clave_torre)),
                precedencia(fila),
            ),
        )
    return sorted(
        filas,
        key=lambda fila: (precedencia(fila), _clave_natural_torre(fila.get(clave_torre))),
    )


def _sin_fecha_orden(filas):
    """Retira el metadato interno de orden antes de exponer el contrato JSON."""
    for fila in filas:
        fila.pop('fecha_orden', None)
        fila.pop('orden_bloque', None)
    return filas


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
    ) or timezone.localdate()


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
    ) or timezone.localdate()


#: Campos de fecha MANUAL diligenciados por torre en ``FaseTorre`` (A3, #166
#: Hilo A). ``TendidoTorre`` solo guarda flags booleanos + updated_at/created_at
#: (fechas de GUARDADO del registro, no de ejecución); estas 8 columnas son las
#: fechas reales que el usuario captura por torre.
_CAMPOS_FECHA_TENDIDO_FASETORRE = (
    'fecha_riega_manila',
    'tendido_conductor_a_fecha',
    'tendido_conductor_b_fecha',
    'tendido_conductor_c_fecha',
    'tendido_opgw_izq_fecha',
    'tendido_opgw_der_fecha',
    'tendido_guarda_fecha',
    'regulacion_fecha',
)


def fecha_avance_tendido(t) -> date:
    """Fecha de avance de un ``TendidoTorre``.

    A3 (#166 Hilo A, reproceso bounce=2): la cascada legacy
    updated_at -> created_at ancla la Curva S en la fecha de GUARDADO del
    registro (BD prod: 2026-06-08..2026-06-19), no en la fecha real de
    ejecución que el usuario diligencia por torre en ``FaseTorre``
    (BD prod: 2025-07..2025-10 para las mismas torres) — eso desplazaba la
    Curva S ~9-11 meses hacia el futuro (bug reportado por el cliente).

    Se intenta PRIMERO el MAX de las fechas pobladas de ``t.torre.fase``
    (getattr defensivo: el OneToOne reverse ``TorreConstruccion.fase`` puede
    no existir — ``RelatedObjectDoesNotExist`` es subclase de
    ``AttributeError``, así que ``getattr(..., None)`` devuelve None sin
    excepción), EXCLUYENDO fechas futuras (> hoy) como guard anti-typo (BD
    prod tiene 1 fecha corrupta a 2028 en torre E58 que de otro modo
    contaminaría la Curva S con un punto en el futuro). Si NINGUNA fecha de
    FaseTorre está poblada (o todas son futuras), cae a la cascada legacy
    updated_at -> created_at. NUNCA None.
    """
    fase_torre = getattr(t.torre, 'fase', None)
    if fase_torre is not None:
        hoy = timezone.localdate()
        candidatas = []
        for campo in _CAMPOS_FECHA_TENDIDO_FASETORRE:
            valor = getattr(fase_torre, campo, None)
            if valor is None:
                continue
            valor = valor.date() if hasattr(valor, 'date') else valor
            if valor > hoy:
                continue  # guard anti-typo (p.ej. 2028 en vez de 2025)
            candidatas.append(valor)
        if candidatas:
            return max(candidatas)

    return _cascada_fecha(
        getattr(t, 'updated_at', None),
        getattr(t, 'created_at', None),
    ) or timezone.localdate()


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
            hoy = timezone.localdate()
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
# Curva S por FECHAS REALES — conteo acumulado de torres (#122 Fase 2)
# ==========================================================================
# Decisión de Miguel (#122): las series de los dashboards de Obra Civil y
# Montaje deben anclarse en las FECHAS REALES por torre (2025), no en la cascada
# updated_at (que cae a 2026) ni en el cronograma project-level (vacío en QA).
# La métrica es CONTEO DE TORRES (acumulado, normalizado a % sobre el total de
# torres aplica=True), NO el avance ponderado por etapas:
#   - OC Planeado  = acumulado de torres por ObraCivilTorre.fecha_esperada
#   - OC Ejecutado = acumulado de torres por ObraCivilTorre.fecha_final
#   - Montaje Ejecutado = acumulado de torres por montaje_fecha_fin
# Cada punto = {fecha ISO, pct = conteo_acumulado / n_torres_aplica * 100}.

def _serie_conteo_por_fecha(fechas, n_torres, clave_data) -> dict:
    """Curva S de CONTEO de torres acumulado, normalizado a % sobre n_torres.

    ``fechas`` = iterable de ``date`` (una por torre con la fecha poblada; los
    NULL se filtran ANTES de llamar). Agrupa por fecha, acumula el conteo y lo
    expresa como % del total de torres (aplica=True). Monótona creciente.

    Retorna ``{'labels':[iso], <clave_data>:[float redondeado a 2]}`` para que
    el contrato de salida sea el mismo que ``serie_curva_s_real`` (clave_data=
    'ejecutado') o ``serie_planeado`` (clave_data='planeado'), y NO haya que
    tocar el JS de los templates.
    """
    if n_torres <= 0:
        return {'labels': [], clave_data: []}
    from collections import defaultdict
    conteo_por_fecha = defaultdict(int)
    for f in fechas:
        if f is None:
            continue
        conteo_por_fecha[f] += 1
    if not conteo_por_fecha:
        return {'labels': [], clave_data: []}
    fechas_ordenadas = sorted(conteo_por_fecha.keys())
    labels = []
    data = []
    acum = 0
    for f in fechas_ordenadas:
        acum += conteo_por_fecha[f]
        labels.append(f.isoformat())
        data.append(round((acum / n_torres) * 100.0, 2))
    return {'labels': labels, clave_data: data}


def serie_planeado_oc_fechas(proyecto) -> dict:
    """Serie "Planeado" de Obra Civil por FECHAS REALES (#122 Fase 2).

    Acumula el CONTEO de torres (aplica=True) por su
    ``ObraCivilTorre.fecha_esperada`` (los NULL se ignoran), ordenado por fecha,
    normalizado a % sobre el total de torres aplica=True. Reemplaza al
    cronograma project-level (vacío en QA) como fuente del "Planeado" de OC.

    Devuelve ``{'labels':[iso], 'planeado':[float]}`` (mismo contrato que
    ``serie_planeado``).
    """
    from .models import ObraCivilTorre
    n_torres = proyecto.torres.filter(aplica=True).count() or 0
    qs = (ObraCivilTorre.objects
          .filter(proyecto=proyecto, torre__aplica=True, fecha_esperada__isnull=False)
          .values_list('fecha_esperada', flat=True))
    return _serie_conteo_por_fecha(list(qs), n_torres, 'planeado')


def serie_ejecutado_oc_fechas(proyecto) -> dict:
    """Serie "Ejecutado" de Obra Civil por FECHAS REALES (#122 Fase 2).

    Acumula el CONTEO de torres (aplica=True) por su
    ``ObraCivilTorre.fecha_final`` (los NULL se ignoran), ordenado por fecha,
    normalizado a % sobre el total de torres aplica=True. Ancla el "Ejecutado"
    en las fechas reales (2025), NO en la cascada ``updated_at`` (2026).

    Devuelve ``{'labels':[iso], 'ejecutado':[float]}`` (mismo contrato que
    ``serie_curva_s_real``).
    """
    from .models import ObraCivilTorre
    n_torres = proyecto.torres.filter(aplica=True).count() or 0
    qs = (ObraCivilTorre.objects
          .filter(proyecto=proyecto, torre__aplica=True, fecha_final__isnull=False)
          .values_list('fecha_final', flat=True))
    return _serie_conteo_por_fecha(list(qs), n_torres, 'ejecutado')


def serie_ejecutado_montaje_fechas(proyecto) -> dict:
    """Serie "Ejecutado" de Montaje por FECHAS REALES (#122 Fase 2).

    Acumula el CONTEO de torres (aplica=True) por su
    ``MontajeEstructuraTorreDetalle.montaje_fecha_fin`` (los NULL se ignoran),
    ordenado por fecha, normalizado a % sobre el total de torres aplica=True.
    Ancla el "Ejecutado" de Montaje en las fechas reales (2025), NO en la
    cascada ``updated_at`` (2026).

    NOTA DE SCOPE (#122): Montaje NO tiene un campo "fecha esperada" por torre
    equivalente a ``ObraCivilTorre.fecha_esperada`` → el "Planeado" de Montaje
    por fechas queda PENDIENTE de agregar dicho campo al modelo
    ``MontajeEstructuraTorreDetalle``. No se inventa una serie planeada; el
    Planeado de Montaje se deja como está hoy (cronograma / plano) hasta que el
    cliente confirme el campo de fecha esperada de montaje.

    Devuelve ``{'labels':[iso], 'ejecutado':[float]}`` (mismo contrato que
    ``serie_curva_s_real``).
    """
    from .models_b3_mont_detalle import MontajeEstructuraTorreDetalle
    n_torres = proyecto.torres.filter(aplica=True).count() or 0
    qs = (MontajeEstructuraTorreDetalle.objects
          .filter(proyecto=proyecto, torre__aplica=True, montaje_fecha_fin__isnull=False)
          .values_list('montaje_fecha_fin', flat=True))
    return _serie_conteo_por_fecha(list(qs), n_torres, 'ejecutado')


# ==========================================================================
# Gantt de Obra Civil — barras por torre (#122 Fase 2)
# ==========================================================================

def gantt_oc(proyecto, orden='numero') -> list:
    """Datos del Gantt de Obra Civil: una barra por torre con sus 3 fechas.

    Devuelve ``[{'torre','inicio','esperada','final'}]`` (fechas en ISO o None)
    ordenado por ``TorreConstruccion.orden_numerico``, SOLO para las torres
    aplica=True que tienen ``fecha_inicio`` poblada (sin inicio no hay barra).

    El template del Dashboard OC lo pinta como barras horizontales (una por
    torre) con Chart.js (indexAxis:'y'), barra flotante [inicio, final].
    """
    from .models import ObraCivilTorre
    qs = (ObraCivilTorre.objects
          .filter(proyecto=proyecto, torre__aplica=True, fecha_inicio__isnull=False)
          .select_related('torre'))
    def _iso(d):
        return d.isoformat() if d else None

    filas = []
    for oc in qs:
        filas.append({
            'torre': oc.torre.numero_display or (oc.torre.numero or ''),
            'inicio': _iso(oc.fecha_inicio),
            'esperada': _iso(oc.fecha_esperada),
            'final': _iso(oc.fecha_final),
            # La fecha de cierre es la única fecha REAL rectora de OC; una
            # planeada o timestamp de edición no debe reordenar al cliente.
            'fecha_orden': oc.fecha_final,
        })
    return _sin_fecha_orden(ordenar_filas_dashboard(filas, orden))


# ===========================================================================
# Gantt consolidado — Obra Civil, Montaje y Tendido (#204)
# ===========================================================================

def gantt_consolidado(proyecto, orden='numero') -> list:
    """Filas del Gantt consolidado, una barra por torre y bloque.

    Cada fila conserva el contrato del Gantt de Obra Civil (``inicio``,
    ``esperada`` y ``final`` en ISO) y añade ``bloque`` para diferenciar sus
    tres fuentes.  Solo incorpora torres ``aplica=True`` que tengan al menos
    una fecha real: una barra sin fechas no comunica avance y Chart.js no la
    puede posicionar de manera fiable.

    Tendido no tiene fechas en ``TendidoTorre``: las fechas reales se capturan
    en la relación legacy ``FaseTorre``.  Por eso su tramo se forma entre la
    primera y última fecha diligenciada allí, sin usar ``updated_at`` (que es
    fecha de guardado, no de ejecución).
    """
    filas = []

    for fila in gantt_oc(proyecto, orden='numero'):
        filas.append({
            **fila,
            'bloque': 'Obra Civil',
            'fecha_orden': date.fromisoformat(fila['final']) if fila['final'] else None,
            'orden_bloque': 0,
        })

    from .models_b3_mont_detalle import MontajeEstructuraTorreDetalle
    montajes = (MontajeEstructuraTorreDetalle.objects
                .filter(proyecto=proyecto, torre__aplica=True)
                .select_related('torre'))
    for detalle in montajes:
        fechas = [
            detalle.prearmado_fecha_inicio,
            detalle.prearmado_fecha_fin,
            detalle.montaje_fecha_inicio,
            detalle.montaje_fecha_fin,
        ]
        fechas = [fecha for fecha in fechas if fecha]
        if not fechas:
            continue
        filas.append({
            'bloque': 'Montaje',
            'torre': detalle.torre.numero_display or (detalle.torre.numero or ''),
            'inicio': min(fechas).isoformat(),
            'esperada': None,
            'final': max(fechas).isoformat(),
            'fecha_orden': detalle.montaje_fecha_fin,
            'orden_bloque': 1,
        })

    from .models import FaseTorre
    tendidos = (FaseTorre.objects
                .filter(proyecto=proyecto, torre__aplica=True)
                .select_related('torre'))
    for fase in tendidos:
        fechas = [getattr(fase, campo, None)
                  for campo in _CAMPOS_FECHA_TENDIDO_FASETORRE]
        fechas = [fecha for fecha in fechas if fecha]
        if not fechas:
            continue
        filas.append({
            'bloque': 'Tendido',
            'torre': fase.torre.numero_display or (fase.torre.numero or ''),
            'inicio': min(fechas).isoformat(),
            'esperada': None,
            'final': max(fechas).isoformat(),
            'fecha_orden': max(fechas),
            'orden_bloque': 2,
        })

    # El orden del Gantt es por *torre*, no por barra.  Ordenar cada fila por
    # su propia fecha puede intercalar, por ejemplo, el Tendido de T-1 entre
    # Obra Civil y Montaje de T-2.  La fecha rectora del grupo es la primera
    # fecha real disponible de cualquiera de sus bloques; los tres bloques
    # quedan consecutivos y conservan su secuencia de ejecución visual.
    grupos = {}
    for fila in filas:
        grupos.setdefault(fila['torre'], []).append(fila)

    def clave_grupo(item):
        torre, bloques = item
        fechas = [bloque['fecha_orden'] for bloque in bloques
                  if bloque['fecha_orden'] is not None]
        fecha_rectora = min(fechas) if fechas else None
        if orden == 'cronologico':
            return (fecha_rectora is None, fecha_rectora, _clave_natural_torre(torre))
        return (_clave_natural_torre(torre),)

    ordenadas = []
    for _torre, bloques in sorted(grupos.items(), key=clave_grupo):
        ordenadas.extend(sorted(bloques, key=lambda bloque: bloque['orden_bloque']))
    return _sin_fecha_orden(ordenadas)


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

def _fechas_rectoras_por_torre(proyecto, fase):
    """Devuelve la fecha real rectora disponible de cada torre por fase.

    No usa ``updated_at`` ni ``created_at``: ambos describen cuándo se guardó
    un registro, no cuándo se ejecutó el trabajo. Las torres legacy sin fecha
    quedan explícitamente en ``None`` para que el orden cronológico las deje al
    final.
    """
    fase = (fase or '').upper()
    if fase == FASE_OOCC:
        from .models import ObraCivilTorre
        return {
            fila.torre_id: fila.fecha_final
            for fila in ObraCivilTorre.objects.filter(proyecto=proyecto, torre__aplica=True)
        }
    if fase == FASE_MONTAJE:
        return {
            fila.torre_id: fila.montaje_fecha_fin
            for fila in _detalles_montaje(proyecto)
        }
    if fase == FASE_TENDIDO:
        from .models import FaseTorre
        fechas = {}
        for fila in FaseTorre.objects.filter(proyecto=proyecto, torre__aplica=True):
            candidatas = [getattr(fila, campo, None) for campo in _CAMPOS_FECHA_TENDIDO_FASETORRE]
            fechas[fila.torre_id] = max((fecha for fecha in candidatas if fecha), default=None)
        return fechas
    return {}


def vista_por_torre(proyecto, fase, orden='numero') -> list:
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
    fechas_rectoras = _fechas_rectoras_por_torre(proyecto, fase)
    for fila in resultado:
        fila['fecha_orden'] = fechas_rectoras.get(fila['torre_id'])
    return _sin_fecha_orden(ordenar_filas_dashboard(resultado, orden, clave_torre='numero'))


# ==========================================================================
# avance_general — matriz de fuentes rectoras por sección
# ==========================================================================

# Cada función devuelve ``float`` cuando existe una fuente de ejecución y
# ``None`` cuando esa fuente todavía no tiene filas.  Es una diferencia
# importante: 0.0 significa progreso real capturado en cero; None permite al
# cronograma mostrar SIN_DATA, sin convertir una ausencia de módulo en 0%.
def _promedio(valores):
    valores = list(valores)
    return round(sum(valores) / len(valores), 2) if valores else None


def _pct_ingenieria(proyecto):
    """Documentos de ingeniería CUMPLE sobre los que aplican.

    ``NO_APLICA`` se excluye del denominador. Si aún no se ha capturado ningún
    documento, no se infiere el avance desde el cronograma planeado.
    """
    from apps.ingenieria.models import IngenieriaEstado

    estados = IngenieriaEstado.objects.filter(
        torre__contrato=proyecto.contrato,
        torre__archivada=False,
    ).exclude(estado__isnull=True)
    if not estados.exists():
        return None
    aplicables = estados.exclude(estado=IngenieriaEstado.Estado.NO_APLICA)
    total = aplicables.count()
    if total == 0:
        return 100.0
    completos = aplicables.filter(estado=IngenieriaEstado.Estado.CUMPLE).count()
    return round((completos / total) * 100, 2)


def _pct_sociopredial(proyecto):
    from .models import SocialPredial

    filas = SocialPredial.objects.filter(torre__proyecto=proyecto, torre__aplica=True)
    return _promedio(100.0 if fila.liberado else 0.0 for fila in filas)


def _pct_socioambiental(proyecto):
    from .models import AmbientalTorre

    filas = AmbientalTorre.objects.filter(torre__proyecto=proyecto, torre__aplica=True)
    return _promedio(100.0 if fila.liberado else 0.0 for fila in filas)


def _pct_obra_civil(proyecto):
    # Deriva del oc_detalle real (257 filas en prod) — mismo origen que la Curva
    # S real, NO del porcentaje_avance_civil_ponderado legacy (que cuelga de
    # torre.pata_obra y sale en 0% cuando el avance real está en oc_detalle).
    by_torre = _detalles_oc_por_torre(proyecto)
    n = proyecto.torres.filter(aplica=True).count() or 0
    if n == 0 or not by_torre:
        return None
    suma = sum(_avance_oc_torre(patas) for patas in by_torre.values())
    return round((suma / n) * 100, 2)


def _pct_montaje(proyecto):
    detalles = list(_detalles_montaje(proyecto))
    n = proyecto.torres.filter(aplica=True).count() or 0
    if n == 0 or not detalles:
        return None
    suma = sum(_to_float(d.avance_ponderado) for d in detalles)
    return round((suma / n) * 100, 2)


def _pct_tendido(proyecto):
    torres = list(_tendido_torres(proyecto))
    n = proyecto.torres.filter(aplica=True).count() or 0
    if n == 0 or not torres:
        return None
    suma = sum((_to_float(t.avance_conductor) + _to_float(t.avance_fibra)) / 2.0 for t in torres)
    return round((suma / n) * 100, 2)


def _pct_spt_pintura(proyecto):
    from .models import SPTTorre
    qs = SPTTorre.objects.filter(proyecto=proyecto, torre__aplica=True)  # #160
    return _promedio(int(s.porcentaje_avance) for s in qs)


def _pct_protecciones(proyecto):
    from .models import TrinchoCuneta

    filas = TrinchoCuneta.objects.filter(
        proyecto=proyecto,
        torre__aplica=True,
        torre__obra_civil__aplica_obras_proteccion=True,
    )
    return _promedio(100.0 if fila.completado else 0.0 for fila in filas)


def _pct_detalles_finales(proyecto):
    # ActividadFinalTorre se relaciona por torre (no tiene FK proyecto directa).
    from .models_b1_actividades_finales import ActividadFinalTorre
    qs = ActividadFinalTorre.objects.filter(torre__proyecto=proyecto, torre__aplica=True)  # #160
    return _promedio(float(a.pct_avance) for a in qs)


#: (seccion, label, fn) — las nueve secciones del cronograma, en su orden
#: contractual. Ninguna fuente usa el porcentaje planeado como sustituto.
FASES_GENERAL = [
    ('INGENIERIA', 'Ingeniería', _pct_ingenieria),
    ('SOCIOPREDIAL', 'Actividades Preliminares — Sociopredial', _pct_sociopredial),
    ('SOCIOAMBIENTAL', 'Actividades Preliminares — Socioambiental', _pct_socioambiental),
    ('OBRA_CIVIL', 'Obra Civil', _pct_obra_civil),
    ('MONTAJE', 'Montaje', _pct_montaje),
    ('SPT', 'SPT y Pintura', _pct_spt_pintura),
    ('TENDIDO', 'Tendido', _pct_tendido),
    ('PROTECCIONES', 'Trinchos y Cunetas', _pct_protecciones),
    ('PRUEBAS', 'Detalles Finales', _pct_detalles_finales),
]


def avance_general(proyecto) -> dict:
    """Dashboard GENERAL: % por las nueve fases + global ponderado.

    Los pesos salen de ``ProgramacionFase.peso_pct`` por sección; si todos son
    0 (estado actual de prod), cae a equiponderado entre las fuentes con dato.
    ``global_pct`` es el promedio ponderado de las fases con fuente real. Las
    secciones sin filas quedan con ``pct=None`` (SIN_DATA) y no distorsionan el
    agregado.

    Devuelve {'fases':[{'seccion','label','pct','peso'}], 'global_pct':float}.
    """
    from .models import ProgramacionFase
    pesos_por_seccion = {
        f.seccion: int(f.peso_pct or 0)
        for f in ProgramacionFase.objects.filter(proyecto=proyecto)
    }

    fases_out = []
    for seccion, label, fn in FASES_GENERAL:
        valor = fn(proyecto)
        pct = round(float(valor), 2) if valor is not None else None
        peso = pesos_por_seccion.get(seccion, 0)
        fases_out.append({'seccion': seccion, 'label': label, 'pct': pct, 'peso': peso})

    fases_con_dato = [fase for fase in fases_out if fase['pct'] is not None]
    total_peso = sum(f['peso'] for f in fases_con_dato)
    if total_peso > 0:
        global_pct = sum(f['pct'] * f['peso'] for f in fases_con_dato) / total_peso
    else:
        # Fallback equiponderado cuando los pesos aún no se configuraron.
        global_pct = (sum(f['pct'] for f in fases_con_dato) / len(fases_con_dato)
                      if fases_con_dato else None)

    return {'fases': fases_out,
            'global_pct': round(global_pct, 2) if global_pct is not None else None}


def avance_modulos(proyecto) -> dict:
    """Porcentajes reales de los tres módulos mostrados en el dashboard.

    Mantiene un único origen de cálculo para las tarjetas consolidadas y para
    ``avance_general``. Las fases sin torres o sin registros devuelven 0.0 por
    contrato, por lo que el dashboard puede renderizar proyectos nuevos sin
    excepciones ni valores ``None``.
    """
    por_seccion = {fase['seccion']: fase['pct']
                   for fase in avance_general(proyecto)['fases']}
    return {
        # Las tarjetas históricas de módulos no tienen estado SIN_DATA; para
        # ellas mantenemos el contrato previo de presentar cero sin convertir
        # ese cero en el valor del cronograma.
        'obra_civil': por_seccion.get('OBRA_CIVIL') or 0.0,
        'montaje': por_seccion.get('MONTAJE') or 0.0,
        'tendido': por_seccion.get('TENDIDO') or 0.0,
    }
