"""
Core views.
"""
import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from .forms_roles import RoleForm
from .mixins import HTMXMixin, RoleRequiredMixin
from .models import Role, RoleModuloPermiso
from .permissions import TODOS_SUBMODULOS
from .utils import set_unidad_negocio

logger = logging.getLogger(__name__)


@login_required
@require_POST
def set_unidad_negocio_view(request: HttpRequest) -> HttpResponse:
    """Persiste la unidad de negocio (`MANTENIMIENTO`/`CONSTRUCCION`/`TODOS`) en la sesión."""
    valor = request.POST.get('unidad_negocio', '')
    normalizada = set_unidad_negocio(request, valor)
    return JsonResponse({'unidad_negocio': normalizada})


class HomeView(LoginRequiredMixin, TemplateView):
    """Home page / Dashboard."""
    template_name = 'core/home.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_campo:
            from django.shortcuts import redirect
            return redirect('campo:lista')
        # RBAC #44: redirigir a módulo único si el usuario solo tiene uno
        if request.user.is_authenticated:
            from django.shortcuts import redirect
            from apps.core.permissions import (
                user_modulos,
                MODULO_CONSTRUCCION,
                MODULO_MANTENIMIENTO,
                MODULO_CONFIG,
            )
            modulos = user_modulos(request.user)
            # Solo redirigir si NO es admin general (que debe ver el home completo)
            if MODULO_CONFIG not in modulos:
                if modulos == {MODULO_CONSTRUCCION}:
                    return redirect('/construccion/')
                if modulos == {MODULO_MANTENIMIENTO}:
                    return redirect('actividades:lista')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Add dashboard data based on user role
        if user.rol in ['admin', 'director', 'coordinador']:
            context['show_full_dashboard'] = True
        else:
            context['show_full_dashboard'] = False

        return context


