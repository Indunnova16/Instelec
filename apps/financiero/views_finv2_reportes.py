"""Maestros y reportes de facturación v2 (#248, #249)."""

from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from .models import Banco, CicloFacturacion, Cliente, FacturaGasto, MetodoPago, Proveedor
from .services_finv2_gastos import calcular_totales
from .services_finv2_ingresos import generar_numero_factura


class TerceroForm(forms.ModelForm):
    class Meta:
        fields = ("nombre", "nit", "email", "telefono", "activo")
        widgets = {"activo": forms.CheckboxInput()}

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


class ClienteForm(TerceroForm):
    class Meta(TerceroForm.Meta):
        model = Cliente


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
    allowed_roles = ["admin", "director", "coordinador"]

    def get_object(self):
        return get_object_or_404(self.model, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = self.get_object() if self.kwargs.get("pk") else None
        context[self.context_object_name] = self.model.objects.all()
        context["form"] = kwargs.get("form") or self.form_class(instance=instance)
        context["editing"] = instance
        return context

    def post(self, request, *args, **kwargs):
        instance = self.get_object() if self.kwargs.get("pk") else None
        form = self.form_class(request.POST, instance=instance)
        if not form.is_valid():
            messages.error(request, "Corrija los campos marcados antes de guardar.")
            return self.render_to_response(self.get_context_data(form=form))
        form.save()
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


class ClienteCrudView(BaseTerceroCrudView):
    model = Cliente
    template_name = "financiero/clientes_lista.html"
    context_object_name = "clientes"
    singular = "cliente"
    form_class = ClienteForm
    success_url_name = "financiero:clientes_lista"


class ClienteFormView(ClienteCrudView):
    template_name = "financiero/cliente_form.html"


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
        gastos = FacturaGasto.objects.all()
        gastos_subtotal = gastos.aggregate(total=Sum("subtotal"))["total"] or Decimal("0.00")
        gastos_total = gastos.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        gastos_pendientes = gastos.exclude(estado=FacturaGasto.Estado.PAGADA).aggregate(
            total=Sum("total")
        )["total"] or Decimal("0.00")

        facturas = list(
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False).select_related(
                "cliente"
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
                "proximo_numero_factura": generar_numero_factura(hoy),
            }
        )
        return context
