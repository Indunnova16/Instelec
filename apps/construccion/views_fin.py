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
``SubModuloRequiredMixin`` con ``required_submodulo = 'FINANCIERO'`` sin riesgo de
403 indebido (los roles admin pasan vía RoleRequiredMixin de todos modos).

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

from apps.financiero.indicadores_finv2 import (
    calcular_indicadores_tecnico_financieros,
    calcular_resumen_ans,
)

from .models import ProyectoConstruccion
from .models_fin import (
    PresupuestoDetalladoConstruccion,
    CostosConstruccion,
    FacturacionConstruccion,
    IndicadorANSConstruccion,
)
from .importers import (
    ContableConstruccionExcelImporter,
    PresupuestoConstruccionExcelImporter,
    detect_excel_format_construccion,
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
        ctx['datos'] = presupuesto.datos if presupuesto else {}
        ctx['sin_datos'] = presupuesto is None
        ctx['resumen'] = self._resumen_presupuesto(
            proyecto, anio, PresupuestoDetalladoConstruccion.Tipo.PLANEADO)
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
            messages.error(request, 'Seleccione un archivo .xlsx.')
            return redirect(destino)

        formato = detect_excel_format_construccion(archivo)
        try:
            archivo.seek(0)
        except Exception:
            pass

        if formato == 'contable':
            res = ContableConstruccionExcelImporter().procesar(archivo)
        elif formato == 'presupuesto':
            res = PresupuestoConstruccionExcelImporter().procesar(archivo)
        else:
            messages.error(
                request,
                'Formato no reconocido. Suba la Base de Datos contable (hoja BD) '
                'o el Presupuesto (columnas de mes).',
            )
            return redirect(destino)

        if res.get('exito'):
            obj, _creado = PresupuestoDetalladoConstruccion.objects.get_or_create(
                proyecto=proyecto, anio=anio,
                tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
                defaults={'datos': {}},
            )
            merged = dict(obj.datos or {})
            merged.update(res.get('datos') or {})
            obj.datos = merged
            obj.save(update_fields=['datos', 'updated_at'])
            messages.success(request, res.get('mensaje') or 'Importación completada.')
            if res.get('advertencia'):
                messages.warning(request, res['advertencia'])
        else:
            messages.error(request, res.get('error') or 'No se pudo procesar el archivo.')
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