def health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for Cloud Run.

    Returns status of:
    - Database connection (with timeout)
    - Cache connection (Redis) - critical for Celery
    - Storage connection (GCS) - actual access verification

    All checks have a 5-second timeout to prevent blocking.
    """
    import os
    import signal
    from django.db import connection, OperationalError
    from django.core.cache import cache
    from django.conf import settings

    TIMEOUT_SECONDS = 5

    class HealthCheckTimeoutError(Exception):
        pass

    def timeout_handler(signum: int, frame: Any) -> None:
        raise HealthCheckTimeoutError("Operation timed out")

    checks: dict[str, str] = {
        'database': 'unknown',
        'cache': 'unknown',
        'storage': 'unknown',
    }
    healthy = True

    # Check database with timeout
    try:
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            checks['database'] = 'healthy'
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except HealthCheckTimeoutError:
        logger.error(f"Database health check timed out after {TIMEOUT_SECONDS}s")
        checks['database'] = f'unhealthy: timeout after {TIMEOUT_SECONDS}s'
        healthy = False
    except (OperationalError, Exception) as e:
        logger.error(f"Database health check failed: {e}")
        checks['database'] = f'unhealthy: {str(e)[:50]}'
        healthy = False

    # Check cache (Redis) with timeout - CRITICAL for Celery
    try:
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
        try:
            cache.set('health_check', 'ok', 10)
            if cache.get('health_check') == 'ok':
                checks['cache'] = 'healthy'
            else:
                checks['cache'] = 'unhealthy: cache read failed'
                healthy = False
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except HealthCheckTimeoutError:
        logger.error(f"Cache health check timed out after {TIMEOUT_SECONDS}s")
        checks['cache'] = f'unhealthy: timeout after {TIMEOUT_SECONDS}s'
        healthy = False  # Redis is critical for Celery
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        checks['cache'] = f'unhealthy: {str(e)[:50]}'
        healthy = False  # Redis is critical for Celery

    # Check storage - verify actual access, not just configuration
    bucket_name = getattr(settings, 'GS_BUCKET_NAME', None)
    if bucket_name:
        try:
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(TIMEOUT_SECONDS)
            try:
                from google.cloud import storage as gcs_storage
                client = gcs_storage.Client()
                bucket = client.bucket(bucket_name)
                # Verify bucket exists and is accessible
                bucket.reload()
                checks['storage'] = 'healthy'
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except HealthCheckTimeoutError:
            logger.error(f"Storage health check timed out after {TIMEOUT_SECONDS}s")
            checks['storage'] = f'unhealthy: timeout after {TIMEOUT_SECONDS}s'
            healthy = False
        except ImportError:
            logger.error("google-cloud-storage package not installed")
            checks['storage'] = 'unhealthy: google-cloud-storage not installed'
            healthy = False
        except Exception as e:
            logger.error(f"Storage health check failed: {e}")
            checks['storage'] = f'unhealthy: {str(e)[:50]}'
            healthy = False
    else:
        checks['storage'] = 'local'

    # Build response
    response_data: dict[str, Any] = {
        'status': 'healthy' if healthy else 'unhealthy',
        'service': 'transmaint',
        'version': os.environ.get('K_REVISION', 'local'),
        'checks': checks,
    }

    status_code = 200 if healthy else 503
    return JsonResponse(response_data, status=status_code)


def health_check_simple(request: HttpRequest) -> JsonResponse:
    """Simple health check for load balancer (fast)."""
    return JsonResponse({'status': 'ok'})


class PresentacionView(TemplateView):
    """Presentación oficial de Instelec - 26 mayo 2026."""
    template_name = 'presentacion_entrega.html'


# ---------------------------------------------------------------------------
# Roles y Permisos -- CRUD sobre Role + matriz de permisos (issue #186, A5)
# Análogo a CargoListView/CargoCreateView/... (apps/cuadrillas/views.py,
# precedente issue #176), bajo "Parametrización" en el sidebar.
# ---------------------------------------------------------------------------
_ROLES_ALLOWED = ['admin', 'director', 'coordinador', 'admin_general', 'coordinador_general']


class RoleListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Listado del maestro Roles, con activos e inactivos."""
    model = Role
    template_name = 'core/roles_lista.html'
    context_object_name = 'roles'
    allowed_roles = _ROLES_ALLOWED

    def get_queryset(self):
        qs = Role.objects.all()
        estado = self.request.GET.get('estado', '').strip()
        if estado == 'activos':
            qs = qs.filter(activo=True)
        elif estado == 'inactivos':
            qs = qs.filter(activo=False)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['estado_filtro'] = self.request.GET.get('estado', '')
        context['total_activos'] = Role.objects.filter(activo=True).count()
        context['total_inactivos'] = Role.objects.filter(activo=False).count()
        return context


class RoleCreateView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """Crear un nuevo Role."""
    template_name = 'core/roles_form.html'
    allowed_roles = _ROLES_ALLOWED

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', RoleForm())
        context['modo'] = 'crear'
        return context

    def post(self, request, *args, **kwargs):
        form = RoleForm(request.POST)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'Rol "{role.nombre}" creado exitosamente.')
            return redirect('core:roles_lista')
        messages.error(request, 'Revise los errores del formulario.')
        return self.render_to_response(self.get_context_data(form=form))


class RoleEditView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, DetailView):
    """Editar un Role existente. `codigo` queda de solo lectura (ver RoleForm)."""
    model = Role
    template_name = 'core/roles_form.html'
    context_object_name = 'role'
    allowed_roles = _ROLES_ALLOWED

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', RoleForm(instance=self.object))
        context['modo'] = 'editar'
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = RoleForm(request.POST, instance=self.object)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'Rol "{role.nombre}" actualizado exitosamente.')
            return redirect('core:roles_lista')
        messages.error(request, 'Revise los errores del formulario.')
        return self.render_to_response(self.get_context_data(form=form))


