"""3 views de descarga del dashboard financiero integrado (#246 Sprint D).

Reutilizan, sin reimplementar:
- ``construir_contexto_dashboard_integrado`` (B3, service contract Kaizen
  #47) para nómina/gastos/ingresos/clientes.
- Los ``classmethod`` de ``CargaFinancieraView`` (Sprint B de #246, ya en
  ``main``) para los 6 indicadores/desglose de costos/tendencia -- y sus
  métodos de instancia ``_periodo()``/``_proyecto_seleccionado()`` para leer
  los MISMOS filtros GET (período/proyecto/tipo/centro de costo) que el
  dashboard, de forma que la descarga respete exactamente lo que el usuario
  tiene filtrado en pantalla.

RBAC de descarga (matriz de negocio del issue #246 Sprint D -- ver
``BLUEPRINT.md`` §B4 y el docstring de la migración
``core/migrations/0008_seed_fin_facturas_gastos_y_roles_248.py``, que deja
explícito que esta restricción MÁS FINA por tipo de reporte es
responsabilidad de B4, no de la hoja RBAC genérica por submódulo):

- Supervisor: sin descarga (ni botón ni endpoint).
- Coordinador: lectura del dashboard, sin descarga.
- Contador (rol sembrado por S1): solo Excel (ve costos).
- Gerente Financiero (rol sembrado por S1) / Admin: los 3 formatos.
- Superusuario: los 3 formatos.
- Cualquier otro rol no listado: sin descarga (deny-by-default).

Esta matriz es INTENCIONALMENTE más estricta que el nivel de acceso
genérico (``ver``/``ver_editar``) de ``RoleModuloPermiso`` sobre
``FIN_HOMOLOGACION`` -- p.ej. ``coordinador``/``director`` tienen
``ver_editar`` ahí (heredado del seed legacy, #247) pero el negocio pidió
explícitamente que NO puedan descargar estos 3 reportes ejecutivos.
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.views import View

from apps.core.models_roles import RoleModuloPermiso
from apps.core.permissions import SUBMODULO_FIN_HOMOLOGACION, user_nivel_acceso_submodulo

from .models_finv2_carga import CargaFinanciera
from .reports_finv2_detallado_excel import generar_excel_detallado
from .reports_finv2_ejecutivo_pdf import generar_pdf_ejecutivo
from .reports_finv2_stakeholders_ppt import generar_ppt_stakeholders
from .services_finv2_indicadores_integracion import construir_contexto_dashboard_integrado
from .views_finv2_carga import CargaFinancieraView

# Regla de negocio de B4 -- ver docstring del módulo. `rol codigo -> formatos
# permitidos`. Ausencia de un rol en este dict == sin descarga (deny-default).
FORMATOS_DESCARGA_POR_ROL = {
    "admin": {"pdf", "excel", "ppt"},
    "admin_general": {"pdf", "excel", "ppt"},
    "gerente_financiero": {"pdf", "excel", "ppt"},
    "contador": {"excel"},
}

_CONTEXTO_VACIO = {
    "integracion_nomina": {
        "con_datos": False,
        "costo_nomina": 0,
        "horas_trabajadas": 0,
        "cantidad_producciones": 0,
        "producciones": [],
    },
    "integracion_gastos": {
        "con_datos": False,
        "total": 0,
        "pendiente_pago": 0,
        "cantidad": 0,
        "detalle": [],
    },
    "integracion_ingresos": {
        "con_datos": False,
        "total": 0,
        "cobrado": 0,
        "cantidad": 0,
        "detalle": [],
    },
    "integracion_clientes": {
        "con_datos": False,
        "activos_total": 0,
        "facturados_periodo": 0,
        "detalle": [],
    },
}


def formatos_permitidos(user) -> set[str]:
    """Formatos que ``user`` puede descargar del dashboard financiero.

    Expuesta como función de módulo (no solo interna a la vista) para que
    el template ``carga_financiera.html`` y esta vista compartan la MISMA
    fuente de verdad en vez de duplicar la lista de roles en dos lugares
    (se usa vía un filtro inline sencillo en el template, ver comentario
    ahí referenciando este dict)."""
    if getattr(user, "is_superuser", False):
        return {"pdf", "excel", "ppt"}
    return set(FORMATOS_DESCARGA_POR_ROL.get(getattr(user, "rol", "") or "", set()))


class _DashboardExportarBaseView(LoginRequiredMixin, View):
    """Base común a los 3 formatos: resuelve el payload UNA vez y delega en
    ``_generar_response`` para el formato concreto."""

    formato: str = ""  # 'pdf' | 'excel' | 'ppt', override en subclase
    content_type: str = ""
    extension: str = ""

    def get(self, request, *args, **kwargs):
        if self.formato not in formatos_permitidos(request.user):
            return HttpResponseForbidden(
                "No tiene autorización para descargar este reporte. "
                "Contacte a un Gerente Financiero o Administrador."
            )

        nivel = user_nivel_acceso_submodulo(request.user, SUBMODULO_FIN_HOMOLOGACION)
        if nivel == RoleModuloPermiso.SIN_ACCESO:
            return HttpResponseForbidden("No tiene acceso al módulo Financiero.")

        payload = self._construir_payload(request)
        contenido = self._generar(payload)
        nombre_proyecto = str(payload["proyecto"]) if payload["proyecto"] else "Todos"
        nombre_archivo = (
            f"Reporte_{self.formato}_{nombre_proyecto}_{payload['anio']}{payload['mes']:02d}"
            f".{self.extension}"
        ).replace(" ", "_")
        response = HttpResponse(contenido, content_type=self.content_type)
        response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
        return response

    @staticmethod
    def _construir_payload(request) -> dict:
        # Reusa los métodos de instancia de CargaFinancieraView para leer
        # EXACTAMENTE los mismos filtros GET que el dashboard, sin
        # reimplementar el parseo de período/proyecto/tipo/centro de costo.
        helper = CargaFinancieraView()
        helper.request = request
        anio, mes, periodo_valido = helper._periodo()
        proyecto = helper._proyecto_seleccionado()
        tipo_operacional, centro_costo = helper._filtros()

        carga = None
        if proyecto and periodo_valido:
            carga = CargaFinanciera.objects.filter(
                proyecto=proyecto,
                anio=anio,
                mes=mes,
                vigente=True,
            ).first()

        contexto_integrado = (
            construir_contexto_dashboard_integrado(anio, mes, contrato=proyecto)
            if periodo_valido
            else _CONTEXTO_VACIO
        )

        payload = {
            "anio": anio,
            "mes": mes,
            "periodo_valido": periodo_valido,
            "proyecto": proyecto,
            "carga": carga,
            "tipo_operacional": tipo_operacional,
            "centro_costo": centro_costo,
            "indicadores": CargaFinancieraView._indicadores(
                carga, tipo_operacional=tipo_operacional, centro_costo=centro_costo
            ),
            "desglose_costos": CargaFinancieraView._desglose_costos(
                carga, tipo_operacional=tipo_operacional, centro_costo=centro_costo
            ),
            "tendencia_6_meses": CargaFinancieraView._tendencia_6_meses(
                carga, tipo_operacional=tipo_operacional, centro_costo=centro_costo
            ),
            "resumen_totales": CargaFinancieraView._resumen_totales(
                carga, tipo_operacional=tipo_operacional, centro_costo=centro_costo
            ),
            "usuario": request.user,
            "generado_en": timezone.now(),
        }
        payload.update(contexto_integrado)
        return payload

    def _generar(self, payload: dict) -> bytes:  # pragma: no cover - override
        raise NotImplementedError


class DashboardExportarPdfView(_DashboardExportarBaseView):
    formato = "pdf"
    content_type = "application/pdf"
    extension = "pdf"

    def _generar(self, payload: dict) -> bytes:
        return generar_pdf_ejecutivo(payload)


class DashboardExportarExcelView(_DashboardExportarBaseView):
    formato = "excel"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    extension = "xlsx"

    def _generar(self, payload: dict) -> bytes:
        return generar_excel_detallado(payload)


class DashboardExportarPptView(_DashboardExportarBaseView):
    formato = "ppt"
    content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    extension = "pptx"

    def _generar(self, payload: dict) -> bytes:
        return generar_ppt_stakeholders(payload)
