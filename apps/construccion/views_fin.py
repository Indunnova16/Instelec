"""B4 (#123) — Vistas + Mixin del Módulo Financiero de Construcción (Fase 2).

6 vistas bajo ``/construccion/<uuid:proyecto_id>/financiero/<subruta>/``:

1. ``DashboardFinancieroConstruccionView``  → name ``fin_dashboard``
2. ``PresupuestoPlaneadoConstruccionView``  → name ``fin_presupuesto_planeado``
3. ``PresupuestoRealConstruccionView``       → name ``fin_presupuesto_real``
4. ``NominaConstruccionView``                → name ``fin_nomina``
5. ``CostosDetalladoConstruccionView``       → name ``fin_costos``
6. ``FacturacionConstruccionView``           → name ``fin_facturacion``

Reusos clave (issue #123 Fase 2/6):
- Modelos B3 (``models_fin``): PresupuestoDetalladoConstruccion, CostosConstruccion,
  FacturacionConstruccion, IndicadorANSConstruccion.
- Helpers de #122 (``apps.financiero.indicadores_finv2``):
  ``calcular_indicadores_tecnico_financieros`` + ``calcular_resumen_ans``.

GATE DE SUBMÓDULO
-----------------
``'FINANCIERO'`` es un sub-módulo **registrado y válido**:
``apps.core.permissions.SUBMODULO_FINANCIERO = 'FINANCIERO'`` ∈ ``TODOS_SUBMODULOS``
y ya lo usa ``FinancieroGridView`` (views.py). Por eso ``ProyectoFinMixin`` usa
``SubModuloRequiredMixin`` con ``required_submodulo = 'FINANCIERO'``.

⚠️ **Corrección (Instelec#267 A7, 2026-09-23):** el comentario original acá
decía "los roles admin pasan vía RoleRequiredMixin de todos modos" — es
INEXACTO. ``RoleRequiredMixin.test_func`` (``apps/core/mixins.py``) resuelve
el branch ``required_submodulo`` **ANTES** de llegar al bypass
``admin_bypass``/``user_es_admin``: para estas 6 vistas el acceso lo decide
**exclusivamente** ``RoleModuloPermiso`` (nivel ``ver``/``ver_editar`` sobre
``CONSTRUCCION``/``FINANCIERO``), sin importar si el rol tiene
``nivel='admin'`` en BD. Esto fue la causa raíz real de #267 A7:
``admin_construccion`` tenía solo ``ver`` (no podía cargar presupuesto) y
``gerente_financiero``/``contador``/``supervisor`` no tenían fila alguna
(sin acceso total) — sembrado/corregido por la migración
``core.0011_seed_construccion_financiero_matriz_roles_267``. Ver
``apps/construccion/permissions_fin.py`` para la matriz de roles completa
(cargar/ver/reportes-por-formato) y su fuente (respuesta del cliente en el
issue).

Templates (``construccion/financiero_*.html``) los crea B5; F4 corre después de
B5, así que referenciar ``template_name`` aquí es seguro aunque el archivo aún
no exista en esta branch.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin, SubModuloRequiredMixin
from apps.financiero.importers_finv2 import (
    MESES_FISCALES_KEYS,
    build_mes_filter_rows,
    build_rubro_display_rows,
    build_rubro_matrix_rows,
)
# Instelec#267 A5 — mismo patrón de reuso cross-módulo que importers.py ya
# aplica: normalización de texto (acentos/mayúsculas/espacios) para comparar
# la Clasificación cruda de ``filas_detalle`` contra el vocabulario fijo
# {ingresos, fijo, variable} sin depender de cómo la tipeó el cliente en Excel.
from apps.financiero.importers_finv2_carga import _normalizar as _fin_normalizar
from apps.financiero.indicadores_finv2 import (
    calcular_indicadores_tecnico_financieros,
    calcular_resumen_ans,
)
from apps.financiero.models_finv2_mapeo import RUBRO_NO_CLASIFICADO

from .importers import (
    ContableConstruccionExcelImporter,
    PresupuestoConstruccionExcelImporter,
    PresupuestoPlanoConstruccionExcelImporter,
    detect_excel_format_construccion,
)
# Instelec#267 A7 — matriz de roles (cargar/ver/reportes-por-formato). Cargar
# y Ver ya los gatea ProyectoFinMixin vía RoleModuloPermiso (ver docstring de
# GATE DE SUBMÓDULO arriba); acá solo se consume el permiso POR FORMATO de
# reporte, que la matriz RBAC genérica no puede expresar (contrato con A10).
from .permissions_fin import formatos_reporte_permitidos
# Instelec#267 A8 — reusa el MISMO agregador rubro×mes que el importador (A2)
# usa para construir finv2_bd desde filas_detalle, en vez de duplicar la
# lógica de suma. Los filtros de Clasificación/Ciudad solo cambian QUÉ
# subconjunto de filas entra, no cómo se agregan.
from .importers import _construir_finv2_bd_desde_filas_planas
from .models import ProyectoConstruccion
from .models_fin import (
    CostosConstruccion,
    FacturacionConstruccion,
    HistorialCargaPresupuestoConstruccion,
    IndicadorANSConstruccion,
    PresupuestoDetalladoConstruccion,
)

# Roles administrativos con acceso al financiero (espejo de views.py::ALL_ADMIN_ROLES).
ALL_ADMIN_ROLES = [
    'admin', 'director', 'coordinador', 'ing_residente',
    'admin_general', 'coordinador_general', 'admin_construccion',
]


def _to_decimal(valor) -> Decimal:
    """int/float/Decimal/str/None → Decimal seguro (nunca lanza)."""
    if isinstance(valor, Decimal):
        return valor
    if valor is None:
        return Decimal('0')
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')


def _parse_periodo(request):
    """Lee ?anio=&mes= del querystring con fallback a hoy.

    Edge case: parámetros inválidos (no numéricos, mes fuera de 1..12) caen al
    valor por defecto sin romper la vista (un 500 por ValueError sería un bug
    de UX: el dashboard debe abrir siempre).
    """
    hoy = date.today()
    try:
        anio = int(request.GET.get('anio', hoy.year))
    except (TypeError, ValueError):
        anio = hoy.year
    try:
        mes = int(request.GET.get('mes', hoy.month))
        if not 1 <= mes <= 12:
            mes = hoy.month
    except (TypeError, ValueError):
        mes = hoy.month
    return anio, mes


# ===========================================================================
# Mixin común
# ===========================================================================
class ProyectoFinMixin(LoginRequiredMixin, RoleRequiredMixin, SubModuloRequiredMixin):
    """Resuelve el ``ProyectoConstruccion`` por ``proyecto_id`` y aplica gates.

    - ``LoginRequiredMixin``      → redirige a login si anónimo.
    - ``RoleRequiredMixin``       → roles admin de construcción (admin level
      siempre pasa vía RBAC v2).
    - ``SubModuloRequiredMixin``  → gate del sub-módulo FINANCIERO (registrado).

    Inyecta al contexto: ``proyecto``, ``active_tab='financiero'``, ``anio``,
    ``mes`` (estos dos del querystring con fallback a hoy).

    Edge case manejado: ``proyecto_id`` inexistente → 404 (get_object_or_404),
    no un 500.
    """
    allowed_roles = ALL_ADMIN_ROLES
    required_submodulo = 'FINANCIERO'
    active_subtab = None  # cada vista la sobreescribe (dashboard/planeado/...)

    def get_proyecto(self):
        if not hasattr(self, '_proyecto_cache'):
            self._proyecto_cache = get_object_or_404(
                ProyectoConstruccion, pk=self.kwargs['proyecto_id']
            )
        return self._proyecto_cache

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = self.get_proyecto()
        anio, mes = _parse_periodo(self.request)
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'financiero'
        ctx['active_subtab'] = self.active_subtab
        ctx['anio'] = anio
        ctx['mes'] = mes
        # Instelec#267 A7 — formatos de reporte (pdf/excel/ppt/csv) que el
        # usuario actual puede descargar, para que CUALQUIER template de
        # este módulo (hoy o cuando A10 agregue los botones de descarga)
        # oculte lo que no aplica SIN depender de un segundo gate server-side
        # distinto del de permissions_fin.py — la fuente de verdad es una
        # sola. Set vacío = sin botones de descarga (p.ej. supervisor).
        ctx['formatos_reporte_permitidos'] = formatos_reporte_permitidos(self.request.user)
        return ctx

    # ----- Helpers de resumen presupuestal compartidos -------------------
    def _resumen_presupuesto(self, proyecto, anio, tipo):
        """Construye el dict ``resumen`` que consumen los indicadores #122.

        Suma los valores mensuales del JSON ``datos`` de
        ``PresupuestoDetalladoConstruccion`` (proyecto, anio, tipo) y produce
        las keys que ``calcular_indicadores_tecnico_financieros`` espera:
        ``ingreso``, ``total_variables``, ``total_fijos``, ``total_gastos``,
        ``resultado``, ``utilidad_pct``.

        Estructura esperada de ``datos`` (flexible — se navega defensivamente):
            {"ingreso": {"enero": 100, ...},
             "variables": {...}, "fijos": {...}}

        Edge case: presupuesto inexistente para (proyecto, anio, tipo) →
        resumen en ceros (no 404; el dashboard muestra "sin datos").
        """
        ingreso = total_variables = total_fijos = Decimal('0')
        presupuesto = (
            PresupuestoDetalladoConstruccion.objects
            .filter(proyecto=proyecto, anio=anio, tipo=tipo)
            .first()
        )
        if presupuesto and isinstance(presupuesto.datos, dict):
            ingreso = self._sumar_seccion(presupuesto.datos, ('ingreso', 'ingresos', 'facturacion'))
            total_variables = self._sumar_seccion(
                presupuesto.datos, ('variables', 'costos_variables', 'costos_directos'))
            total_fijos = self._sumar_seccion(
                presupuesto.datos, ('fijos', 'costos_fijos', 'gastos'))

        total_gastos = total_variables + total_fijos
        resultado = ingreso - total_gastos
        utilidad_pct = (
            (resultado / ingreso * Decimal('100')) if ingreso else Decimal('0')
        )
        return {
            'ingreso': ingreso,
            'total_variables': total_variables,
            'total_fijos': total_fijos,
            'total_gastos': total_gastos,
            'resultado': resultado,
            'utilidad_pct': utilidad_pct.quantize(Decimal('0.01')),
        }

    # ----- A3 (#120): contexto bi-modal (matriz / filtro mes) ------------
    def _bimodal_context(self, datos):
        """Mismo contrato que el lado Mantenimiento (#120 A2).

        Alimenta el partial COMPARTIDO
        ``financiero/_presupuesto_bimodal_tabla.html`` con la matriz rubro × 12
        meses (julio→junio) y el filtro por mes, leyendo ``?vista=`` y ``?mes=``.
        """
        vista = self.request.GET.get('vista', 'matriz')
        if vista not in ('matriz', 'mes'):
            vista = 'matriz'

        matrix_rows, totales_columna, meses_fiscales, total_general = (
            build_rubro_matrix_rows(datos)
        )

        mes_sel = self.request.GET.get('mes') or MESES_FISCALES_KEYS[0]
        if mes_sel not in MESES_FISCALES_KEYS:
            mes_sel = MESES_FISCALES_KEYS[0]
        mes_rows, mes_total, mes_label = build_mes_filter_rows(datos, mes_sel)

        hidden = {
            k: v for k, v in self.request.GET.items()
            if k not in ('vista', 'mes') and v
        }
        base_qs = ''.join(f'{k}={v}&' for k, v in hidden.items())

        return {
            'vista': vista,
            'matrix_rows': matrix_rows,
            'totales_columna': totales_columna,
            'meses_fiscales': meses_fiscales,
            'matrix_total': total_general,
            'mes_sel': mes_sel,
            'mes_rows': mes_rows,
            'mes_total': mes_total,
            'mes_label': mes_label,
            'bimodal_base_qs': base_qs,
            'bimodal_hidden_params': hidden,
        }

    @staticmethod
    def _sumar_seccion(datos, keys):
        """Suma todos los valores numéricos de la primera key presente en ``datos``.

        Acepta tanto ``{key: {mes: valor}}`` como ``{key: valor}``.
        """
        for key in keys:
            seccion = datos.get(key)
            if seccion is None:
                continue
            if isinstance(seccion, dict):
                total = Decimal('0')
                for v in seccion.values():
                    if isinstance(v, dict):
                        for vv in v.values():
                            total += _to_decimal(vv)
                    else:
                        total += _to_decimal(v)
                return total
            return _to_decimal(seccion)
        return Decimal('0')


# ===========================================================================
# 1. DASHBOARD FINANCIERO
# ===========================================================================
class DashboardFinancieroConstruccionView(ProyectoFinMixin, TemplateView):
    """Dashboard financiero comparativo planeado vs real + KPIs + ANS (#123).

    Context (issue #123 Fase 2.1):
        proyecto, anio, mes, resumen_planeado, resumen_real,
        indicadores_tecnico_financieros, indicadores_ans, resumen_ans.
    """
    template_name = 'construccion/financiero_dashboard.html'
    active_subtab = 'dashboard'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = ctx['proyecto']
        anio = ctx['anio']

        resumen_planeado = self._resumen_presupuesto(
            proyecto, anio, PresupuestoDetalladoConstruccion.Tipo.PLANEADO)
        resumen_real = self._resumen_presupuesto(
            proyecto, anio, PresupuestoDetalladoConstruccion.Tipo.REAL)

        ctx['resumen_planeado'] = resumen_planeado
        ctx['resumen_real'] = resumen_real

        # 6 indicadores técnico-financieros (#122). Función pura, división segura.
        ctx['indicadores_tecnico_financieros'] = (
            calcular_indicadores_tecnico_financieros(resumen_planeado, resumen_real)
        )

        # Sección ANS reutilizando el helper #122 (modelo de mantenimiento).
        # Defensivo: si el helper no encuentra registro devuelve sin_datos=True.
        try:
            ctx['resumen_ans'] = calcular_resumen_ans(
                linea=None, anio=anio, mes=ctx['mes'])
        except Exception:
            ctx['resumen_ans'] = {'filas': [], 'sin_datos': True}

        # Indicadores ANS propios de construcción (modelo B3) del período.
        ctx['indicadores_ans'] = list(
            IndicadorANSConstruccion.objects
            .filter(proyecto=proyecto, periodo_anio=anio, periodo_mes=ctx['mes'])
            .order_by('nombre')
        )

        # Alertas: indicadores en rojo + ANS incumplidos.
        alertas = [
            ind for ind in ctx['indicadores_tecnico_financieros']
            if ind.get('estado') == 'rojo'
        ]
        alertas += [
            f"ANS incumplido: {a.nombre} ({a.valor_actual}%)"
            for a in ctx['indicadores_ans']
            if a.estado == IndicadorANSConstruccion.Estado.INCUMPLIDO
        ]
        ctx['alertas'] = alertas
        return ctx


# ===========================================================================
# UPSERT por período — merge granular de ``datos`` JSON (Instelec#267 F.1.2)
# ===========================================================================
# Bug de origen: el POST hacía ``merged.update(res['datos'])`` a nivel RAÍZ,
# reemplazando la llave 'finv2_bd' (o una sección legacy ingreso/variables/
# fijos) COMPLETA en cada carga — si Janet cargaba Septiembre y luego Octubre,
# Octubre borraba los rubros/meses de Septiembre que no reaparecieran en el
# archivo nuevo. Mismo patrón de bug ya confirmado roto en #261 ("Reemplaza
# período, no duplica"), y EXACTAMENTE lo que #267 (Fase 1.2) pide evitar:
# "UPSERT: Reemplaza período, no duplica" — el mes/rubro que SÍ viene en el
# archivo nuevo reemplaza (upsert) su propio valor; lo que NO viene se
# PRESERVA tal cual estaba.
def _merge_seccion_mensual(existente, nuevo):
    """Merge por (concepto, mes) de una sección legacy ``{concepto: {mes: valor}}``
    (formato de ``PresupuestoConstruccionExcelImporter``: ingreso/variables/fijos).

    Por cada concepto, la recarga de UN mes reemplaza solo ese mes (upsert);
    los conceptos/meses que el archivo nuevo no trae se conservan intactos.
    """
    resultado = {
        concepto: dict(meses or {})
        for concepto, meses in (existente or {}).items()
    }
    for concepto, meses_nuevo in (nuevo or {}).items():
        meses_actual = dict(resultado.get(concepto) or {})
        meses_actual.update(meses_nuevo or {})
        resultado[concepto] = meses_actual
    return resultado


def _merge_finv2_bd(existente, nuevo):
    """Merge por (rubro, mes) del bloque ``finv2_bd`` (BD contable, #120/#267).

    Reconstruye cada rubro a partir de sus cuentas: por cuenta equivalente
    (``cta_equivalente``) mezcla el diccionario de ``meses`` — el mes que SÍ
    trae el archivo nuevo reemplaza su propio valor (upsert), el resto se
    preserva — y recalcula ``total`` de cuenta/rubro/general a partir de los
    meses ya mezclados, para que la paridad ``sum(meses) == total`` se
    mantenga íntegra después de N cargas.

    Instelec#267 A2 — dos extensiones sobre lo que dejó A1:
    - El importador plano (``PresupuestoPlanoConstruccionExcelImporter``) NO
      produce ``cuentas`` (eso es exclusivo del importador contable BD): un
      rubro nuevo llega con ``meses`` directo y una lista de ``cuentas``
      vacía. Reconstruir ``meses`` a partir de ``cuentas`` en ese caso
      BORRARÍA el dato recién puesto (lista vacía → meses vacíos) — por eso
      esta función ahora bifurca: si el rubro nuevo trae cuentas, reconcilia
      por cuenta (comportamiento original, intacto); si no, hace upsert
      directo sobre ``meses`` del rubro, sin tocar las ``cuentas``
      pre-existentes de ese rubro (por si alguna vez también recibió una
      carga contable).
    - ``filas_detalle`` (fuente de verdad de Clasificación/Ciudad/Código
      contable por fila, que A8/A5 necesitan y que el agregado ``rubros`` no
      distingue) se mezcla con el mismo criterio "reemplaza período, no
      duplica": upsert por (rubro, ciudad, año, mes).
    """
    if not nuevo:
        return dict(existente or {})
    if not existente:
        return dict(nuevo)

    rubros_actual = {
        rubro: {
            'total': info.get('total', 0.0),
            'meses': dict(info.get('meses') or {}),
            'cuentas': [dict(c) for c in (info.get('cuentas') or [])],
        }
        for rubro, info in (existente.get('rubros') or {}).items()
    }

    for rubro, info_nuevo in (nuevo.get('rubros') or {}).items():
        destino = rubros_actual.setdefault(
            rubro, {'total': 0.0, 'meses': {}, 'cuentas': []})
        cuentas_nuevo = info_nuevo.get('cuentas') or []
        if cuentas_nuevo:
            cuentas_por_cta = {
                c.get('cta_equivalente'): dict(c)
                for c in destino.get('cuentas') or []
            }
            for cuenta_nueva in cuentas_nuevo:
                cta = cuenta_nueva.get('cta_equivalente')
                actual_cta = cuentas_por_cta.get(cta) or {
                    'cta_equivalente': cta,
                    'descripcion': cuenta_nueva.get('descripcion', ''),
                    'total': 0.0,
                    'meses': {},
                }
                meses_cta = dict(actual_cta.get('meses') or {})
                meses_cta.update(cuenta_nueva.get('meses') or {})
                actual_cta['meses'] = meses_cta
                actual_cta['total'] = round(sum(meses_cta.values()), 2)
                if cuenta_nueva.get('descripcion'):
                    actual_cta['descripcion'] = cuenta_nueva['descripcion']
                cuentas_por_cta[cta] = actual_cta

            destino['cuentas'] = list(cuentas_por_cta.values())
            meses_rubro = {}
            for cuenta in destino['cuentas']:
                for mk, mv in (cuenta.get('meses') or {}).items():
                    meses_rubro[mk] = round(meses_rubro.get(mk, 0.0) + mv, 2)
            destino['meses'] = meses_rubro
        else:
            # Formato plano (#267 A2): sin cuentas — upsert directo por mes.
            meses_actual = dict(destino.get('meses') or {})
            meses_actual.update(info_nuevo.get('meses') or {})
            destino['meses'] = meses_actual

        destino['total'] = round(sum(destino['meses'].values()), 2)
        rubros_actual[rubro] = destino

    total_general = round(sum(r['total'] for r in rubros_actual.values()), 2)
    cuentas_no_clasificado = (
        rubros_actual.get(RUBRO_NO_CLASIFICADO, {}).get('cuentas') or [])
    cuentas_no_mapeadas = sorted({
        c.get('cta_equivalente') for c in cuentas_no_clasificado
        if c.get('cta_equivalente')
    })
    cuentas_count = sum(len(r.get('cuentas') or []) for r in rubros_actual.values())

    # filas_detalle (#267 A2): mismo criterio "reemplaza período, no duplica"
    # de A1, a nivel de fila cruda — upsert por (rubro, ciudad, año, mes).
    filas_existente = list(existente.get('filas_detalle') or [])
    filas_nuevo = list(nuevo.get('filas_detalle') or [])
    if filas_nuevo:
        indice = {
            (f.get('rubro'), f.get('ciudad'), f.get('anio'), f.get('mes')): f
            for f in filas_existente
        }
        for f in filas_nuevo:
            indice[(f.get('rubro'), f.get('ciudad'), f.get('anio'), f.get('mes'))] = f
        filas_detalle = list(indice.values())
    else:
        filas_detalle = filas_existente

    resultado = {
        'rubros': rubros_actual,
        'total': total_general,
        'cuentas_count': cuentas_count,
        'cuentas_no_mapeadas': cuentas_no_mapeadas,
        # Diagnóstico acumulado (no participa de ningún cálculo): filas sin
        # fecha reconocible a través de TODAS las cargas hechas hasta ahora.
        'filas_sin_mes': (
            (existente.get('filas_sin_mes') or 0)
            + (nuevo.get('filas_sin_mes') or 0)
        ),
    }
    if filas_detalle:
        resultado['filas_detalle'] = filas_detalle
    return resultado


# ===========================================================================
# KPI Cards ejecutivos por Clasificación real (Instelec#267 Fase 4, A5)
# ===========================================================================
# Ejemplo LITERAL del issue (Fase 4):
#   INGRESO: -$23.511.292.673 | COSTOS VARIABLES: +$2.813.662.061
#   COSTOS FIJOS: +$4.243.284.093 | RESULTADO: -$30.568.238.827
_CLASIFICACION_INGRESOS = 'ingresos'
_CLASIFICACION_FIJO = 'fijo'
_CLASIFICACION_VARIABLE = 'variable'


def _kpi_cards_finv2_bd(datos):
    """4 KPI cards ejecutivos agrupando ``datos['finv2_bd']['filas_detalle']``
    (A2) por Clasificación REAL de cada fila cruda.

    A propósito NO reusa ``ProyectoFinMixin._resumen_presupuesto`` /
    ``_sumar_seccion``: esos helpers agrupan por las secciones legacy
    ``ingreso``/``variables``/``fijos`` del formato de columnas-por-mes
    (``PresupuestoConstruccionExcelImporter``), que el formato plano nuevo
    (``PresupuestoPlanoConstruccionExcelImporter``, A2) NO produce — ese
    importador solo deja ``finv2_bd`` con ``rubros`` (agregado, sin
    Clasificación) + ``filas_detalle`` (crudo, CON Clasificación por fila,
    fuente de verdad para A5/A8).

        INGRESO           = SUM(valor) donde Clasificacion == 'Ingresos'
        COSTOS_FIJOS       = SUM(valor) donde Clasificacion == 'Fijo'
        COSTOS_VARIABLES   = SUM(valor) donde Clasificacion == 'Variable'
        RESULTADO          = INGRESO - (COSTOS_FIJOS + COSTOS_VARIABLES)

    La comparación se hace vía ``_fin_normalizar`` (lower + sin acentos +
    espacios colapsados) — la Clasificación se persiste TAL CUAL la tipeó el
    cliente en el Excel (``test_issue_267_a2_importador_plano.py`` confirma
    ``filas_detalle[i]['clasificacion'] == 'Fijo'``, sin normalizar), así que
    comparar por ``==`` literal sería frágil ante "FIJO"/"fijo "/variaciones.

    Edge case (presupuesto legacy sin A2, o ``finv2_bd`` ausente/vacío):
    ``filas_detalle`` no existe → 4 ceros + ``tiene_filas_detalle=False``,
    el template NO pinta las cards nuevas (no hay Clasificación real que
    agrupar, y NO hay que confundir al usuario con ceros falsos).
    """
    filas = ((datos or {}).get('finv2_bd') or {}).get('filas_detalle') or []
    ingreso = Decimal('0')
    costos_fijos = Decimal('0')
    costos_variables = Decimal('0')
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        clasificacion = _fin_normalizar(fila.get('clasificacion'))
        valor = _to_decimal(fila.get('valor'))
        if clasificacion == _CLASIFICACION_INGRESOS:
            ingreso += valor
        elif clasificacion == _CLASIFICACION_FIJO:
            costos_fijos += valor
        elif clasificacion == _CLASIFICACION_VARIABLE:
            costos_variables += valor
        # Clasificación desconocida: no debería ocurrir (A2 la valida en
        # carga contra CLASIFICACIONES_PRESUPUESTO_PLANO), pero si un dato
        # legacy trae algo distinto simplemente no suma a ninguna card —
        # nunca lanza.

    resultado = ingreso - (costos_fijos + costos_variables)
    return {
        'ingreso': ingreso,
        'costos_fijos': costos_fijos,
        'costos_variables': costos_variables,
        'resultado': resultado,
        'tiene_filas_detalle': bool(filas),
    }


# ===========================================================================
# Filtros Clasificación + Ciudad (Instelec#267 Fase 2, A8)
# ===========================================================================
# Opciones fijas del <select> Clasificación — mismo vocabulario que valida A2
# (CLASIFICACIONES_PRESUPUESTO_PLANO) y agrupa A5 (_kpi_cards_finv2_bd): el
# Excel del cliente solo puede traer una de estas 3 (o el archivo se rechaza
# en la carga), así que no hace falta derivarlas de filas_detalle.
_FILTRO_TODOS = 'todos'
_CLASIFICACION_FILTRO_OPCIONES = [
    (_CLASIFICACION_FIJO, 'Fijos'),
    (_CLASIFICACION_VARIABLE, 'Variables'),
    (_CLASIFICACION_INGRESOS, 'Ingresos'),
]


def _opciones_ciudad(filas):
    """Ciudades REALES presentes en ``filas_detalle`` (A2), orden alfabético,
    sin vacíos ni duplicados por variación de tipeo.

    Comparación normalizada (``_fin_normalizar``) para deduplicar
    "Barranquilla"/"barranquilla "/"BARRANQUILLA" como una sola opción — se
    conserva el primer valor tal cual lo tipeó el cliente para mostrarlo en
    el ``<option>``.
    """
    vistas = {}
    for f in filas:
        if not isinstance(f, dict):
            continue
        ciudad = (f.get('ciudad') or '').strip()
        if not ciudad:
            continue
        clave = _fin_normalizar(ciudad)
        vistas.setdefault(clave, ciudad)
    return sorted(vistas.values(), key=_fin_normalizar)


def _filtrar_filas_detalle(filas, clasificacion, ciudad):
    """Subconjunto de ``filas_detalle`` que matchea Clasificación Y/O Ciudad.

    ``clasificacion``/``ciudad`` vacíos o ``'todos'`` → esa dimensión no
    filtra. Comparación normalizada (acentos/mayúsculas/espacios) — mismo
    criterio que ``_kpi_cards_finv2_bd`` para no ser frágil ante cómo el
    cliente tipeó el valor en el Excel.
    """
    clas_norm = (
        _fin_normalizar(clasificacion)
        if clasificacion and clasificacion != _FILTRO_TODOS else None
    )
    ciudad_norm = (
        _fin_normalizar(ciudad)
        if ciudad and ciudad != _FILTRO_TODOS else None
    )
    if clas_norm is None and ciudad_norm is None:
        return list(filas)

    resultado = []
    for f in filas:
        if not isinstance(f, dict):
            continue
        if clas_norm is not None and _fin_normalizar(f.get('clasificacion')) != clas_norm:
            continue
        if ciudad_norm is not None and _fin_normalizar(f.get('ciudad')) != ciudad_norm:
            continue
        resultado.append(f)
    return resultado


def _datos_filtrados_por_clasificacion_ciudad(datos, clasificacion, ciudad):
    """Reconstruye ``datos`` con ``finv2_bd`` recalculado SOLO sobre las filas
    de ``filas_detalle`` (A2) que pasan el filtro (A8) — alimenta la matriz
    (Fase 2) y la tabla de Rubros (Fase 3) ya filtradas.

    Reusa ``_construir_finv2_bd_desde_filas_planas`` (el mismo agregador del
    importador) para no duplicar la suma por rubro/mes.

    Sin ``filas_detalle`` (presupuesto legacy, formato columnas-por-mes) o
    sin filtro activo → devuelve ``datos`` intacto: Clasificación/Ciudad no
    existen por fila en el legacy, así que el filtro simplemente no aplica
    (nunca rompe la vista).
    """
    filas = ((datos or {}).get('finv2_bd') or {}).get('filas_detalle') or []
    if not filas:
        return datos
    sin_filtro = (
        (not clasificacion or clasificacion == _FILTRO_TODOS)
        and (not ciudad or ciudad == _FILTRO_TODOS)
    )
    if sin_filtro:
        return datos

    filas_filtradas = _filtrar_filas_detalle(filas, clasificacion, ciudad)
    resultado = dict(datos)
    resultado['finv2_bd'] = _construir_finv2_bd_desde_filas_planas(filas_filtradas)
    return resultado


def _merge_presupuesto_datos(existente, nuevo):
    """UPSERT por período (Instelec#267 Fase 1.2): reemplaza SOLO lo que el
    archivo nuevo trae (rubro/concepto + mes), preserva el resto tal cual.

    Reemplaza el ``merged.update(res['datos'])`` a nivel raíz que causaba el
    bug de origen (colapsaba 'finv2_bd', o una sección legacy completa, en
    cada carga).
    """
    merged = dict(existente or {})
    for key, valor_nuevo in (nuevo or {}).items():
        if key == 'finv2_bd':
            merged['finv2_bd'] = _merge_finv2_bd(merged.get('finv2_bd'), valor_nuevo)
        elif key in ('ingreso', 'variables', 'fijos') and isinstance(valor_nuevo, dict):
            merged[key] = _merge_seccion_mensual(merged.get(key), valor_nuevo)
        else:
            merged[key] = valor_nuevo
    return merged


# ---------------------------------------------------------------------------
# Historial de cargas (Instelec#267 Fase 1.3, A3) — helpers de lectura de
# ``res['datos']`` para poblar ``HistorialCargaPresupuestoConstruccion``.
# ---------------------------------------------------------------------------
def _mes_unico_desde_datos(datos):
    """Mes único del archivo importado, o ``None``.

    Solo el formato plano (A2) trae ``finv2_bd['filas_detalle']`` con un
    ``mes`` por fila — si TODAS las filas comparten el mismo mes, ese es el
    período de la carga (caso típico: Janet sube 1 archivo/mes). Si el
    archivo mezcla meses, o es un formato legacy sin ``filas_detalle``
    ('contable'/'presupuesto' de columnas por mes, que cubren el año
    completo), no hay un mes puntual que reportar → ``None``.
    """
    if not isinstance(datos, dict):
        return None
    filas = (datos.get('finv2_bd') or {}).get('filas_detalle') or []
    meses = {f.get('mes') for f in filas if isinstance(f, dict) and f.get('mes')}
    return meses.pop() if len(meses) == 1 else None


def _valor_total_desde_datos(datos):
    """Valor total de la carga, para el registro de historial.

    - Formato ``finv2_bd`` (A2 plano / #120 contable): usa el ``total`` que el
      importer ya calculó.
    - Formato legacy (columnas por mes → ingreso/variables/fijos): suma las 3
      secciones (mismo criterio que ``ProyectoFinMixin._sumar_seccion``).
    Navega defensivamente — nunca lanza, nunca devuelve ``None``.
    """
    if not isinstance(datos, dict):
        return Decimal('0')
    finv2_bd = datos.get('finv2_bd')
    if isinstance(finv2_bd, dict) and finv2_bd.get('total') is not None:
        return _to_decimal(finv2_bd['total'])
    total = Decimal('0')
    for key in ('ingreso', 'variables', 'fijos'):
        seccion = datos.get(key)
        if isinstance(seccion, dict):
            for v in seccion.values():
                if isinstance(v, dict):
                    for vv in v.values():
                        total += _to_decimal(vv)
                else:
                    total += _to_decimal(v)
    return total


# ===========================================================================
# 2. PRESUPUESTO PLANEADO
# ===========================================================================
class PresupuestoPlaneadoConstruccionView(ProyectoFinMixin, TemplateView):
    """Presupuesto PLANEADO del año (estructura JSON + resumen) (#123 Fase 2.2)."""
    template_name = 'construccion/financiero_presupuesto_planeado.html'
    active_subtab = 'presupuesto_planeado'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto, anio = ctx['proyecto'], ctx['anio']
        presupuesto = (
            PresupuestoDetalladoConstruccion.objects
            .filter(proyecto=proyecto, anio=anio,
                    tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO)
            .first()
        )
        ctx['tipo'] = 'PLANEADO'
        ctx['presupuesto'] = presupuesto
        datos = presupuesto.datos if presupuesto else {}
        ctx['datos'] = datos
        ctx['sin_datos'] = presupuesto is None
        ctx['resumen'] = self._resumen_presupuesto(
            proyecto, anio, PresupuestoDetalladoConstruccion.Tipo.PLANEADO)

        # A8 (#267 Fase 2): filtros Clasificación + Ciudad, leídos de
        # ?clasificacion=&ciudad=, aplicados sobre filas_detalle (A2) ANTES
        # de construir la matriz (Fase 2) y la tabla de Rubros (Fase 3).
        # KPI cards (A5, Fase 4) NO se filtran — el issue no lo pide ahí — y
        # el gate ``tiene_datos_bd`` tampoco: debe reflejar si HAY datos
        # cargados, no si el filtro elegido tiene resultados (un filtro sin
        # matches no puede colapsar toda la pestaña a "sin datos cargados").
        filas_sin_filtrar = ((datos or {}).get('finv2_bd') or {}).get('filas_detalle') or []
        clasificacion_sel = (self.request.GET.get('clasificacion') or _FILTRO_TODOS).strip()
        clasificacion_sel = _fin_normalizar(clasificacion_sel) or _FILTRO_TODOS
        ciudad_sel = (self.request.GET.get('ciudad') or _FILTRO_TODOS).strip()
        ctx['clasificaciones_disponibles'] = (
            _CLASIFICACION_FILTRO_OPCIONES if filas_sin_filtrar else []
        )
        ctx['ciudades_disponibles'] = _opciones_ciudad(filas_sin_filtrar)
        ctx['clasificacion_sel'] = clasificacion_sel
        ctx['ciudad_sel'] = ciudad_sel
        ctx['filtro_activo'] = bool(filas_sin_filtrar) and (
            clasificacion_sel != _FILTRO_TODOS
            or _fin_normalizar(ciudad_sel) != _FILTRO_TODOS
        )
        datos_filtrados = _datos_filtrados_por_clasificacion_ciudad(
            datos, clasificacion_sel, ciudad_sel)

        # Rubros del contable (espejo #120): cuando la carga fue una BD contable,
        # los datos viven en datos['finv2_bd'] y se muestran agrupados por rubro.
        # (A8) Se construyen sobre datos_filtrados — matrix_rows/rubro_rows
        # reflejan el filtro elegido, tiene_datos_bd usa el dato SIN filtrar.
        rubro_rows_sin_filtrar, _rubro_total_sin_filtrar = build_rubro_display_rows(datos)
        ctx['tiene_datos_bd'] = bool(rubro_rows_sin_filtrar)
        rubro_rows, rubro_total = build_rubro_display_rows(datos_filtrados)
        ctx['rubro_rows'] = rubro_rows
        ctx['rubro_total'] = rubro_total
        ctx['matrix_vacia_por_filtro'] = (
            ctx['filtro_activo'] and ctx['tiene_datos_bd'] and not rubro_rows
        )
        # A5 (#267 Fase 4): 4 KPI cards ejecutivos por Clasificación real
        # (Ingreso/Costos Fijos/Costos Variables/Resultado), fuente de verdad
        # filas_detalle de A2 — independiente de rubro_rows/tiene_datos_bd,
        # SIEMPRE sobre el total sin filtrar (Fase 4 del issue no pide filtro).
        ctx['kpi_cards'] = _kpi_cards_finv2_bd(datos)
        # A3 (#120): vista bi-modal (matriz 12 meses + filtro mes), espejo de
        # Mantenimiento, reusando el partial compartido. (A8) Alimentada con
        # datos_filtrados para que la matriz también respete Clasificación/Ciudad.
        ctx.update(self._bimodal_context(datos_filtrados))
        # A3 (#267 Fase 1.3): historial de cargas del proyecto — NO se filtra
        # por año/tipo: Janet carga 1 vez/mes y el historial debe mostrar la
        # tendencia entre períodos, no solo el año en pantalla.
        ctx['historial_cargas'] = (
            HistorialCargaPresupuestoConstruccion.objects
            .filter(proyecto=proyecto)
            .select_related('usuario')
            .order_by('-fecha')[:10]
        )
        return ctx

    def post(self, request, *args, **kwargs):
        """Carga BD contable / presupuesto desde Excel (#123 Fase 4, espejo #120).

        El form (``_financiero_cargar_bd.html``) postea ``action=cargar_bd`` +
        ``archivo`` + ``anio``. Detecta el formato, corre el importer adecuado
        y persiste el resultado en ``PresupuestoDetalladoConstruccion.datos``.
        """
        from django.contrib import messages
        from django.shortcuts import redirect

        proyecto = get_object_or_404(ProyectoConstruccion, pk=kwargs['proyecto_id'])
        try:
            anio = int(request.POST.get('anio') or date.today().year)
        except (ValueError, TypeError):
            anio = date.today().year
        destino = f'{request.path}?anio={anio}&tab=cargar'

        archivo = request.FILES.get('archivo')
        if not archivo:
            # Sin archivo no hay intento de carga real: no genera registro de
            # historial (es una validación de formulario, no un evento auditable).
            messages.error(request, 'Seleccione un archivo .xlsx.')
            return redirect(destino)

        nombre_archivo = (getattr(archivo, 'name', '') or '')[:255]
        usuario = request.user if request.user.is_authenticated else None

        formato = detect_excel_format_construccion(archivo)
        try:
            archivo.seek(0)
        except Exception:
            pass

        if formato == 'contable':
            res = ContableConstruccionExcelImporter().procesar(archivo)
        elif formato == 'presupuesto':
            res = PresupuestoConstruccionExcelImporter().procesar(archivo)
        elif formato == 'presupuesto_plano':
            # Instelec#267 A2: formato plano del cliente
            # (Tipo|Proyecto|Rubro|Clasificacion|Valor|mes|año|ciudad).
            res = PresupuestoPlanoConstruccionExcelImporter().procesar(archivo)
        else:
            mensaje_formato_no_reconocido = (
                'Formato no reconocido. Suba la Base de Datos contable (hoja BD), '
                'el Presupuesto (columnas de mes) o el Presupuesto plano '
                '(Tipo|Proyecto|Rubro|Clasificacion|Valor|mes|año|ciudad).'
            )
            res = {
                'exito': False, 'error': mensaje_formato_no_reconocido,
                'advertencia': None, 'mensaje': None, 'datos': None, 'filas': 0,
            }

        if res.get('exito'):
            obj, _creado = PresupuestoDetalladoConstruccion.objects.get_or_create(
                proyecto=proyecto, anio=anio,
                tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
                defaults={'datos': {}},
            )
            obj.datos = _merge_presupuesto_datos(obj.datos, res.get('datos'))
            obj.save(update_fields=['datos', 'updated_at'])
            messages.success(request, res.get('mensaje') or 'Importación completada.')
            if res.get('advertencia'):
                messages.warning(request, res['advertencia'])
            # A3 (#267 Fase 1.3): registrar la carga exitosa en el historial.
            HistorialCargaPresupuestoConstruccion.objects.create(
                proyecto=proyecto,
                anio=anio,
                mes=_mes_unico_desde_datos(res.get('datos')),
                usuario=usuario,
                filas_procesadas=res.get('filas') or 0,
                valor_total=_valor_total_desde_datos(res.get('datos')),
                estado=HistorialCargaPresupuestoConstruccion.Estado.PROCESADA,
                archivo_nombre=nombre_archivo,
            )
        else:
            messages.error(request, res.get('error') or 'No se pudo procesar el archivo.')
            # A3 (#267 Fase 1.3): registrar la carga fallida CON detalle — el
            # detalle de errores sobrevive aunque el mensaje flash de Django
            # desaparezca tras el próximo request (el historial es la fuente
            # persistente para que Janet/soporte vean qué pasó).
            HistorialCargaPresupuestoConstruccion.objects.create(
                proyecto=proyecto,
                anio=anio,
                mes=None,
                usuario=usuario,
                filas_procesadas=0,
                valor_total=Decimal('0'),
                estado=HistorialCargaPresupuestoConstruccion.Estado.ERROR,
                archivo_nombre=nombre_archivo,
                detalle_errores={
                    'error': res.get('error'),
                    'advertencia': res.get('advertencia'),
                },
            )
        return redirect(destino)


# ===========================================================================
# 3. PRESUPUESTO REAL
# ===========================================================================
class PresupuestoRealConstruccionView(ProyectoFinMixin, TemplateView):
    """Presupuesto REAL del año (ejecutado) (#123 Fase 2.3)."""
    template_name = 'construccion/financiero_presupuesto_real.html'
    active_subtab = 'presupuesto_real'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto, anio = ctx['proyecto'], ctx['anio']
        presupuesto = (
            PresupuestoDetalladoConstruccion.objects
            .filter(proyecto=proyecto, anio=anio,
                    tipo=PresupuestoDetalladoConstruccion.Tipo.REAL)
            .first()
        )
        ctx['tipo'] = 'REAL'
        ctx['presupuesto'] = presupuesto
        ctx['datos'] = presupuesto.datos if presupuesto else {}
        ctx['sin_datos'] = presupuesto is None
        ctx['resumen'] = self._resumen_presupuesto(
            proyecto, anio, PresupuestoDetalladoConstruccion.Tipo.REAL)
        # A5 (#267 Fase 4): mismo partial compartido con Planeado — si algún
        # día el REAL también recibe finv2_bd/filas_detalle, las cards ya
        # están conectadas; hoy con datos legacy simplemente no se pintan
        # (tiene_filas_detalle=False).
        ctx['kpi_cards'] = _kpi_cards_finv2_bd(ctx['datos'])
        # Total ejecutado derivado de costos registrados (cruce con CostosConstruccion).
        total_costos = Decimal('0')
        for c in CostosConstruccion.objects.filter(
                proyecto=proyecto, fecha__year=anio):
            total_costos += _to_decimal(c.costo_total)
        ctx['total_costos_registrados'] = total_costos
        return ctx


# ===========================================================================
# 4. NÓMINA
# ===========================================================================
class NominaConstruccionView(ProyectoFinMixin, TemplateView):
    """Nómina / personal administrativo del proyecto (#123 Fase 2.4).

    No existe (aún) un modelo PersonalAdministrativoConstruccion (fuera del scope
    de B3). Se usa el desglose de costos tipo MANO_OBRA como proxy de nómina del
    período, agrupando por concepto. Versión 1.0 funcional; el CRUD de personal
    queda diferido (no es de los 5 modelos de B3).
    """
    template_name = 'construccion/financiero_nomina.html'
    active_subtab = 'nomina'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto, anio = ctx['proyecto'], ctx['anio']
        costos_mano_obra = list(
            CostosConstruccion.objects
            .filter(proyecto=proyecto, fecha__year=anio,
                    tipo_recurso=CostosConstruccion.TipoRecurso.MANO_OBRA)
            .order_by('-fecha')
        )
        total_nomina = sum((_to_decimal(c.costo_total) for c in costos_mano_obra),
                           Decimal('0'))
        ctx['costos_mano_obra'] = costos_mano_obra
        ctx['total_nomina'] = total_nomina
        ctx['sin_datos'] = not costos_mano_obra
        return ctx


# ===========================================================================
# 5. COSTOS DETALLADO
# ===========================================================================
class CostosDetalladoConstruccionView(ProyectoFinMixin, TemplateView):
    """Tabla de costos ejecutados con filtro por tipo de recurso (#123 Fase 2.5)."""
    template_name = 'construccion/financiero_costos_detallado.html'
    active_subtab = 'costos'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto, anio = ctx['proyecto'], ctx['anio']
        qs = (
            CostosConstruccion.objects
            .filter(proyecto=proyecto, fecha__year=anio)
            .select_related('actividad')
            .order_by('-fecha')
        )
        # Filtro opcional por tipo de recurso (?tipo_recurso=MATERIAL).
        tipo_recurso = self.request.GET.get('tipo_recurso')
        validos = {c[0] for c in CostosConstruccion.TipoRecurso.choices}
        if tipo_recurso in validos:
            qs = qs.filter(tipo_recurso=tipo_recurso)
            ctx['filtro_tipo_recurso'] = tipo_recurso

        costos = list(qs)
        # Totales por tipo de recurso (para el resumen superior de la tabla).
        totales_por_tipo = {}
        total_general = Decimal('0')
        for c in costos:
            valor = _to_decimal(c.costo_total)
            totales_por_tipo[c.tipo_recurso] = (
                totales_por_tipo.get(c.tipo_recurso, Decimal('0')) + valor
            )
            total_general += valor

        ctx['costos'] = costos
        ctx['totales_por_tipo'] = totales_por_tipo
        ctx['total_general'] = total_general
        ctx['tipos_recurso'] = CostosConstruccion.TipoRecurso.choices
        ctx['sin_datos'] = not costos
        return ctx


# ===========================================================================
# 6. FACTURACIÓN
# ===========================================================================
class FacturacionConstruccionView(ProyectoFinMixin, TemplateView):
    """Gestión de facturas + seguimiento de pagos (#123 Fase 2.6)."""
    template_name = 'construccion/financiero_facturacion.html'
    active_subtab = 'facturacion'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = ctx['proyecto']
        facturas = list(
            FacturacionConstruccion.objects
            .filter(proyecto=proyecto)
            .order_by('-fecha_emision')
        )
        total_facturado = sum(
            (_to_decimal(f.monto_facturado) for f in facturas), Decimal('0'))
        total_pagado = sum(
            (_to_decimal(f.monto_pagado) for f in facturas), Decimal('0'))
        ctx['facturas'] = facturas
        ctx['total_facturado'] = total_facturado
        ctx['total_pagado'] = total_pagado
        ctx['saldo_total'] = total_facturado - total_pagado
        ctx['estados'] = FacturacionConstruccion.Estado.choices
        ctx['sin_datos'] = not facturas
        return ctx
