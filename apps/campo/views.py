"""
Views for field records.
"""
from typing import Any

from django.db.models import QuerySet
from django.views.generic import ListView, DetailView, CreateView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import RegistroCampo, Evidencia, ReporteDano, FotoDano, Procedimiento


class RegistroListView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, ListView):
    """List field records."""
    model = RegistroCampo
    template_name = 'campo/lista.html'
    partial_template_name = 'campo/partials/lista_registros.html'
    context_object_name = 'registros'
    paginate_by = 20
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self) -> QuerySet[RegistroCampo]:
        qs = super().get_queryset().select_related(
            'actividad',
            'actividad__linea',
            'actividad__torre',
            'actividad__tipo_actividad',
            'usuario'
        ).prefetch_related('evidencias')

        # Filters
        linea = self.request.GET.get('linea')
        if linea:
            from uuid import UUID
            try:
                UUID(linea)
                qs = qs.filter(actividad__linea_id=linea)
            except ValueError:
                pass  # Invalid UUID, ignore filter

        sincronizado = self.request.GET.get('sincronizado')
        if sincronizado:
            qs = qs.filter(sincronizado=sincronizado == 'true')

        return qs


class RegistroDetailView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """Detail view for a field record."""
    model = RegistroCampo
    template_name = 'campo/detalle.html'
    context_object_name = 'registro'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['evidencias_antes'] = self.object.evidencias.filter(tipo='ANTES')
        context['evidencias_durante'] = self.object.evidencias.filter(tipo='DURANTE')
        context['evidencias_despues'] = self.object.evidencias.filter(tipo='DESPUES')
        context['tipos_vegetacion'] = RegistroCreateView.TIPOS_VEGETACION
        return context


class EvidenciasView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """View for listing evidence photos."""
    model = Evidencia
    template_name = 'campo/evidencias.html'
    context_object_name = 'evidencias'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self) -> QuerySet[Evidencia]:
        return Evidencia.objects.filter(
            registro_campo_id=self.kwargs['pk']
        ).order_by('tipo', 'fecha_captura')

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['registro'] = RegistroCampo.objects.get(pk=self.kwargs['pk'])
        return context


