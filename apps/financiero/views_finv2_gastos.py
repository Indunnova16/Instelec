"""Vistas del flujo completo de facturas de gastos (#248)."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import DetailView, FormView, ListView

from apps.core.mixins import RoleRequiredMixin

from .forms_finv2_gastos import FacturaGastoForm, PagoFacturaGastoForm
from .models import FacturaGasto
from .services_finv2_gastos import aprobar_gasto, registrar_pago_gasto


class GastosListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = 'financiero/facturas_gastos_lista.html'
    context_object_name = 'facturas'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        queryset = FacturaGasto.objects.select_related('proveedor', 'contrato').all()
        estado = self.request.GET.get('estado')
        return queryset.filter(estado=estado) if estado in FacturaGasto.Estado.values else queryset


class GastoCreateView(LoginRequiredMixin, RoleRequiredMixin, FormView):
    template_name = 'financiero/factura_gasto_form.html'
    form_class = FacturaGastoForm
    success_url = reverse_lazy('financiero:facturas_gastos_lista')
    allowed_roles = ['admin', 'director', 'coordinador']

    def form_valid(self, form):
        factura = form.save()
        messages.success(self.request, 'Factura registrada y total calculado con IVA del 19%.')
        return redirect('financiero:factura_gasto_detalle', pk=factura.pk)


class GastoDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    template_name = 'financiero/factura_gasto_detalle.html'
    context_object_name = 'factura'
    model = FacturaGasto
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pago_form'] = PagoFacturaGastoForm()
        return context

    def post(self, request, *args, **kwargs):
        factura = self.get_object()
        accion = request.POST.get('accion')
        try:
            if accion == 'aprobar':
                aprobar_gasto(factura, request.POST.get('comentario_decision', ''))
                messages.success(request, 'Factura aprobada y lista para pago.')
            elif accion == 'pagar':
                form = PagoFacturaGastoForm(request.POST)
                if not form.is_valid():
                    return self.render_to_response(self.get_context_data(pago_form=form))
                registrar_pago_gasto(factura, **form.cleaned_data)
                messages.success(request, 'Pago registrado con su referencia.')
            else:
                messages.error(request, 'La acción solicitada no es válida.')
        except ValidationError as error:
            messages.error(request, error.messages[0])
        return redirect('financiero:factura_gasto_detalle', pk=factura.pk)
