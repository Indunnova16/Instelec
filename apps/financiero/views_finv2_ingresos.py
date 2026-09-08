"""Emisión, consulta, PDF y cobranza de facturas de ingreso (#249)."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import RoleRequiredMixin

from .forms_finv2_ingresos import (
    FacturaIngresoForm,
    LineaFacturaIngresoFormSet,
    PagoFacturaIngresoForm,
)
from .models import CicloFacturacion
from .services_finv2_ingresos import generar_numero_factura


class IngresoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = "financiero/facturas_ingresos_lista.html"
    context_object_name = "facturas"
    allowed_roles = ["admin", "director", "coordinador"]

    def get_queryset(self):
        return (
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False)
            .select_related(
                "cliente",
                "presupuesto__linea",
            )
            .order_by("-fecha_factura", "-numero_secuencial")
        )


class IngresoCreateView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "financiero/factura_ingreso_form.html"
    allowed_roles = ["admin", "director", "coordinador"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or FacturaIngresoForm(
            initial={"fecha_factura": timezone.localdate()}
        )
        context["lineas_formset"] = kwargs.get("lineas_formset") or LineaFacturaIngresoFormSet(
            prefix="lineas"
        )
        return context

    def post(self, request, *args, **kwargs):
        form = FacturaIngresoForm(request.POST)
        lineas = LineaFacturaIngresoFormSet(request.POST, prefix="lineas")
        if not (form.is_valid() and lineas.is_valid()):
            messages.error(request, "Revise los datos de la factura y sus líneas.")
            return self.render_to_response(self.get_context_data(form=form, lineas_formset=lineas))
        try:
            with transaction.atomic():
                factura = form.save(commit=False)
                factura.numero_factura = generar_numero_factura(factura.fecha_factura)
                factura.numero_secuencial = int(factura.numero_factura.rsplit("-", 1)[1])
                factura.estado = CicloFacturacion.Estado.FACTURA_EMITIDA
                factura.save()
                lineas.instance = factura
                items = lineas.save(commit=False)
                subtotal = Decimal("0.00")
                for item in items:
                    item.total = item.cantidad * item.valor_unitario
                    subtotal += item.total
                    item.save()
                for item in lineas.deleted_objects:
                    item.delete()
                iva = (subtotal * Decimal("0.19")).quantize(Decimal("0.01"))
                factura.subtotal = subtotal
                factura.iva = iva
                factura.total = subtotal + iva
                factura.monto_facturado = factura.total
                factura.save(
                    update_fields=["subtotal", "iva", "total", "monto_facturado", "updated_at"]
                )
        except IntegrityError:
            messages.error(request, "Otra emisión tomó ese consecutivo. Intente nuevamente.")
            return self.render_to_response(self.get_context_data(form=form, lineas_formset=lineas))
        messages.success(request, f"Factura {factura.numero_factura} emitida correctamente.")
        return redirect("financiero:factura_ingreso_detalle", pk=factura.pk)


class IngresoDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    template_name = "financiero/factura_ingreso_detalle.html"
    context_object_name = "factura"
    allowed_roles = ["admin", "director", "coordinador"]

    def get_queryset(self):
        return (
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False)
            .select_related("cliente", "presupuesto")
            .prefetch_related(
                "lineas_factura", "pagos_factura__banco", "pagos_factura__metodo_pago"
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pagado = sum((p.monto for p in self.object.pagos_factura.all()), Decimal("0.00"))
        context["saldo_pendiente"] = max(Decimal("0.00"), self.object.total - pagado)
        context["pago_form"] = kwargs.get("pago_form") or PagoFacturaIngresoForm(
            saldo=context["saldo_pendiente"]
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        pagado = sum((p.monto for p in self.object.pagos_factura.all()), Decimal("0.00"))
        saldo = max(Decimal("0.00"), self.object.total - pagado)
        form = PagoFacturaIngresoForm(request.POST, saldo=saldo)
        if not form.is_valid():
            messages.error(request, "No fue posible registrar el pago.")
            return self.render_to_response(self.get_context_data(pago_form=form))
        with transaction.atomic():
            pago = form.save(commit=False)
            pago.ciclo = self.object
            pago.save()
            self.object.monto_pagado = pagado + pago.monto
            if self.object.monto_pagado >= self.object.total:
                self.object.estado = CicloFacturacion.Estado.PAGO_RECIBIDO
                self.object.fecha_pago = pago.fecha
            self.object.save(update_fields=["monto_pagado", "estado", "fecha_pago", "updated_at"])
        messages.success(request, "Pago registrado correctamente.")
        return redirect("financiero:factura_ingreso_detalle", pk=self.object.pk)


class IngresoPdfView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    allowed_roles = ["admin", "director", "coordinador"]

    def get(self, request, pk, *args, **kwargs):
        factura = (
            CicloFacturacion.objects.filter(numero_secuencial__isnull=False)
            .select_related("cliente", "presupuesto")
            .prefetch_related("lineas_factura")
            .filter(pk=pk)
            .first()
        )
        if not factura:
            raise Http404("La factura solicitada no existe.")
        html = render_to_string(
            "financiero/factura_ingreso_pdf.html", {"factura": factura, "request": request}
        )
        try:
            from weasyprint import HTML

            pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        except (ImportError, OSError) as error:
            return HttpResponse(
                f"No fue posible generar el PDF: {error}", status=503, content_type="text/plain"
            )
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{factura.numero_factura}.pdf"'
        return response