class RegistroCreateView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """View for creating a new REM Tipo A field record."""
    template_name = 'campo/crear.html'
    partial_template_name = 'campo/partials/form_registro.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    TIPOS_VEGETACION = [
        ('arboles_aislados', 'Arboles aislados'),
        ('bosque_plantado', 'Bosque plantado'),
        ('bosque_natural', 'Bosque natural'),
        ('cerca_viva', 'Cerca viva'),
        ('cultivo_agricola', 'Cultivo agricola'),
    ]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        from apps.lineas.models import Linea

        context['lineas'] = Linea.objects.filter(activa=True)
        context['tipos_vegetacion'] = self.TIPOS_VEGETACION
        context['fecha_hoy'] = timezone.now().strftime('%Y-%m-%d')

        return context

    def post(self, request, *args, **kwargs):
        import json
        from django.http import HttpResponseRedirect
        from apps.actividades.models import Actividad, TipoActividad
        from apps.lineas.models import Linea, Torre

        linea_id = request.POST.get('linea')
        torre_desde_id = request.POST.get('torre_desde')
        torre_hasta_id = request.POST.get('torre_hasta')
        fecha = request.POST.get('fecha')
        observaciones = request.POST.get('observaciones', '')

        if not linea_id or not torre_desde_id or not torre_hasta_id or not fecha:
            context = self.get_context_data(**kwargs)
            context['error'] = 'Debe seleccionar linea, torres y fecha'
            return self.render_to_response(context)

        try:
            linea = Linea.objects.get(pk=linea_id)
            torre_desde = Torre.objects.get(pk=torre_desde_id)
            torre_hasta = Torre.objects.get(pk=torre_hasta_id)
        except (Linea.DoesNotExist, Torre.DoesNotExist):
            context = self.get_context_data(**kwargs)
            context['error'] = 'Linea o torre no encontrada'
            return self.render_to_response(context)

        # Find or create SERVIDUMBRE activity type
        tipo_servidumbre, _ = TipoActividad.objects.get_or_create(
            categoria='SERVIDUMBRE',
            defaults={
                'codigo': 'REM-SERV',
                'nombre': 'Mantenimiento Servidumbre REM',
                'activo': True,
            }
        )

        # Find existing active activity or create a new one
        actividad = Actividad.objects.filter(
            linea=linea,
            torre=torre_desde,
            tipo_actividad=tipo_servidumbre,
            estado__in=['PENDIENTE', 'PROGRAMADA', 'EN_CURSO'],
        ).first()

        if not actividad:
            actividad = Actividad.objects.create(
                linea=linea,
                torre=torre_desde,
                tipo_actividad=tipo_servidumbre,
                fecha_programada=fecha,
                estado='EN_CURSO',
            )
        elif actividad.estado == 'PENDIENTE':
            actividad.estado = 'EN_CURSO'
            actividad.save(update_fields=['estado', 'updated_at'])

        # Build vegetation type data
        vegetacion_tipo = {}
        for veg_key, _ in self.TIPOS_VEGETACION:
            vegetacion_tipo[veg_key] = request.POST.get(f'veg_{veg_key}', '')

        # Parse vegetation report JSON
        reporte_vegetacion = []
        try:
            reporte_raw = request.POST.get('reporte_vegetacion_json', '[]')
            reporte_vegetacion = json.loads(reporte_raw)
            # Filter out empty rows
            reporte_vegetacion = [
                row for row in reporte_vegetacion
                if row.get('especie', '').strip()
            ]
        except (json.JSONDecodeError, TypeError):
            pass

        # Build datos_formulario JSON
        datos_formulario = {
            'tipo_formulario': 'REM_TIPO_A',
            'vano_torre_desde': torre_desde.numero,
            'vano_torre_hasta': torre_hasta.numero,
            'fecha': fecha,
            'diligenciado_por': request.user.get_full_name(),
            'ahuyentamiento_fauna': request.POST.get('ahuyentamiento_fauna', ''),
            'limpieza': {
                'rastrojo': request.POST.get('limpieza_rastrojo') == 'true',
                'cunetas': request.POST.get('limpieza_cunetas') == 'true',
            },
            'vegetacion_tipo': vegetacion_tipo,
            'marcacion_arboles': {
                'amarillo_poda': request.POST.get('marcacion_amarillo_poda') == 'true',
                'blanco_tala': request.POST.get('marcacion_blanco_tala') == 'true',
            },
            'trabajo_ejecutado': request.POST.get('trabajo_ejecutado', ''),
            'contacto_permiso': {
                'vereda': request.POST.get('contacto_vereda', ''),
                'municipio': request.POST.get('contacto_municipio', ''),
                'propietario': request.POST.get('contacto_propietario', ''),
                'finca': request.POST.get('contacto_finca', ''),
                'cedula': request.POST.get('contacto_cedula', ''),
                'telefono': request.POST.get('contacto_telefono', ''),
            },
            'reporte_vegetacion': reporte_vegetacion,
            'inspecciones': {
                'electromecanica': request.POST.get('insp_electromecanica', ''),
                'sitio_torre': request.POST.get('insp_sitio_torre', ''),
                'senalizacion': request.POST.get('insp_senalizacion', ''),
                'desviadores_vuelo': request.POST.get('insp_desviadores', ''),
                'cauces_naturales': request.POST.get('insp_cauces', ''),
                'residuos': request.POST.get('insp_residuos', ''),
            },
        }

        registro = RegistroCampo.objects.create(
            actividad=actividad,
            usuario=request.user,
            fecha_inicio=timezone.now(),
            observaciones=observaciones,
            datos_formulario=datos_formulario,
            sincronizado=True,
            fecha_sincronizacion=timezone.now()
        )

        # Handle photo uploads (Antes / Durante / Despues)
        self._save_evidencias(request, registro)

        return HttpResponseRedirect(reverse_lazy('campo:detalle', kwargs={'pk': registro.pk}))


    @staticmethod
    def _save_evidencias(request, registro):
        """Save uploaded photos as Evidencia records."""
        from django.core.files.storage import default_storage
        import os

        TIPO_MAP = {
            'fotos_antes': 'ANTES',
            'fotos_durante': 'DURANTE',
            'fotos_despues': 'DESPUES',
        }

        for field_name, tipo in TIPO_MAP.items():
            fotos = request.FILES.getlist(field_name)
            for foto in fotos:
                if not foto.content_type.startswith('image/'):
                    continue
                # Save file to storage (GCS in production, local in dev)
                ext = os.path.splitext(foto.name)[1].lower() or '.jpg'
                path = f'campo/evidencias/{registro.pk}/{tipo.lower()}/{foto.name}'
                saved_path = default_storage.save(path, foto)
                url = default_storage.url(saved_path)

                Evidencia.objects.create(
                    registro_campo=registro,
                    tipo=tipo,
                    url_original=url,
                    fecha_captura=timezone.now(),
                )


