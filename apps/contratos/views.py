"""
Views for contract management.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.mixins import RoleRequiredMixin

from .forms import ContratoForm
from .models import Contrato


class ContratoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List contracts grouped by business unit."""
    model = Contrato
    template_name = 'contratos/lista.html'
    context_object_name = 'contratos'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        qs = super().get_queryset()
        unidad = self.request.GET.get('unidad')
        if unidad in ('MANTENIMIENTO', 'CONSTRUCCION'):
            qs = qs.filter(unidad_negocio=unidad)
        estado = self.request.GET.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unidad_filter'] = self.request.GET.get('unidad', '')
        context['estado_filter'] = self.request.GET.get('estado', '')
        context['contratos_mantenimiento'] = Contrato.objects.filter(
            unidad_negocio='MANTENIMIENTO'
        )
        context['contratos_construccion'] = Contrato.objects.filter(
            unidad_negocio='CONSTRUCCION'
        )
        context['total_contratos'] = Contrato.objects.count()
        context['total_activos'] = Contrato.objects.filter(estado='ACTIVO').count()
        return context


def _sincronizar_torres(contrato):
    """Genera torres T1..TN si numero_torres está definido."""
    from apps.ingenieria.models import TorreContrato
    n = contrato.numero_torres
    if not n:
        return
    existentes = set(contrato.torres.values_list('nombre', flat=True))
    nuevas = [f"T{i}" for i in range(1, n + 1) if f"T{i}" not in existentes]
    TorreContrato.objects.bulk_create([
        TorreContrato(contrato=contrato, nombre=nombre, orden=int(nombre[1:]))
        for nombre in nuevas
    ])


class ContratoCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    """Create a new contract."""
    model = Contrato
    form_class = ContratoForm
    template_name = 'contratos/form.html'
    success_url = reverse_lazy('contratos:lista')
    allowed_roles = ['admin', 'director']

    def form_valid(self, form):
        response = super().form_valid(form)
        _sincronizar_torres(self.object)
        messages.success(self.request, 'Contrato creado exitosamente.')
        return response


class ContratoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Update an existing contract."""
    model = Contrato
    form_class = ContratoForm
    template_name = 'contratos/form.html'
    success_url = reverse_lazy('contratos:lista')
    allowed_roles = ['admin', 'director']

    def form_valid(self, form):
        response = super().form_valid(form)
        _sincronizar_torres(self.object)
        messages.success(self.request, 'Contrato actualizado exitosamente.')
        return response


class ContratoDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    """Delete a contract."""
    model = Contrato
    success_url = reverse_lazy('contratos:lista')
    allowed_roles = ['admin']

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Contrato eliminado exitosamente.')
        return super().delete(request, *args, **kwargs)
