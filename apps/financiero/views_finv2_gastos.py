"""Vistas del flujo completo de facturas de gastos (#248).

RBAC granular (#248 gap): `allowed_roles=["admin","director","coordinador"]`
hardcodeado quedó reemplazado por `required_submodulo =
SUBMODULO_FIN_FACTURAS_GASTOS`, mismo criterio ya aplicado a Facturas de
Ingresos en `views_finv2_ingresos.py` (#249 gap 1) -- la matriz
`RoleModuloPermiso` (S1 sembró `contador`/`gerente_financiero` con acceso)
es ahora la autoridad, no una lista fija en código.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.contratos.models import Contrato
from apps.core.mixins import RoleRequiredMixin
from apps.core.models_roles import RoleModuloPermiso
from apps.core.permissions import SUBMODULO_FIN_FACTURAS_GASTOS, user_nivel_acceso_submodulo

from .forms_finv2_gastos import FacturaGastoForm, ImportarFacturasGastoForm, PagoFacturaGastoForm
from .importers_finv2_gastos import columnas_para, validar_filas
from .models import (
    AuditoriaFacturaGasto,
    CargaFacturaGasto,
    FacturaGasto,
    HomologacionProjectsContable,
    Proveedor,
)
from .services_finv2_gastos import (
    UMBRAL_APROBACION,
    aprobar_gasto,
    calcular_totales,
    registrar_pago_gasto,
)

SESSION_KEY_IMPORTACION_GASTOS = "importacion_facturas_gasto"


def _registrar_cambio_estado(factura, estado_anterior, usuario):
    """Auditoría de transición de estado (#248) -- mismo patrón externo al
    servicio que usa `IngresoDetailView.post()` para `AuditoriaFacturaIngreso`
    (services_finv2_gastos.py no está en FILES_OWNED de esta sub-feature)."""
    if factura.estado != estado_anterior:
        AuditoriaFacturaGasto.objects.create(
            factura=factura,
            campo="estado",
            valor_anterior=estado_anterior,
            valor_nuevo=factura.estado,
            usuario=usuario,
        )


class GastosListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = "financiero/facturas_gastos_lista.html"
    context_object_name = "facturas"
    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS

    def get_queryset(self):
        queryset = FacturaGasto.objects.select_related("proveedor", "contrato").all()
        estado = self.request.GET.get("estado")
        return queryset.filter(estado=estado) if estado in FacturaGasto.Estado.values else queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        base = FacturaGasto.objects.exclude(estado=FacturaGasto.Estado.RECHAZADA).select_related(
            "proveedor"
        )
        # Alertas del checklist #248 sección 8: pendientes de aprobación
        # (>$1M), próximas a vencer (7 días, usa el supuesto de
        # fecha_vencimiento) y sin pagar.
        context["alertas"] = {
            "pendientes_aprobacion": base.filter(
                estado=FacturaGasto.Estado.PENDIENTE_APROBACION,
                total__gt=UMBRAL_APROBACION,
            ).order_by("-total")[:10],
            "proximas_vencer": base.filter(
                estado__in=[
                    FacturaGasto.Estado.PENDIENTE_APROBACION,
                    FacturaGasto.Estado.PENDIENTE_PAGO,
                ],
                fecha_vencimiento__isnull=False,
                fecha_vencimiento__gte=hoy,
                fecha_vencimiento__lte=hoy + timedelta(days=7),
            ).order_by("fecha_vencimiento")[:10],
            "sin_pagar": base.filter(
                estado__in=[
                    FacturaGasto.Estado.PENDIENTE_APROBACION,
                    FacturaGasto.Estado.PENDIENTE_PAGO,
                ]
            ).order_by("fecha")[:10],
        }
        context["estados"] = FacturaGasto.Estado.choices
        context["filtro_estado"] = self.request.GET.get("estado", "")
        return context


class GastoCreateView(LoginRequiredMixin, RoleRequiredMixin, FormView):
    template_name = "financiero/factura_gasto_form.html"
    form_class = FacturaGastoForm
    success_url = reverse_lazy("financiero:facturas_gastos_lista")
    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS

    def form_valid(self, form):
        factura = form.save()
        AuditoriaFacturaGasto.objects.create(
            factura=factura,
            campo="creacion",
            valor_anterior="",
            valor_nuevo=f"registrada por {self.request.user.get_username()} — total ${factura.total}",
            usuario=self.request.user.get_username(),
        )
        messages.success(self.request, "Factura registrada y total calculado con IVA del 19%.")
        return redirect("financiero:factura_gasto_detalle", pk=factura.pk)


class GastoDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    template_name = "financiero/factura_gasto_detalle.html"
    context_object_name = "factura"
    model = FacturaGasto
    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pago_form"] = kwargs.get("pago_form") or PagoFacturaGastoForm()
        context["auditoria"] = self.object.auditoria.all()[:20]
        return context

    def post(self, request, *args, **kwargs):
        factura = self.get_object()
        accion = request.POST.get("accion")
        estado_anterior = factura.estado
        usuario = request.user.get_username()
        try:
            if accion == "aprobar":
                aprobar_gasto(factura, request.POST.get("comentario_decision", ""))
                _registrar_cambio_estado(factura, estado_anterior, usuario)
                messages.success(request, "Factura aprobada y lista para pago.")
            elif accion == "rechazar":
                # Checklist #248 sección 3: "Puede aprobar o rechazar con
                # comentarios" -- el flujo original solo cubría aprobar.
                comentario = (request.POST.get("comentario_decision", "") or "").strip()
                if factura.estado != FacturaGasto.Estado.PENDIENTE_APROBACION:
                    raise ValidationError(
                        "Solo se pueden rechazar facturas pendientes de aprobación."
                    )
                if not comentario:
                    raise ValidationError("El comentario es obligatorio para rechazar una factura.")
                factura.estado = FacturaGasto.Estado.RECHAZADA
                factura.comentario_decision = comentario
                factura.save(update_fields=["estado", "comentario_decision", "updated_at"])
                _registrar_cambio_estado(factura, estado_anterior, usuario)
                messages.success(request, "Factura rechazada.")
            elif accion == "pagar":
                form = PagoFacturaGastoForm(request.POST)
                if not form.is_valid():
                    return self.render_to_response(self.get_context_data(pago_form=form))
                registrar_pago_gasto(factura, **form.cleaned_data)
                _registrar_cambio_estado(factura, estado_anterior, usuario)
                messages.success(request, "Pago registrado con su referencia.")
            else:
                messages.error(request, "La acción solicitada no es válida.")
        except ValidationError as error:
            mensaje = error.messages[0] if hasattr(error, "messages") else str(error)
            messages.error(request, mensaje)
        return redirect("financiero:factura_gasto_detalle", pk=factura.pk)


class GastoImportarView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Paso 1 de la carga masiva (#248 sección 5): subir archivo + historial.

    `test_func` exige `ver_editar` incluso para el GET -- mismo criterio de
    `ImportarFacturasIngresoView` (#249): subir un archivo es una acción
    mutativa aunque todavía no persista nada hasta la confirmación.
    """

    template_name = "financiero/factura_gasto_importar.html"
    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        nivel = user_nivel_acceso_submodulo(self.request.user, self.required_submodulo)
        return nivel == RoleModuloPermiso.VER_EDITAR

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columnas"] = columnas_para()
        context["form"] = kwargs.get("form") or ImportarFacturasGastoForm()
        context["historial"] = CargaFacturaGasto.objects.all()[:10]
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("plantilla") == "csv":
            respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
            respuesta["Content-Disposition"] = 'attachment; filename="plantilla_facturas_gasto.csv"'
            respuesta.write(",".join(columnas_para()) + "\n")
            return respuesta
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        form = ImportarFacturasGastoForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Seleccione un archivo CSV o XLSX válido.")
            return self.render_to_response(self.get_context_data(form=form))
        archivo = form.cleaned_data["archivo"]
        try:
            filas, errores = validar_filas(
                archivo, Proveedor, Contrato, HomologacionProjectsContable, FacturaGasto
            )
        except Exception as exc:  # noqa: BLE001 -- errores de parseo del archivo
            errores, filas = [{"fila": 1, "error": str(exc)}], []
        preview = {
            "archivo_nombre": archivo.name,
            "filas": [
                {
                    campo: (
                        valor.isoformat()
                        if hasattr(valor, "isoformat")
                        else str(valor)
                        if isinstance(valor, Decimal)
                        else valor
                    )
                    for campo, valor in fila.items()
                }
                for fila in filas
            ],
            "errores": errores,
            "nuevas": sum(fila["accion_carga"] == "crear" for fila in filas),
            "actualizaciones": sum(fila["accion_carga"] == "actualizar" for fila in filas),
        }
        request.session[SESSION_KEY_IMPORTACION_GASTOS] = preview
        CargaFacturaGasto.objects.create(
            archivo_nombre=archivo.name,
            usuario=request.user.get_username(),
            filas_total=len(filas) + len(errores),
            filas_validas=len(filas),
            filas_error=len(errores),
            resultado="PREVIEW" if not errores else "RECHAZADA",
            detalle_errores=errores,
        )
        return redirect("financiero:factura_gasto_importar_preview")


class GastoImportarPreviewView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Paso 2: vista previa sin persistir + confirmación transaccional + reintento."""

    template_name = "financiero/factura_gasto_importar_preview.html"
    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        nivel = user_nivel_acceso_submodulo(self.request.user, self.required_submodulo)
        return nivel == RoleModuloPermiso.VER_EDITAR

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["preview"] = self.request.session.get(SESSION_KEY_IMPORTACION_GASTOS)
        return context

    def get(self, request, *args, **kwargs):
        if not request.session.get(SESSION_KEY_IMPORTACION_GASTOS):
            messages.error(request, "No hay una vista previa activa. Cargue un archivo primero.")
            return redirect("financiero:factura_gasto_importar")
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        preview = request.session.get(SESSION_KEY_IMPORTACION_GASTOS)
        if not preview:
            messages.error(request, "No hay una vista previa activa. Cargue un archivo primero.")
            return redirect("financiero:factura_gasto_importar")

        if request.POST.get("cancelar"):
            del request.session[SESSION_KEY_IMPORTACION_GASTOS]
            messages.info(request, "Carga descartada. Puede intentar con otro archivo.")
            return redirect("financiero:factura_gasto_importar")

        if not request.POST.get("confirmar"):
            messages.error(request, "Acción no reconocida.")
            return self.render_to_response(self.get_context_data())

        if preview.get("errores"):
            messages.error(request, "Corrija los errores señalados antes de confirmar la carga.")
            return self.render_to_response(self.get_context_data())
        if not preview.get("filas"):
            messages.error(request, "No hay filas válidas para confirmar.")
            return self.render_to_response(self.get_context_data())

        creadas = actualizadas = 0
        detalle_filas = []
        usuario = request.user.get_username()
        with transaction.atomic():
            for fila in preview["filas"]:
                fecha_factura = date.fromisoformat(fila["fecha_factura"])
                valor_neto = Decimal(fila["valor_neto"])
                totales = calcular_totales(valor_neto)
                homologacion = HomologacionProjectsContable.objects.filter(
                    centro_costo__iexact=fila["centro_costo"], activo=True
                ).first()

                if fila["accion_carga"] == "actualizar":
                    factura = FacturaGasto.objects.select_for_update().get(pk=fila["_factura_id"])
                    antes = {
                        "concepto": factura.concepto,
                        "subtotal": str(factura.subtotal),
                        "centro_costo": factura.centro_costo,
                    }
                    factura.concepto = fila["concepto"]
                    factura.centro_costo = fila["centro_costo"]
                    factura.contrato_id = fila["contrato_id"]
                    factura.homologacion = homologacion
                    factura.subtotal = totales["subtotal"]
                    factura.iva = totales["iva"]
                    factura.total = totales["total"]
                    factura.save()
                    for campo, valor_nuevo in (
                        ("concepto", fila["concepto"]),
                        ("subtotal", str(totales["subtotal"])),
                        ("centro_costo", fila["centro_costo"]),
                    ):
                        if antes.get(campo, "") != valor_nuevo:
                            AuditoriaFacturaGasto.objects.create(
                                factura=factura,
                                campo=campo,
                                valor_anterior=antes.get(campo, ""),
                                valor_nuevo=valor_nuevo,
                                usuario=usuario,
                            )
                    actualizadas += 1
                    accion = "actualizar"
                else:
                    # #248: el CSV no trae número de documento -- se genera
                    # uno determinístico y legible (ver importers_finv2_gastos.py).
                    numero_documento = f"CM-{fecha_factura:%Y%m%d}-{fila['fila']:04d}"
                    estado = (
                        FacturaGasto.Estado.PENDIENTE_APROBACION
                        if totales["total"] > UMBRAL_APROBACION or fila["requiere_aprobacion"]
                        else FacturaGasto.Estado.PENDIENTE_PAGO
                    )
                    factura = FacturaGasto.objects.create(
                        proveedor_id=fila["proveedor_id"],
                        contrato_id=fila["contrato_id"],
                        homologacion=homologacion,
                        numero_documento=numero_documento,
                        fecha=fecha_factura,
                        fecha_vencimiento=fecha_factura + timedelta(days=30),
                        concepto=fila["concepto"],
                        categoria="Carga masiva",
                        centro_costo=fila["centro_costo"],
                        subtotal=totales["subtotal"],
                        iva=totales["iva"],
                        total=totales["total"],
                        estado=estado,
                    )
                    AuditoriaFacturaGasto.objects.create(
                        factura=factura,
                        campo="creacion",
                        valor_anterior="",
                        valor_nuevo=f"carga masiva — total ${factura.total}",
                        usuario=usuario,
                    )
                    creadas += 1
                    accion = "crear"

                detalle_filas.append(
                    {
                        "proveedor_nit": fila["proveedor_nit"],
                        "numero_documento": factura.numero_documento,
                        "fecha": fecha_factura.isoformat(),
                        "concepto": factura.concepto,
                        "total": str(factura.total),
                        "accion": accion,
                    }
                )

            CargaFacturaGasto.objects.create(
                archivo_nombre=preview["archivo_nombre"],
                usuario=usuario,
                filas_total=len(preview["filas"]),
                filas_validas=len(preview["filas"]),
                filas_creadas=creadas,
                filas_actualizadas=actualizadas,
                resultado="CONFIRMADA",
                detalle_filas=detalle_filas,
            )
        del request.session[SESSION_KEY_IMPORTACION_GASTOS]
        messages.success(
            request,
            f"Carga confirmada: {creadas} factura(s) creada(s), {actualizadas} actualizada(s).",
        )
        return redirect("financiero:facturas_gastos_lista")


class GastoCargasHistorialView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = "financiero/factura_gasto_cargas.html"
    context_object_name = "cargas"
    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS
    paginate_by = 25

    def get_queryset(self):
        return CargaFacturaGasto.objects.all()


class GastoCargaCsvView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Export CSV de una carga CONFIRMADA (regla migrations->export del
    BLUEPRINT) -- consumidor http_get de `CargaFacturaGasto.detalle_filas`."""

    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS

    def get(self, request, pk, *args, **kwargs):
        carga = CargaFacturaGasto.objects.filter(pk=pk, resultado="CONFIRMADA").first()
        if not carga:
            raise Http404("La carga solicitada no existe o no fue confirmada.")
        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = f'attachment; filename="carga_gastos_{carga.pk}.csv"'
        respuesta.write("proveedor_nit,numero_documento,fecha,concepto,total,accion\n")
        for fila in carga.detalle_filas:
            concepto = str(fila.get("concepto", "")).replace(",", ";")
            respuesta.write(
                f"{fila.get('proveedor_nit', '')},{fila.get('numero_documento', '')},"
                f"{fila.get('fecha', '')},{concepto},{fila.get('total', '')},"
                f"{fila.get('accion', '')}\n"
            )
        return respuesta