class ReportarDanoCreateView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """View for creating a damage report with geolocation."""
    template_name = 'campo/reportar_dano.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.lineas.models import Linea
        context['lineas'] = Linea.objects.filter(activa=True)
        context['tipos_dano'] = ReporteDano.TipoDano.choices
        context['severidades'] = ReporteDano.Severidad.choices
        return context

    def post(self, request, *args, **kwargs):
        from decimal import Decimal, InvalidOperation
        from django.http import HttpResponseRedirect

        descripcion = request.POST.get('descripcion', '').strip()
        latitud_raw = request.POST.get('latitud', '').strip()
        longitud_raw = request.POST.get('longitud', '').strip()
        linea_id = request.POST.get('linea', '').strip() or None
        torre_id = request.POST.get('torre', '').strip() or None
        tipo_dano = request.POST.get('tipo_dano', 'OTRO').strip()
        severidad = request.POST.get('severidad', 'MEDIA').strip()

        if not descripcion:
            context = self.get_context_data(**kwargs)
            context['error'] = 'Debe ingresar una descripción del daño'
            return self.render_to_response(context)

        latitud = None
        longitud = None
        if latitud_raw and longitud_raw:
            try:
                latitud = Decimal(latitud_raw)
                longitud = Decimal(longitud_raw)
            except InvalidOperation:
                pass

        reporte = ReporteDano.objects.create(
            usuario=request.user,
            descripcion=descripcion,
            latitud=latitud,
            longitud=longitud,
            linea_id=linea_id,
            torre_id=torre_id,
            tipo_dano=tipo_dano,
            severidad=severidad,
        )

        # Handle photo uploads
        fotos = request.FILES.getlist('fotos')
        for foto in fotos:
            FotoDano.objects.create(
                reporte=reporte,
                imagen=foto,
            )

        return HttpResponseRedirect(reverse_lazy('campo:detalle_dano', kwargs={'pk': reporte.pk}))


class ReportesDanoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List damage reports."""
    model = ReporteDano
    template_name = 'campo/lista_danos.html'
    context_object_name = 'reportes'
    paginate_by = 20
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self) -> QuerySet[ReporteDano]:
        return super().get_queryset().select_related('usuario', 'linea', 'torre')


class ReporteDanoDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Detail view for a damage report."""
    model = ReporteDano
    template_name = 'campo/detalle_dano.html'
    context_object_name = 'reporte'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self):
        return super().get_queryset().select_related('usuario', 'linea', 'torre').prefetch_related('fotos')


class ProcedimientoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List uploaded procedure documents."""
    model = Procedimiento
    template_name = 'campo/procedimientos_lista.html'
    context_object_name = 'procedimientos'
    paginate_by = 20
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self) -> QuerySet[Procedimiento]:
        return super().get_queryset().select_related('subido_por')


class ProcedimientoCreateView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """View for uploading a new procedure document."""
    template_name = 'campo/procedimiento_crear.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    ALLOWED_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.webp'}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    def post(self, request, *args, **kwargs):
        import os
        from django.http import HttpResponseRedirect

        titulo = request.POST.get('titulo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        archivo = request.FILES.get('archivo')

        if not titulo or not archivo:
            context = self.get_context_data(**kwargs)
            context['error'] = 'Debe ingresar un título y seleccionar un archivo.'
            return self.render_to_response(context)

        _, ext = os.path.splitext(archivo.name)
        if ext.lower() not in self.ALLOWED_EXTENSIONS:
            context = self.get_context_data(**kwargs)
            context['error'] = f'Tipo de archivo no permitido: {ext}'
            return self.render_to_response(context)

        if archivo.size > self.MAX_FILE_SIZE:
            context = self.get_context_data(**kwargs)
            context['error'] = 'El archivo excede el tamaño máximo permitido (50 MB).'
            return self.render_to_response(context)

        Procedimiento.objects.create(
            titulo=titulo,
            descripcion=descripcion,
            archivo=archivo,
            nombre_original=archivo.name,
            tipo_archivo=archivo.content_type or '',
            tamanio=archivo.size,
            subido_por=request.user,
        )

        return HttpResponseRedirect(reverse_lazy('campo:procedimientos'))
