"""
Dashboard financiero v2 — mixin de indicadores técnico-financieros / ANS.

B2 (#122). Engancha los 6 KPIs tecnico-financieros + la seccion ANS al
``DashboardFinancieroView`` existente SIN tocar su ``get_context_data``.

El mixin es la **PRIMERA base** de la CBV
(``class DashboardFinancieroView(DashboardFinancieroMixinV2, ...)``), por lo
que su ``get_context_data`` corre primero: llama a ``super()`` (que arma
``resumen_planeado`` / ``resumen_real`` / filtros) y luego inyecta:

- ``indicadores_tecnico_financieros``: list[dict] (6 KPIs).
- ``indicadores_ans``: list[dict] (9 filas ANS).
- ``resumen_ans``: dict (total ponderado + estado general).

Reutiliza ``apps.indicadores.models_b4_mantenimiento_detallado.IndicadorANSContractual``
via las funciones puras de ``indicadores_finv2.py``. NO crea modelos.
"""
from .indicadores_finv2 import (
    calcular_indicadores_tecnico_financieros,
    calcular_resumen_ans,
)


class DashboardFinancieroMixinV2:
    """
    Mixin que agrega los indicadores v2 (#122) al contexto del dashboard.

    Debe ir como PRIMERA base de ``DashboardFinancieroView`` para que su
    ``get_context_data`` ejecute y, via ``super()``, deje correr el resto del
    MRO (que construye ``resumen_planeado``/``resumen_real`` y los filtros).
    """

    def _calcular_indicadores_tecnico_financieros(self, resumen_planeado, resumen_real, extras=None):
        """Wrapper de instancia sobre la funcion pura (testeable / sobre-escribible)."""
        return calcular_indicadores_tecnico_financieros(
            resumen_planeado, resumen_real, extras=extras
        )

    def _calcular_indicadores_ans(self, linea=None, anio=None, mes=None):
        """Wrapper de instancia sobre la funcion pura del resumen ANS."""
        return calcular_resumen_ans(linea=linea, anio=anio, mes=mes)

    def _linea_de_contrato(self, context):
        """
        Deriva la ``Linea`` para filtrar ANS a partir del contrato seleccionado.

        El dashboard filtra por contrato (no por linea). Los registros ANS
        ``IndicadorANSContractual`` se llevan por linea (o globales, linea NULL).
        Tomamos la primera linea activa del contrato; si no hay contrato o no
        tiene lineas, devolvemos None -> ANS global (linea NULL) o "sin datos".
        """
        contrato = context.get("contrato_seleccionado")
        if contrato is None:
            return None
        # Relacion contrato -> lineas (FK ``contrato`` en Linea).
        try:
            lineas_rel = getattr(contrato, "linea_set", None)
            if lineas_rel is None:
                lineas_rel = getattr(contrato, "lineas", None)
            if lineas_rel is None:
                return None
            return lineas_rel.filter(activa=True).first() or lineas_rel.first()
        except Exception:
            return None

    def get_context_data(self, **kwargs):
        # Como mixin de PRIMERA base: dejar correr el resto del MRO primero
        # (DashboardFinancieroView arma resumen_planeado / resumen_real / filtros).
        context = super().get_context_data(**kwargs)

        resumen_planeado = context.get("resumen_planeado") or {}
        resumen_real = context.get("resumen_real") or {}
        anio = context.get("anio")
        mes = context.get("mes")
        # mes == 0 en el dashboard significa "todo el año" -> ANS sin filtro de mes.
        mes_ans = mes if mes else None

        # 6 KPIs tecnico-financieros sobre el resumen que ya armo la vista base.
        context["indicadores_tecnico_financieros"] = self._calcular_indicadores_tecnico_financieros(
            resumen_planeado, resumen_real
        )

        # Seccion ANS reutilizando IndicadorANSContractual (B4).
        linea = self._linea_de_contrato(context)
        resumen_ans = self._calcular_indicadores_ans(linea=linea, anio=anio, mes=mes_ans)
        context["resumen_ans"] = resumen_ans
        context["indicadores_ans"] = resumen_ans.get("filas", [])

        return context
