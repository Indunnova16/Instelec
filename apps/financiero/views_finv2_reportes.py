"""Maestros y reportes de facturación v2 (#248, #249)."""

from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin
from apps.core.models_roles import RoleModuloPermiso
from apps.core.permissions import SUBMODULO_FIN_MAESTROS, user_nivel_acceso_submodulo

from .models import (
    AuditoriaTercero, Banco, CargaTerceros, CicloFacturacion, Cliente, FacturaGasto, MetodoPago, Proveedor,
)
from .importers_terceros import columnas_para, validar_filas
from .services_finv2_gastos import calcular_totales
from .services_finv2_ingresos import facturacion_real_vs_meta, generar_numero_factura


class TerceroForm(forms.ModelForm):
    nit_inmutable = False

    class Meta:
        fields = (
            "nombre", "nit", "email", "telefono", "direccion", "plazo_pago_dias",
            "fecha_inicio_contrato", "fecha_fin_contrato", "activo", "motivo_inactivacion",
        )
        widgets = {"activo": forms.CheckboxInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El default del modelo no vuelve opcional el input de un ModelForm.
        # Mantenerlo opcional preserva altas legacy que no enviaban este campo.
        self.fields["plazo_pago_dias"].required = False
        # BaseModel asigna UUID antes del primer save; ``pk`` no distingue una
        # alta de una edición. Sólo inmovilizamos el NIT de un tercero ya
        # persistido.
        if self.instance and not self.instance._state.adding:
            self.fields["nit"].disabled = True

    def clean_plazo_pago_dias(self):
        valor = self.cleaned_data.get("plazo_pago_dias")
        return valor if valor not in (None, "") else 30

    def clean(self):
        cleaned = super().clean()
        inicio, fin = cleaned.get("fecha_inicio_contrato"), cleaned.get("fecha_fin_contrato")
        if inicio and fin and fin < inicio:
            self.add_error("fecha_fin_contrato", "La fecha final no puede ser anterior al inicio.")
        if not cleaned.get("activo") and not (cleaned.get("motivo_inactivacion") or "").strip():
            self.add_error("motivo_inactivacion", "Indique el motivo de inactivación.")
        return cleaned

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre o razón social es obligatorio.")
        return nombre

    def clean_nit(self):
        nit = (self.cleaned_data.get("nit") or "").strip()
        return nit or None


class ProveedorForm(TerceroForm):
    class Meta(TerceroForm.Meta):
        model = Proveedor
        fields = TerceroForm.Meta.fields[:5] + ("tipo_servicio",) + TerceroForm.Meta.fields[5:]


class ClienteForm(TerceroForm):
    class Meta(TerceroForm.Meta):
        model = Cliente
        fields = TerceroForm.Meta.fields[:5] + ("industria",) + TerceroForm.Meta.fields[5:]


class MaestroPagoForm(forms.ModelForm):
    class Meta:
        fields = ("nombre", "activo")

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre es obligatorio.")
        return nombre


class BaseTerceroCrudView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """CRUD de terceros con desactivación segura para registros con facturas."""

    model = None
    template_name = ""
    context_object_name = "terceros"
    singular = "registro"
    form_class = TerceroForm
    success_url_name = ""
    required_submodulo = SUBMODULO_FIN_MAESTROS
    # Este maestro no admite el bypass por nivel administrativo: la matriz
    # granular es el contrato de acceso del cliente.
    admin_bypass = False
    requiere_gestion_para_ver = False

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        nivel = user_nivel_acceso_submodulo(
            self.request.user, self.required_submodulo
        )
        necesita_edicion = (
            self.requiere_gestion_para_ver
            or self.request.method != "GET"
            or bool(self.kwargs.get("pk"))
        )
        if necesita_edicion:
            return nivel == RoleModuloPermiso.VER_EDITAR
        return nivel in (RoleModuloPermiso.VER, RoleModuloPermiso.VER_EDITAR)

    def get_queryset(self):
        estado = self.request.GET.get("estado", "activos")
        queryset = self.model.objects.all()
        if estado == "activos":
            queryset = queryset.filter(activo=True)
        elif estado == "inactivos":
            queryset = queryset.filter(activo=False)
        return queryset

    def get_object(self):
        return get_object_or_404(self.model, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = self.get_object() if self.kwargs.get("pk") else None
        context[self.context_object_name] = self.get_queryset()
        context["form"] = kwargs.get("form") or self.form_class(instance=instance)
        context["editing"] = instance
        context["puede_gestionar"] = (
            user_nivel_acceso_submodulo(
                self.request.user, self.required_submodulo
            ) == RoleModuloPermiso.VER_EDITAR
        )
        return context

    def post(self, request, *args, **kwargs):
        instance = self.get_object() if self.kwargs.get("pk") else None
        # ModelForm construye valores sobre ``instance`` durante is_valid();
        # conservar el estado previo antes de validar para detectar la
        # transición activo → inactivo correctamente.
        estaba_activo = instance.activo if instance else None
        form = self.form_class(request.POST, instance=instance)
        if not form.is_valid():
            messages.error(request, "Corrija los campos marcados antes de guardar.")
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
            before = {}
            if instance:
                before = {field: str(getattr(instance, field) or "") for field in form.changed_data}
            saved = form.save(commit=False)
            if instance and estaba_activo and not saved.activo:
                saved.inactivo_desde = timezone.localdate()
            if instance and not estaba_activo and saved.activo:
                saved.inactivo_desde = None
                saved.motivo_inactivacion = ""
            saved.save()
            tipo = "CLIENTE" if self.model is Cliente else "PROVEEDOR"
            for field in form.changed_data:
                AuditoriaTercero.objects.create(
                    tercero_tipo=tipo, tercero_id=saved.pk, campo=field,
                    valor_anterior=before.get(field, ""), valor_nuevo=str(getattr(saved, field) or ""),
                    usuario=request.user.get_username(),
                )
        accion = "actualizado" if instance else "creado"
        messages.success(request, f"{self.singular.capitalize()} {accion} correctamente.")
        return redirect(self.success_url_name)


class ProveedorCrudView(BaseTerceroCrudView):
    model = Proveedor
    template_name = "financiero/proveedores_lista.html"
    context_object_name = "proveedores"
    singular = "proveedor"
    form_class = ProveedorForm
    success_url_name = "financiero:proveedores_lista"


class ProveedorFormView(ProveedorCrudView):
    template_name = "financiero/proveedor_form.html"
    requiere_gestion_para_ver = True


class ClienteCrudView(BaseTerceroCrudView):
    model = Cliente
    template_name = "financiero/clientes_lista.html"
    context_object_name = "clientes"
    singular = "cliente"
    form_class = ClienteForm
    success_url_name = "financiero:clientes_lista"


class ClienteFormView(ClienteCrudView):
    template_name = "financiero/cliente_form.html"
    requiere_gestion_para_ver = True


class TerceroAuditoriaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "financiero/tercero_auditoria.html"
    required_submodulo = SUBMODULO_FIN_MAESTROS
    admin_bypass = False
    requiere_gestion_para_ver = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["auditoria"] = AuditoriaTercero.objects.filter(
            tercero_tipo=self.kwargs["tipo"], tercero_id=self.kwargs["pk"]
        )
        return context


class ImportarTercerosView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Preview primero; la confirmación crea todo el lote o nada."""

    template_name = "financiero/terceros_importar.html"
    required_submodulo = SUBMODULO_FIN_MAESTROS
    admin_bypass = False
    requiere_gestion_para_ver = True

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        nivel = user_nivel_acceso_submodulo(
            self.request.user, self.required_submodulo
        )
        return nivel == RoleModuloPermiso.VER_EDITAR
    tipo = None
    model = None
    listado_url = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "tipo": self.tipo.lower(), "columnas": columnas_para(self.tipo),
            "historial": CargaTerceros.objects.filter(tercero_tipo=self.tipo)[:10],
            "preview": self.request.session.get(f"importacion_{self.tipo}"),
        })
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("plantilla") == "csv":
            respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
            respuesta["Content-Disposition"] = f'attachment; filename="plantilla_{self.tipo.lower()}s.csv"'
            respuesta.write(",".join(columnas_para(self.tipo)) + "\n")
            return respuesta
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        clave = f"importacion_{self.tipo}"
        if request.POST.get("confirmar"):
            preview = request.session.get(clave)
            if not preview or preview.get("errores"):
                messages.error(request, "No hay una vista previa válida para confirmar.")
                return redirect(request.path)
            with transaction.atomic():
                self.model.objects.bulk_create([self.model(**fila) for fila in preview["filas"]])
                CargaTerceros.objects.create(
                    tercero_tipo=self.tipo, archivo_nombre=preview["archivo_nombre"],
                    usuario=request.user.get_username(), filas_total=len(preview["filas"]),
                    filas_validas=len(preview["filas"]), resultado="CONFIRMADA",
                )
            del request.session[clave]
            messages.success(request, f"Carga de {self.tipo.lower()}s confirmada correctamente.")
            return redirect(self.listado_url)
        archivo = request.FILES.get("archivo")
        if not archivo:
            messages.error(request, "Seleccione un archivo CSV o XLSX.")
            return self.render_to_response(self.get_context_data())
        try:
            filas, errores = validar_filas(archivo, self.tipo, self.model)
        except Exception as exc:
            errores, filas = [{"fila": 1, "error": str(exc)}], []
        preview = {"archivo_nombre": archivo.name, "filas": [
            {campo: valor.isoformat() if hasattr(valor, "isoformat") else valor for campo, valor in fila.items()}
            for fila in filas
        ], "errores": errores}
        request.session[clave] = preview
        CargaTerceros.objects.create(
            tercero_tipo=self.tipo, archivo_nombre=archivo.name, usuario=request.user.get_username(),
            filas_total=len(filas) + len(errores), filas_validas=len(filas), filas_error=len(errores),
            resultado="PREVIEW" if not errores else "RECHAZADA", detalle_errores=errores,
        )
        return self.render_to_response(self.get_context_data())


class ImportarClientesView(ImportarTercerosView):
    tipo, model, listado_url = "CLIENTE", Cliente, "financiero:clientes_lista"


class ImportarProveedoresView(ImportarTercerosView):
    tipo, model, listado_url = "PROVEEDOR", Proveedor, "financiero:proveedores_lista"


class MaestrosPagoView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "financiero/maestros_pago.html"
    allowed_roles = ["admin", "director", "coordinador"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bancos"] = Banco.objects.all()
        context["metodos_pago"] = MetodoPago.objects.all()
        context["form"] = kwargs.get("form") or MaestroPagoForm()
        context["tipo"] = kwargs.get("tipo", "banco")
        return context

    def post(self, request, *args, **kwargs):
        modelo = {"banco": Banco, "metodo": MetodoPago}.get(request.POST.get("tipo"))
        if modelo is None:
            messages.error(request, "El tipo de maestro solicitado no es válido.")
            return redirect("financiero:maestros_pago")
        instance = None
        if request.POST.get("pk"):
            instance = get_object_or_404(modelo, pk=request.POST["pk"])
        form = MaestroPagoForm(request.POST, instance=instance)
        if not form.is_valid():
            messages.error(request, "Corrija el maestro de pago antes de guardar.")
            return self.render_to_response(
                self.get_context_data(form=form, tipo=request.POST["tipo"])
            )
        form.save()
        messages.success(
            request,
            "Maestro de pago actualizado correctamente."
            if instance
            else "Maestro de pago creado correctamente.",
        )
        return redirect("financiero:maestros_pago")


class ReporteFacturacionView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "financiero/reportes_facturacion.html"
    allowed_roles = ["admin", "director", "coordinador"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        gastos = FacturaGasto.objects.select_related("proveedor").all()
        gastos_subtotal = gastos.aggregate(total=Sum("subtotal"))["total"] or Decimal("0.00")
        gastos_total = gastos.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        gastos_pendientes = gastos.exclude(estado=FacturaGasto.Estado.PAGADA).aggregate(
            total=Sum("total")
        )["total"] or Decimal("0.00")

        facturas = list(
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False).select_related(
                "cliente", "presupuesto", "proyecto"
            )
        )
        hoy = timezone.localdate()
        cartera_total = Decimal("0.00")
        cartera_vencida = Decimal("0.00")
        vencidas = 0
        dias_para_pagar = []
        for factura in facturas:
            saldo = max(Decimal("0.00"), factura.total - factura.monto_pagado)
            cartera_total += saldo
            if (
                saldo
                and factura.plazo_pago_dias is not None
                and factura.fecha_factura
                and factura.fecha_factura + timedelta(days=factura.plazo_pago_dias) < hoy
            ):
                cartera_vencida += saldo
                vencidas += 1
            # Plazo promedio real de pago (no el contractual): solo facturas
            # ya cobradas, días efectivamente transcurridos hasta el pago.
            if (
                factura.estado == CicloFacturacion.Estado.PAGO_RECIBIDO
                and factura.fecha_pago
                and factura.fecha_factura
            ):
                dias_para_pagar.append((factura.fecha_pago - factura.fecha_factura).days)

        total_facturas = len(facturas)
        tasa_morosidad = round((vencidas / total_facturas) * 100, 1) if total_facturas else None
        presupuestos = {factura.presupuesto_id: factura.presupuesto for factura in facturas if factura.presupuesto_id}
        indicadores_meta = [facturacion_real_vs_meta(presupuesto) for presupuesto in presupuestos.values()]

        # Contratos B1/B2: se llaman con la firma publicada por las sub-features dueñas.
        total_estimado_gastos = (
            calcular_totales(gastos_subtotal)["total"] if gastos_subtotal else Decimal("0.00")
        )
        context.update(
            {
                "gastos_total": gastos_total,
                "gastos_pendientes": gastos_pendientes,
                "total_estimado_gastos": total_estimado_gastos,
                "cartera_total": cartera_total,
                "cartera_vencida": cartera_vencida,
                "facturas_vencidas": vencidas,
                "tasa_morosidad": tasa_morosidad,
                "plazo_promedio": (
                    round(sum(dias_para_pagar) / len(dias_para_pagar), 1)
                    if dias_para_pagar
                    else None
                ),
                "facturas_cartera": facturas,
                "gastos_historicos": gastos,
                "proximo_numero_factura": generar_numero_factura(hoy),
                "indicadores_meta": indicadores_meta,
            }
        )
        return context
