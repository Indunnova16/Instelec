"""
Views for field records.
"""
from typing import Any

from django.db.models import QuerySet, Q
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from apps.core.mixins import HTMXMixin, RoleRequiredMixin
from .models import RegistroCampo, Evidencia, ReporteDano, FotoDano, Procedimiento, RegistroAvance


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

        # Campo users only see their own records
        if self.request.user.is_campo:
            qs = qs.filter(usuario=self.request.user)

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
    """
    List damage reports with filters.
    Actualizado: 1 abril 2026
    """
    model = ReporteDano
    template_name = 'campo/lista_danos.html'
    context_object_name = 'reportes'
    paginate_by = 20
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self) -> QuerySet[ReporteDano]:
        qs = super().get_queryset().select_related('usuario', 'linea', 'torre').prefetch_related('fotos')

        # Filtro por línea
        linea_id = self.request.GET.get('linea')
        if linea_id:
            qs = qs.filter(linea_id=linea_id)

        # Filtro por severidad
        severidad = self.request.GET.get('severidad')
        if severidad:
            qs = qs.filter(severidad=severidad)

        # Filtro por tipo
        tipo = self.request.GET.get('tipo')
        if tipo:
            qs = qs.filter(tipo=tipo)

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Datos para filtros
        from apps.lineas.models import Linea
        context['lineas'] = Linea.objects.filter(activa=True).order_by('codigo')
        context['tipos'] = ReporteDano.Tipo.choices
        context['severidades'] = ReporteDano.Severidad.choices

        # Valores actuales de filtros
        context['filtros'] = {
            'linea': self.request.GET.get('linea', ''),
            'severidad': self.request.GET.get('severidad', ''),
            'tipo': self.request.GET.get('tipo', ''),
        }

        return context


class ReporteDanoDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Detail view for a damage report."""
    model = ReporteDano
    template_name = 'campo/detalle_dano.html'
    context_object_name = 'reporte'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self):
        return super().get_queryset().select_related('usuario', 'linea', 'torre').prefetch_related('fotos')


class ProcedimientoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """
    List uploaded procedure documents with search functionality.
    Actualizado: 1 abril 2026
    """
    model = Procedimiento
    template_name = 'campo/procedimientos_lista.html'
    context_object_name = 'procedimientos'
    paginate_by = 20
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_queryset(self) -> QuerySet[Procedimiento]:
        qs = super().get_queryset().select_related('subido_por')

        # Búsqueda por término
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(titulo__icontains=q) |
                Q(descripcion__icontains=q) |
                Q(nombre_original__icontains=q) |
                Q(tipo_archivo__icontains=q)
            )

        return qs.order_by('-created_at')


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


class ProcedimientoViewerView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """
    View for displaying/viewing a procedure document.
    Agregado: 1 abril 2026

    Para PDFs, usa visualización inline.
    Para otros formatos, ofrece descarga.
    """
    model = Procedimiento
    template_name = 'campo/procedimiento_viewer.html'
    context_object_name = 'procedimiento'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor', 'liniero']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        procedimiento = self.get_object()

        # Verificar si es PDF para visualización inline
        context['es_pdf'] = procedimiento.es_pdf
        context['url_archivo'] = procedimiento.archivo.url if procedimiento.archivo else None

        return context


class AvancesCuadrillaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """
    Vista de avances de vanos para cuadrillas en campo.
    Agregado: 1 abril 2026

    Permite a los miembros de cuadrilla ver y marcar el estado de vanos asignados.
    """
    template_name = 'campo/avances_cuadrilla.html'
    allowed_roles = ['supervisor', 'liniero', 'auxiliar']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Obtener cuadrilla actual del usuario
        from apps.cuadrillas.models import CuadrillaMiembro

        miembro = CuadrillaMiembro.objects.filter(
            usuario=self.request.user,
            activo=True,
            cuadrilla__activa=True
        ).select_related('cuadrilla').first()

        if not miembro:
            context['vanos'] = []
            context['mensaje'] = 'No estás asignado a ninguna cuadrilla activa'
            return context

        cuadrilla = miembro.cuadrilla
        context['cuadrilla'] = cuadrilla

        # Obtener actividad activa de la cuadrilla
        from apps.actividades.models import Actividad
        actividad_activa = Actividad.objects.filter(
            cuadrillas=cuadrilla,
            estado__in=['PROGRAMADA', 'EN_CURSO']
        ).select_related('linea', 'tipo_actividad', 'tramo').first()

        if not actividad_activa:
            context['vanos'] = []
            context['mensaje'] = 'No hay actividades asignadas a tu cuadrilla'
            return context

        context['actividad'] = actividad_activa

        # Obtener vanos de esta cuadrilla
        from .models import AvanceVano

        vanos_propios = actividad_activa.avances_vanos.filter(
            cuadrilla_asignada_original=cuadrilla
        ).select_related('torre_inicio', 'torre_fin', 'marcado_por', 'revisado_por')

        # Vanos de otras cuadrillas que esta cuadrilla está ayudando
        vanos_apoyo = actividad_activa.avances_vanos.filter(
            cuadrilla=cuadrilla
        ).exclude(
            cuadrilla_asignada_original=cuadrilla
        ).select_related('torre_inicio', 'torre_fin', 'cuadrilla_asignada_original', 'marcado_por')

        context['vanos_propios'] = vanos_propios
        context['vanos_apoyo'] = vanos_apoyo

        # Calcular estadísticas
        total_vanos = vanos_propios.count()
        ejecutados = vanos_propios.filter(estado='ejecutado').count()
        sin_permiso = vanos_propios.filter(estado='sin_permiso').count()
        pendientes = vanos_propios.filter(estado='pendiente').count()

        context['estadisticas'] = {
            'total': total_vanos,
            'ejecutados': ejecutados,
            'sin_permiso': sin_permiso,
            'pendientes': pendientes,
            'porcentaje': round((ejecutados / total_vanos * 100) if total_vanos > 0 else 0, 1)
        }

        return context


class MarcarVanoView(LoginRequiredMixin, View):
    """
    Vista HTMX para marcar el estado de un vano.
    Agregado: 1 abril 2026
    """

    def post(self, request, vano_id):
        from django.shortcuts import get_object_or_404, render
        from django.http import HttpResponse
        from .models import AvanceVano

        vano = get_object_or_404(AvanceVano, id=vano_id)
        nuevo_estado = request.POST.get('estado')
        observaciones = request.POST.get('observaciones', '')

        # Validar que usuario pertenece a la cuadrilla asignada
        from apps.cuadrillas.models import CuadrillaMiembro
        es_miembro = CuadrillaMiembro.objects.filter(
            usuario=request.user,
            cuadrilla=vano.cuadrilla,
            activo=True
        ).exists()

        if not es_miembro and request.user.rol not in ['admin', 'director', 'coordinador']:
            return HttpResponse('No autorizado', status=403)

        # Confirmación para evitar errores (solo para ejecutado)
        confirmar = request.POST.get('confirmar', 'false') == 'true'
        if not confirmar and nuevo_estado == 'ejecutado':
            # Retornar modal de confirmación
            return render(request, 'campo/partials/confirmar_vano.html', {
                'vano': vano
            })

        # Actualizar estado
        if nuevo_estado in dict(AvanceVano.Estado.choices):
            vano.estado = nuevo_estado
            vano.marcado_por = request.user
            vano.fecha_marcado = timezone.now()
            vano.observaciones = observaciones
            vano.save()

            # Si es ejecutado, recalcular avance de actividad
            if nuevo_estado == 'ejecutado':
                vano.actividad.recalcular_avance()

        # Retornar partial actualizado
        return render(request, 'campo/partials/vano_item.html', {
            'vano': vano
        })


# ==================== REGISTRO DE AVANCES ====================

class RegistroAvanceCreateView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """
    Formulario para registrar avances en torres.
    - Trabajadores: ven solo su línea y cuadrilla asignadas
    - Administradores: pueden seleccionar cualquier línea, torre y cuadrilla
    """
    template_name = 'campo/avance_registrar.html'
    allowed_roles = ['liniero', 'auxiliar', 'supervisor', 'admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
        es_admin = usuario.rol in ['admin', 'director', 'coordinador']

        if es_admin:
            # Administradores: pueden ver todas las líneas y cuadrillas
            from apps.lineas.models import Linea, Torre
            from apps.cuadrillas.models import Cuadrilla

            context['es_admin'] = True
            context['lineas'] = Linea.objects.filter(activa=True).order_by('codigo')
            context['cuadrillas'] = Cuadrilla.objects.filter(activa=True).order_by('nombre')
            context['torres'] = Torre.objects.select_related('linea').order_by('linea', 'numero')
        else:
            # Trabajadores: ven solo su línea y cuadrilla asignadas
            from apps.cuadrillas.models import CuadrillaMiembro
            miembro = CuadrillaMiembro.objects.filter(
                usuario=usuario,
                activo=True
            ).select_related('cuadrilla').first()

            if not miembro:
                context['error'] = 'No estás asignado a ninguna cuadrilla activa.'
                return context

            cuadrilla = miembro.cuadrilla
            context['cuadrilla'] = cuadrilla

            # Obtener línea asignada a la cuadrilla
            if not cuadrilla.linea_asignada:
                context['error'] = 'Tu cuadrilla no tiene una línea asignada.'
                return context

            linea = cuadrilla.linea_asignada
            context['linea'] = linea

            # Obtener torres de la línea
            from apps.lineas.models import Torre
            torres = Torre.objects.filter(linea=linea).order_by('numero')
            context['torres'] = torres

        # Tipos de avance
        context['tipos_avance'] = RegistroAvance.TipoAvance.choices

        return context

    def post(self, request, *args, **kwargs):
        """Crear registro de avance."""
        from django.shortcuts import redirect
        from django.contrib import messages
        from apps.cuadrillas.models import CuadrillaMiembro, Cuadrilla
        from apps.lineas.models import Torre, Linea
        from uuid import UUID

        usuario = request.user
        es_admin = usuario.rol in ['admin', 'director', 'coordinador']

        # Obtener datos del formulario
        torre_id = request.POST.get('torre_id', '').strip()
        tipo_avance = request.POST.get('tipo_avance', 'completo').strip()
        observaciones = request.POST.get('observaciones', '').strip()
        porcentaje = request.POST.get('porcentaje', '100').strip()
        cuadrilla_id = request.POST.get('cuadrilla_id', '').strip()  # Para admins

        # Validaciones
        if not torre_id:
            messages.error(request, 'Debes seleccionar una torre.')
            return redirect('campo:avance_registrar')

        try:
            torre_uuid = UUID(torre_id)
            torre = Torre.objects.get(id=torre_uuid)
        except (ValueError, TypeError):
            messages.error(request, 'Torre inválida.')
            return redirect('campo:avance_registrar')
        except Torre.DoesNotExist:
            messages.error(request, 'Torre no encontrada.')
            return redirect('campo:avance_registrar')

        linea = torre.linea

        # Determinar cuadrilla
        if es_admin:
            # Los admins pueden seleccionar cuadrilla
            if cuadrilla_id:
                try:
                    cuadrilla_uuid = UUID(cuadrilla_id)
                    cuadrilla = Cuadrilla.objects.get(id=cuadrilla_uuid)
                except (ValueError, TypeError, Cuadrilla.DoesNotExist):
                    messages.error(request, 'Cuadrilla inválida.')
                    return redirect('campo:avance_registrar')
            else:
                # Si admin no selecciona cuadrilla, es null (avance general)
                cuadrilla = None
        else:
            # Trabajadores: deben estar en una cuadrilla
            miembro = CuadrillaMiembro.objects.filter(
                usuario=usuario,
                activo=True
            ).select_related('cuadrilla', 'cuadrilla__linea_asignada').first()

            if not miembro:
                messages.error(request, 'No estás asignado a ninguna cuadrilla activa.')
                return redirect('campo:avance_registrar')

            cuadrilla = miembro.cuadrilla
            linea_cuadrilla = cuadrilla.linea_asignada

            if not linea_cuadrilla:
                messages.error(request, 'Tu cuadrilla no tiene una línea asignada.')
                return redirect('campo:avance_registrar')

            # Validar que la torre pertenece a la línea de la cuadrilla
            if torre.linea_id != linea_cuadrilla.id:
                messages.error(request, 'La torre no pertenece a tu línea asignada.')
                return redirect('campo:avance_registrar')

            linea = linea_cuadrilla

        # Validar porcentaje
        try:
            porcentaje = int(porcentaje)
            if not (0 <= porcentaje <= 100):
                porcentaje = 100
        except (ValueError, TypeError):
            porcentaje = 100

        # Validar tipo de avance
        tipos_validos = dict(RegistroAvance.TipoAvance.choices)
        if tipo_avance not in tipos_validos:
            tipo_avance = 'completo'

        # Crear registro
        try:
            RegistroAvance.objects.create(
                usuario=usuario,
                cuadrilla=cuadrilla,
                linea=linea,
                torre=torre,
                tipo_avance=tipo_avance,
                observaciones=observaciones,
                porcentaje=porcentaje
            )
            messages.success(
                request,
                f'Avance registrado en Torre {torre.numero} exitosamente.'
            )
        except Exception as e:
            messages.error(request, f'Error al registrar avance: {str(e)}')

        return redirect('campo:avance_registrar')


class MisAvancesListView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, ListView):
    """
    Lista de avances registrados.
    Usuarios de campo ven solo sus propios avances.
    Administradores ven todos los avances con filtros.
    """
    model = RegistroAvance
    template_name = 'campo/avances_lista.html'
    partial_template_name = 'campo/partials/avances_lista.html'
    context_object_name = 'avances'
    paginate_by = 20
    allowed_roles = ['liniero', 'auxiliar', 'supervisor', 'admin', 'director', 'coordinador']

    def get_queryset(self) -> QuerySet:
        qs = RegistroAvance.objects.select_related(
            'usuario', 'cuadrilla', 'linea', 'torre'
        )

        # Usuario de campo solo ve sus propios avances
        if self.request.user.is_campo:
            qs = qs.filter(usuario=self.request.user)

        # Filtros opcionales
        linea = self.request.GET.get('linea')
        if linea:
            from uuid import UUID
            try:
                UUID(linea)
                qs = qs.filter(linea_id=linea)
            except ValueError:
                pass

        cuadrilla = self.request.GET.get('cuadrilla')
        if cuadrilla:
            from uuid import UUID
            try:
                UUID(cuadrilla)
                qs = qs.filter(cuadrilla_id=cuadrilla)
            except ValueError:
                pass

        tipo_avance = self.request.GET.get('tipo_avance')
        if tipo_avance:
            qs = qs.filter(tipo_avance=tipo_avance)

        return qs.order_by('-fecha_avance')

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Agregar líneas y cuadrillas para los filtros
        from apps.lineas.models import Linea
        from apps.cuadrillas.models import Cuadrilla

        context['lineas'] = Linea.objects.filter(activa=True).order_by('codigo')
        context['cuadrillas'] = Cuadrilla.objects.filter(activa=True).order_by('nombre')

        return context
