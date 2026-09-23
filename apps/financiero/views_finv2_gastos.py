"""Vistas del flujo completo de facturas de gastos (#248).

RBAC granular (#248 gap): `allowed_roles=["admin","director","coordinador"]`
hardcodeado quedó reemplazado por `required_submodulo =
SUBMODULO_FIN_FACTURAS_GASTOS`, mismo criterio ya aplicado a Facturas de
Ingresos en `views_finv2_ingresos.py` (#249 gap 1) -- la matriz
`RoleModuloPermiso` (S1 sembró `contador`/`gerente_financiero` con acceso)
es ahora la autoridad, no una lista fija en código.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.core.mixins import RoleRequiredMixin
from apps.core.models_roles import RoleModuloPermiso
from apps.core.permissions import SUBMODULO_FIN_FACTURAS_GASTOS, user_nivel_acceso_submodulo

from .forms_finv2_gastos import FacturaGastoForm, GenerarFacturasGastoForm, PagoFacturaGastoForm
from .models import (
    AuditoriaFacturaGasto,
    CargaFacturaGasto,
    FacturaGasto,
)
from .services_finv2_gastos import (
    UMBRAL_APROBACION,
    aprobar_gasto,
    cargas_elegibles_para_generar_gastos,
    generar_facturas_gasto_desde_carga,
    registrar_pago_gasto,
)

SESSION_KEY_GENERACION_GASTOS = "generacion_facturas_gasto_carga_id"


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
    """Paso 1 (#248, corrección post-rechazo 22-sep): elegir la
    `CargaFinanciera` (proyecto+período) YA cargada y homologada por #246,
    en vez de subir un CSV con columnas propias que nunca coincidieron con
    el archivo real del cliente (causa raíz del rechazo de Andrea -- ver
    SPRINTS/PLAN_2026-09-23_248_facturas_gasto_desde_carga_financiera.md).

    `test_func` exige `ver_editar` incluso para el GET -- mismo criterio que
    antes: elegir la carga origen encadena una mutación (generación) aunque
    todavía no persista nada hasta la confirmación del paso 2.
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
        context["form"] = kwargs.get("form") or GenerarFacturasGastoForm()
        context["historial"] = CargaFacturaGasto.objects.all()[:10]
        return context

    def post(self, request, *args, **kwargs):
        form = GenerarFacturasGastoForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Seleccione una carga financiera procesada con líneas reales.")
            return self.render_to_response(self.get_context_data(form=form))
        carga = form.cleaned_data["carga_financiera"]
        request.session[SESSION_KEY_GENERACION_GASTOS] = str(carga.pk)
        return redirect("financiero:factura_gasto_importar_preview")


class GastoImportarPreviewView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Paso 2: vista previa sin persistir + confirmación transaccional (#248).

    La vista previa vuelve a ejecutar `generar_facturas_gasto_desde_carga`
    con `commit=False` (misma función que persiste en la confirmación) --
    así el preview nunca puede desincronizarse de lo que en verdad se va a
    guardar.
    """

    template_name = "financiero/factura_gasto_importar_preview.html"
    required_submodulo = SUBMODULO_FIN_FACTURAS_GASTOS

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        nivel = user_nivel_acceso_submodulo(self.request.user, self.required_submodulo)
        return nivel == RoleModuloPermiso.VER_EDITAR

    def _carga_seleccionada(self):
        carga_id = self.request.session.get(SESSION_KEY_GENERACION_GASTOS)
        if not carga_id:
            return None
        return cargas_elegibles_para_generar_gastos().filter(pk=carga_id).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        carga = self._carga_seleccionada()
        context["carga"] = carga
        context["resultado"] = (
            generar_facturas_gasto_desde_carga(carga, commit=False) if carga else None
        )
        return context

    def get(self, request, *args, **kwargs):
        if not self._carga_seleccionada():
            messages.error(request, "No hay una carga financiera seleccionada. Elija una primero.")
            return redirect("financiero:factura_gasto_importar")
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        carga = self._carga_seleccionada()
        if not carga:
            messages.error(request, "No hay una carga financiera seleccionada. Elija una primero.")
            return redirect("financiero:factura_gasto_importar")

        if request.POST.get("cancelar"):
            request.session.pop(SESSION_KEY_GENERACION_GASTOS, None)
            messages.info(request, "Generación descartada. Puede elegir otra carga financiera.")
            return redirect("financiero:factura_gasto_importar")

        if not request.POST.get("confirmar"):
            messages.error(request, "Acción no reconocida.")
            return self.render_to_response(self.get_context_data())

        usuario = request.user.get_username()
        with transaction.atomic():
            resultado = generar_facturas_gasto_desde_carga(carga, usuario=usuario, commit=True)

            detalle_filas = []
            for item in resultado.procesadas:
                factura = item.factura
                AuditoriaFacturaGasto.objects.create(
                    factura=factura,
                    campo="generacion",
                    valor_anterior="",
                    valor_nuevo=(
                        f"{'creada' if item.accion == 'crear' else 'actualizada'} desde carga "
                        f"financiera {carga.proyecto.codigo} {carga.mes:02d}/{carga.anio} — "
                        f"total ${factura.total}"
                    ),
                    usuario=usuario,
                )
                detalle_filas.append(
                    {
                        "proveedor_nit": factura.proveedor.nit or "",
                        "numero_documento": factura.numero_documento,
                        "fecha": factura.fecha.isoformat(),
                        "concepto": factura.concepto,
                        "total": str(factura.total),
                        "accion": item.accion,
                    }
                )

            CargaFacturaGasto.objects.create(
                archivo_nombre=f"Carga financiera {carga.proyecto.codigo} {carga.mes:02d}/{carga.anio}",
                usuario=usuario,
                filas_total=len(detalle_filas) + resultado.total_omitidas,
                filas_validas=len(detalle_filas),
                filas_error=resultado.total_omitidas,
                filas_creadas=resultado.total_creadas,
                filas_actualizadas=resultado.total_actualizadas,
                resultado="CONFIRMADA",
                detalle_errores=[
                    {"fila": omitida.fila_origen, "error": f"{omitida.concepto}: {omitida.motivo}"}
                    for omitida in resultado.omitidas
                ],
                detalle_filas=detalle_filas,
            )
        request.session.pop(SESSION_KEY_GENERACION_GASTOS, None)
        messages.success(
            request,
            f"Generación confirmada: {resultado.total_creadas} factura(s) creada(s), "
            f"{resultado.total_actualizadas} actualizada(s), {resultado.total_omitidas} omitida(s).",
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