class RoleInactivarView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Alterna activo/inactivo de un Role. Nunca borra el registro (sin FK
    real que lo fuerce, pero un Role en uso por Usuarios existentes no debe
    desaparecer -- ver PLAN §1)."""
    model = Role
    allowed_roles = _ROLES_ALLOWED

    def post(self, request, *args, **kwargs):
        role = self.get_object()
        role.activo = not role.activo
        role.save(update_fields=['activo', 'updated_at'])
        if role.activo:
            messages.success(request, f'Rol "{role.nombre}" reactivado.')
        else:
            messages.success(
                request,
                f'Rol "{role.nombre}" inactivado. '
                'No aparecerá en el picklist de asignación de Usuarios (ver A4).',
            )
        return redirect('core:roles_lista')


def _columnas_matriz():
    """(clave, etiqueta) de cada columna de la matriz: 3 módulos + N sub-módulos
    de CONSTRUCCION (issue #186, A5)."""
    columnas_modulo = list(RoleModuloPermiso.MODULO_CHOICES)
    columnas_submodulo = [
        (s, s.replace('_', ' ').title()) for s in sorted(TODOS_SUBMODULOS)
    ]
    return columnas_modulo, columnas_submodulo


class RoleModuloPermisoMatrizView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Grid roles (filas) x módulos/sub-módulos (columnas) -- issue #186, A5.

    Celda = nivel_acceso (sin_acceso/ver/ver_editar), guardado vía HTMX por
    celda (`RoleModuloPermisoCeldaView`), sin reload completo. Soporta crear
    roles nuevos (vía `RoleCreateView` arriba) y asignarles permisos acá
    mismo, sin deploy."""
    template_name = 'core/roles_matriz.html'
    allowed_roles = _ROLES_ALLOWED

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columnas_modulo, columnas_submodulo = _columnas_matriz()

        roles = Role.objects.filter(activo=True).prefetch_related('permisos')
        filas = []
        for role in roles:
            permisos_por_columna = {
                (p.submodulo or p.modulo): p.nivel_acceso for p in role.permisos.all()
            }
            filas.append({'role': role, 'permisos': permisos_por_columna})

        context['filas'] = filas
        context['columnas_modulo'] = columnas_modulo
        context['columnas_submodulo'] = columnas_submodulo
        context['nivel_choices'] = RoleModuloPermiso.NIVEL_ACCESO_CHOICES
        context['sin_acceso'] = RoleModuloPermiso.SIN_ACCESO
        return context


class RoleModuloPermisoCeldaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Guarda UNA celda de la matriz vía HTMX (POST) -- issue #186, A5.

    `columna` es el código de módulo (MANTENIMIENTO/CONSTRUCCION/CONFIG) o de
    sub-módulo (siempre implica modulo=CONSTRUCCION). El `save()` de
    `RoleModuloPermiso` dispara la señal de invalidación de cache
    (apps/core/models_roles.py) -- efecto inmediato, sin esperar el TTL."""
    allowed_roles = _ROLES_ALLOWED
    template_name = 'core/partials/_matriz_celda.html'

    def post(self, request, role_codigo, columna, *args, **kwargs):
        role = get_object_or_404(Role, codigo=role_codigo)

        nivel_valido = dict(RoleModuloPermiso.NIVEL_ACCESO_CHOICES)
        nivel_acceso = request.POST.get(f'celda_{role_codigo}_{columna}', '').strip()
        if nivel_acceso not in nivel_valido:
            nivel_acceso = RoleModuloPermiso.SIN_ACCESO

        modulos_validos = dict(RoleModuloPermiso.MODULO_CHOICES)
        if columna in modulos_validos:
            modulo, submodulo = columna, None
        else:
            modulo, submodulo = RoleModuloPermiso.MODULO_CONSTRUCCION, columna

        RoleModuloPermiso.objects.update_or_create(
            role=role, modulo=modulo, submodulo=submodulo,
            defaults={'nivel_acceso': nivel_acceso},
        )

        return self.render_to_response({
            'role': role,
            'columna': columna,
            'nivel_actual': nivel_acceso,
            'nivel_choices': RoleModuloPermiso.NIVEL_ACCESO_CHOICES,
        })
