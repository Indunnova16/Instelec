"""
Views for contract management.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.mixins import RoleRequiredMixin
from apps.core.utils import get_unidad_negocio

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
        # GET param overrides session filter; fallback to session ('TODOS' = sin filtro).
        unidad = self.request.GET.get('unidad') or get_unidad_negocio(self.request)
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
    """Sincroniza el set de torres T1..TN del contrato (soft-delete).

    - Faltantes → crea TorreContrato + PredialTorre + AmbientalTorre.
    - Sobrantes activas → marca archivada=True (preserva histórico).
    - Reaparecidas (T6 archivada y vuelve a estar en el rango) → archivada=False.
    """
    from apps.ingenieria.models import TorreContrato
    from apps.preliminares.models import AmbientalTorre, PredialTorre

    n = contrato.numero_torres
    if not n:
        return

    esperadas = {f"T{i}": i for i in range(1, n + 1)}
    existentes = {t.nombre: t for t in contrato.torres.all()}

    # 1) Crear faltantes.
    nuevas_objs = [
        TorreContrato(contrato=contrato, nombre=nombre, orden=orden)
        for nombre, orden in esperadas.items()
        if nombre not in existentes
    ]
    if nuevas_objs:
        TorreContrato.objects.bulk_create(nuevas_objs)
        # bulk_create no dispara signals: crear Predial/Ambiental manualmente.
        nuevas_db = TorreContrato.objects.filter(
            contrato=contrato,
            nombre__in=[t.nombre for t in nuevas_objs],
        )
        PredialTorre.objects.bulk_create(
            [PredialTorre(torre=t) for t in nuevas_db],
            ignore_conflicts=True,
        )
        AmbientalTorre.objects.bulk_create(
            [AmbientalTorre(torre=t) for t in nuevas_db],
            ignore_conflicts=True,
        )

    # 2) Archivar sobrantes activas.
    a_archivar = [t.pk for t in existentes.values()
                  if t.nombre not in esperadas and not t.archivada]
    if a_archivar:
        TorreContrato.objects.filter(pk__in=a_archivar).update(archivada=True)

    # 3) Reactivar torres archivadas que volvieron al rango.
    a_reactivar = [t.pk for t in existentes.values()
                   if t.nombre in esperadas and t.archivada]
    if a_reactivar:
        TorreContrato.objects.filter(pk__in=a_reactivar).update(archivada=False)


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
