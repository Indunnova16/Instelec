from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.contratos.models import Contrato
from apps.core.mixins import RoleRequiredMixin
from apps.ingenieria.models import TorreContrato

from .models import AmbientalTorre, PredialTorre

ALLOWED_ROLES = ['admin', 'director', 'coordinador', 'ing_residente']

# Campos del modelo PredialTorre: campo -> tipo
CAMPOS_PREDIAL = {
    'departamento':       'text',
    'municipio':          'text',
    'unidad_territorial': 'text',
    'predio':             'text',
    'propietario':        'text',
    'telefono':           'text',
    'socializacion':      'date',
    'acta_vecindad':      'date',
    'acta_acceso_com':    'date',
    'autorizacion_prop':  'date',
    'acta_acceso_priv':   'date',
    'liberacion_predial': 'bool',
    'observaciones':      'text',
}

# Campos del modelo AmbientalTorre: campo -> tipo
CAMPOS_AMBIENTAL = {
    'ahuyentamiento':        'date_or_na',    # "YYYY-MM-DD" o "NA" o ""
    'conteo_epifitas':       'date_or_na',
    'traslado_vivero':       'date_or_na',
    'reubicacion_epifitas':  'date_or_na',
    'aprov_sitio':           'date_or_na',
    'arqueologia_poligonos': 'choice',        # '', 'OK', 'NO_OK', 'NA'
    'adecuacion_accesos':    'decimal',       # km
    'accesos_intervenidos':  'decimal',       # km
    'avance_rescate':        'decimal',       # %
    'liberacion_pdo':        'bool',          # null/True/False
    'aprov_vano':            'bool',
    'rescate_arqueologico':  'bool',
    'observaciones':         'text',
}


# ── Selección de contrato ────────────────────────────────────────────────────

class PreliminaresSeleccionarView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    template_name = 'preliminares/seleccionar.html'
    context_object_name = 'contratos'
    allowed_roles = ALLOWED_ROLES

    def get_queryset(self):
        return Contrato.objects.filter(unidad_negocio='CONSTRUCCION')


# ── Socio-Predial ────────────────────────────────────────────────────────────

class PreliminaresPreDialView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = 'preliminares/predial.html'
    allowed_roles = ALLOWED_ROLES

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contrato = get_object_or_404(Contrato, pk=self.kwargs['contrato_id'])
        torres   = TorreContrato.objects.filter(contrato=contrato)

        # get_or_create predial record for each tower
        filas = []
        for torre in torres:
            pred, _ = PredialTorre.objects.get_or_create(torre=torre)
            filas.append({'torre': torre, 'pred': pred})

        context.update({
            'contrato': contrato,
            'categoria': 'PREDIAL',
            'filas': filas,
        })
        return context


class ActualizarCampoPredialView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ALLOWED_ROLES

    def post(self, request, contrato_id):
        torre_id = request.POST.get('torre_id')
        campo    = request.POST.get('campo')
        valor    = request.POST.get('valor', '').strip()

        if campo not in CAMPOS_PREDIAL:
            return HttpResponse(status=400)

        torre = get_object_or_404(TorreContrato, id=torre_id, contrato_id=contrato_id)
        pred, _ = PredialTorre.objects.get_or_create(torre=torre)

        tipo = CAMPOS_PREDIAL[campo]
        if tipo == 'date':
            setattr(pred, campo, valor or None)
        elif tipo == 'bool':
            setattr(pred, campo, True if valor == '1' else (False if valor == '0' else None))
        else:
            setattr(pred, campo, valor)

        pred.save(update_fields=[campo])
        return HttpResponse(status=204)


# ── Socio-Ambiental ──────────────────────────────────────────────────────────

class PreliminaresAmbientalView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = 'preliminares/ambiental_editable.html'
    allowed_roles = ALLOWED_ROLES

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contrato = get_object_or_404(Contrato, pk=self.kwargs['contrato_id'])
        torres   = TorreContrato.objects.filter(contrato=contrato)

        filas = []
        for torre in torres:
            amb, _ = AmbientalTorre.objects.get_or_create(torre=torre)
            filas.append({'torre': torre, 'amb': amb})

        context.update({
            'contrato': contrato,
            'categoria': 'AMBIENTAL',
            'filas': filas,
        })
        return context


class ActualizarCampoAmbientalView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ALLOWED_ROLES

    def post(self, request, contrato_id):
        from django.template.loader import render_to_string

        torre_id = request.POST.get('torre_id')
        campo    = request.POST.get('campo')
        valor    = request.POST.get('valor', '').strip()

        if campo not in CAMPOS_AMBIENTAL:
            return HttpResponse(status=400)

        torre = get_object_or_404(TorreContrato, id=torre_id, contrato_id=contrato_id)
        amb, _ = AmbientalTorre.objects.get_or_create(torre=torre)

        tipo = CAMPOS_AMBIENTAL[campo]
        try:
            if tipo == 'date_or_na':
                setattr(amb, campo, valor or '')
            elif tipo == 'choice':
                setattr(amb, campo, valor or '')
            elif tipo == 'decimal':
                setattr(amb, campo, float(valor) if valor else None)
            elif tipo == 'bool':
                setattr(amb, campo, True if valor == '1' else (False if valor == '0' else None))
            elif tipo == 'text':
                setattr(amb, campo, valor)

            amb.save(update_fields=[campo])
        except (ValueError, TypeError):
            return HttpResponse(status=400)

        # Renderizar celda actualizada
        html = render_to_string('preliminares/partials/_campo_ambiental.html', {
            'campo': campo,
            'valor': getattr(amb, campo),
            'tipo': tipo,
            'torre_id': torre_id,
            'contrato_id': contrato_id,
        })
        return HttpResponse(html)
