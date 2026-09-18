"""PDF ejecutivo del dashboard financiero integrado (#246 Sprint D).

Consume el ``payload`` armado por
``views_finv2_dashboard_exportar._construir_payload_dashboard`` -- NUNCA
recalcula indicadores/tendencia/desglose (eso ya lo hace
``CargaFinancieraView``, Sprint B de #246) ni la integración
nómina/gastos/ingresos/clientes (eso lo hace
``construir_contexto_dashboard_integrado``, B3). Este módulo solo
formatea ese dict a HTML y lo convierte a PDF con WeasyPrint (ya declarado
en ``requirements/base.txt``, mismo patrón que ``apps/ambiental/reports.py``
y ``apps/financiero/views_finv2_ingresos.py``).
"""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

ZERO = Decimal("0.00")


def _money(valor: Any) -> str:
    if valor is None:
        return "--"
    try:
        return f"${Decimal(valor).quantize(Decimal('0.01')):,.2f}"
    except Exception:
        return str(valor)


def _pct(valor: Any) -> str:
    if valor is None:
        return "--"
    try:
        return f"{Decimal(valor).quantize(Decimal('0.01'))}%"
    except Exception:
        return str(valor)


def _valor_indicador(indicador: dict) -> str:
    if indicador.get("sin_base") or indicador.get("valor") is None:
        return "Sin base comparable"
    if indicador.get("unidad") == "%":
        return _pct(indicador["valor"])
    return _money(indicador["valor"])


def _construir_recomendaciones(payload: dict) -> list[str]:
    """Recomendaciones derivadas de las alertas ya calculadas -- no inventa
    reglas de negocio nuevas, solo traduce cada alerta existente a una
    acción sugerida en lenguaje de negocio."""
    recomendaciones: list[str] = []
    for indicador in payload.get("indicadores") or []:
        if indicador.get("alerta") and indicador.get("causa"):
            recomendaciones.append(indicador["causa"])
    gastos = payload.get("integracion_gastos") or {}
    if gastos.get("con_datos") and gastos.get("pendiente_pago", ZERO) > ZERO:
        recomendaciones.append(
            f"Hay {_money(gastos['pendiente_pago'])} en facturas de gasto "
            "pendientes de pago en el período -- priorizar su liquidación."
        )
    if not recomendaciones:
        recomendaciones.append(
            "Sin alertas activas en el período: el gasto ejecutado está dentro "
            "de lo presupuestado y no hay pendientes críticos identificados."
        )
    return recomendaciones


def generar_pdf_ejecutivo(payload: dict) -> bytes:
    """Portada, período/proyecto, 6 indicadores, alertas, tendencia,
    recomendaciones y firma -- versión 1.0 completa (Sprint D)."""
    from weasyprint import HTML

    proyecto = payload.get("proyecto")
    proyecto_nombre = escape(str(proyecto)) if proyecto else "Todos los proyectos"
    periodo = f"{payload['mes']:02d}/{payload['anio']}"
    generado_en = payload.get("generado_en")
    usuario = payload.get("usuario")

    indicadores = payload.get("indicadores") or []
    filas_indicadores = (
        "".join(
            f"<tr class='{'alerta' if i.get('alerta') else ''}'>"
            f"<td>{escape(str(i.get('nombre', '')))}</td>"
            f"<td>{escape(_valor_indicador(i))}</td>"
            f"<td>{'⚠ Alerta' if i.get('alerta') else 'OK'}</td>"
            "</tr>"
            for i in indicadores
        )
        or "<tr><td colspan='3'>Sin indicadores calculados: el período no tiene carga financiera vigente.</td></tr>"
    )

    alertas = [i for i in indicadores if i.get("alerta")]
    filas_alertas = (
        "".join(
            f"<li>{escape(str(i.get('nombre', '')))}: {escape(str(i.get('causa') or 'Ver detalle en el dashboard.'))}</li>"
            for i in alertas
        )
        or "<li>No hay alertas activas en el período.</li>"
    )

    tendencia = payload.get("tendencia_6_meses") or []
    filas_tendencia = (
        "".join(
            f"<tr><td>{escape(str(t['periodo']))}</td><td>{_money(t['costo_real'])}</td>"
            f"<td>{_money(t['costo_presupuestado'])}</td></tr>"
            for t in tendencia
        )
        or "<tr><td colspan='3'>Sin histórico de cargas previas para este proyecto.</td></tr>"
    )

    recomendaciones = "".join(f"<li>{escape(r)}</li>" for r in _construir_recomendaciones(payload))

    resumen_totales = payload.get("resumen_totales") or {}

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Reporte ejecutivo financiero</title>
<style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #1f2937; font-size: 11pt; }}
  h1 {{ color: #111827; font-size: 22pt; margin-bottom: 0; }}
  h2 {{ color: #1e40af; font-size: 14pt; margin-top: 24px; border-bottom: 1px solid #d1d5db; padding-bottom: 4px; }}
  .subtitulo {{ color: #6b7280; font-size: 12pt; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #e5e7eb; font-size: 10pt; }}
  th {{ background: #f3f4f6; }}
  tr.alerta td {{ color: #b91c1c; font-weight: bold; }}
  .resumen {{ display: flex; gap: 24px; margin-top: 12px; }}
  .resumen div {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 16px; }}
  .firma {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #d1d5db; color: #6b7280; font-size: 9pt; }}
  ul {{ margin: 8px 0; padding-left: 20px; }}
</style>
</head>
<body>
  <h1>Reporte Ejecutivo Financiero</h1>
  <p class="subtitulo">{proyecto_nombre} &middot; Período {periodo}</p>

  <div class="resumen">
    <div><strong>Costo real</strong><br>{_money(resumen_totales.get("costo_real"))}</div>
    <div><strong>Costo presupuestado</strong><br>{_money(resumen_totales.get("costo_presupuestado"))}</div>
  </div>

  <h2>Indicadores (6)</h2>
  <table>
    <thead><tr><th>Indicador</th><th>Valor</th><th>Estado</th></tr></thead>
    <tbody>{filas_indicadores}</tbody>
  </table>

  <h2>Alertas</h2>
  <ul>{filas_alertas}</ul>

  <h2>Tendencia (últimos períodos)</h2>
  <table>
    <thead><tr><th>Período</th><th>Costo real</th><th>Costo presupuestado</th></tr></thead>
    <tbody>{filas_tendencia}</tbody>
  </table>

  <h2>Recomendaciones</h2>
  <ul>{recomendaciones}</ul>

  <div class="firma">
    Generado automáticamente por el sistema financiero Instelec (Indunnova S.A.S.)
    {f"el {generado_en:%d/%m/%Y %H:%M}" if generado_en else ""}
    {f"por {escape(str(usuario))}" if usuario else ""}.
    Este documento respeta los filtros de período/proyecto/tipo/centro de costo
    activos al momento de la descarga.
  </div>
</body>
</html>"""

    return HTML(string=html).write_pdf()
