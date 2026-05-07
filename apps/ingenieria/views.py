from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.contratos.models import Contrato
from apps.core.mixins import RoleRequiredMixin

from .models import DOCUMENTOS_POR_CATEGORIA, IngenieriaEstado, TorreContrato


class IngenieriaSeleccionarView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = 'ingenieria/seleccionar.html'
    context_object_name = 'contratos'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_queryset(self):
        return Contrato.objects.filter(unidad_negocio='CONSTRUCCION')


class IngenieriaBaseView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']
    categoria = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contrato = get_object_or_404(Contrato, pk=self.kwargs['contrato_id'])
        torres = TorreContrato.objects.filter(contrato=contrato)
        documentos = DOCUMENTOS_POR_CATEGORIA[self.categoria]

        # Agrupar documentos por subcategoría
        grupos = {}
        for codigo, subcategoria, nombre in documentos:
            if subcategoria not in grupos:
                grupos[subcategoria] = []
            grupos[subcategoria].append({'codigo': codigo, 'nombre': nombre})

        # Cargar estados existentes en un dict para acceso rápido
        estados_qs = IngenieriaEstado.objects.filter(
            torre__contrato=contrato,
            categoria=self.categoria,
        )
        estados_map = {
            (e.torre_id, e.documento_codigo): (e.estado, e.observacion)
            for e in estados_qs
        }

        # Construir filas de la tabla
        filas = []
        for torre in torres:
            celdas = {}
            for codigo, _, _ in documentos:
                estado, obs = estados_map.get((torre.id, codigo), (None, ''))
                celdas[codigo] = {'estado': estado, 'observacion': obs or ''}
            filas.append({'torre': torre, 'celdas': celdas})

        context.update({
            'contrato': contrato,
            'categoria': self.categoria,
            'grupos': grupos,
            'documentos': documentos,
            'filas': filas,
            'estados_choices': IngenieriaEstado.Estado.choices,
        })
        return context


class IngenieriaCivilView(IngenieriaBaseView):
    template_name = 'ingenieria/tabla.html'
    categoria = 'CIVIL'


class IngenieriaMontajeView(IngenieriaBaseView):
    template_name = 'ingenieria/tabla.html'
    categoria = 'MONTAJE'


class IngenieriaTendidoView(IngenieriaBaseView):
    template_name = 'ingenieria/tabla.html'
    categoria = 'TENDIDO'


class ActualizarEstadoView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def post(self, request, contrato_id):
        torre_id = request.POST.get('torre_id')
        documento_codigo = request.POST.get('documento_codigo')
        estado = request.POST.get('estado') or None
        categoria = request.POST.get('categoria')

        torre = get_object_or_404(TorreContrato, id=torre_id, contrato_id=contrato_id)

        obj, _ = IngenieriaEstado.objects.update_or_create(
            torre=torre,
            categoria=categoria,
            documento_codigo=documento_codigo,
            defaults={'estado': estado},
        )

        return HttpResponse(_render_celda(obj.estado, obj.observacion, torre_id, documento_codigo, categoria, contrato_id))


class GuardarObservacionView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def post(self, request, contrato_id):
        torre_id = request.POST.get('torre_id')
        documento_codigo = request.POST.get('documento_codigo')
        categoria = request.POST.get('categoria')
        observacion = request.POST.get('observacion', '').strip()

        torre = get_object_or_404(TorreContrato, id=torre_id, contrato_id=contrato_id)

        obj, _ = IngenieriaEstado.objects.get_or_create(
            torre=torre,
            categoria=categoria,
            documento_codigo=documento_codigo,
            defaults={'estado': None, 'observacion': observacion},
        )
        if not _:
            obj.observacion = observacion
            obj.save(update_fields=['observacion'])

        return HttpResponse(_render_celda(obj.estado, obj.observacion, torre_id, documento_codigo, categoria, contrato_id))


def _render_celda(estado, observacion, torre_id, documento_codigo, categoria, contrato_id):
    opciones = [
        (None, '-', 'bg-gray-100 dark:bg-gray-700 text-gray-500'),
        ('CUMPLE', 'C', 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300'),
        ('NO_CUMPLE', 'NC', 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300'),
        ('NO_APLICA', 'NA', 'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300'),
    ]
    siguiente = {None: 'CUMPLE', 'CUMPLE': 'NO_CUMPLE', 'NO_CUMPLE': 'NO_APLICA', 'NO_APLICA': None}
    prox_estado = siguiente[estado]

    label_map = {None: '-', 'CUMPLE': 'C', 'NO_CUMPLE': 'NC', 'NO_APLICA': 'NA'}
    color_map = {
        None: 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400',
        'CUMPLE': 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200 font-bold',
        'NO_CUMPLE': 'bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200 font-bold',
        'NO_APLICA': 'bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200 font-bold',
    }

    has_obs = bool(observacion)
    indicator = '<span class="absolute top-0 right-0 w-0 h-0 border-t-[6px] border-r-[6px] border-t-transparent border-r-orange-400"></span>' if has_obs else ''
    obs_safe = observacion.replace('"', '&quot;').replace("'", "&#39;")

    return f'''<div class="relative group celda-wrapper"
        data-torre-id="{torre_id}"
        data-codigo="{documento_codigo}"
        data-categoria="{categoria}"
        data-contrato-id="{contrato_id}"
        data-observacion="{obs_safe}">
      <button
        hx-post="/ingenieria/{contrato_id}/estado/"
        hx-vals='{{"torre_id": "{torre_id}", "documento_codigo": "{documento_codigo}", "categoria": "{categoria}", "estado": "{prox_estado or ""}"}}'
        hx-swap="outerHTML"
        hx-target="closest .celda-wrapper"
        class="w-full h-full min-w-[2.5rem] py-1 px-1 rounded text-xs transition-colors {color_map[estado]}"
      >{label_map[estado]}</button>
      {indicator}
    </div>'''
