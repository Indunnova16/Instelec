"""
Core mixins for views and models.
"""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse


class HTMXMixin:
    """
    Mixin for HTMX-aware views.
    Automatically uses partial template for HTMX requests.
    """
    partial_template_name = None

    def get_template_names(self):
        if self.request.headers.get('HX-Request') and self.partial_template_name:
            return [self.partial_template_name]
        return super().get_template_names()

    def dispatch(self, request, *args, **kwargs):
        self.is_htmx = request.headers.get('HX-Request', False)
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(UserPassesTestMixin):
    """
    Mixin that requires user to have specific role(s).
    Administrators (admin role) have access to all views.
    RBAC v2 (#44): cualquier rol nivel `admin` (admin_general, coordinador_general,
    admin_mantenimiento, admin_construccion) pasa automáticamente — independientemente
    de la `allowed_roles` legacy que la vista declare.

    #235 — `admin_bypass = False` desactiva ESE atajo para una vista puntual,
    volviendo `allowed_roles` autoritativo. Existe porque el bypass hace que
    `allowed_roles` sea decorativo para 9 de los 15 roles: una vista que
    declara `['admin']` en realidad la ven 9 roles. Eso es tolerable —y hasta
    deseado— en las superficies operativas (los admins de área deben ver todo
    lo suyo), pero NO donde se otorga privilegio (gestión de usuarios, reset de
    contraseña, matriz de permisos): ahí un `admin_construccion` no debe poder
    tocar cuentas ni permisos.

    Se optó por opt-out en vez de invertir la precedencia globalmente porque la
    auditoría del blast radius (294 vistas alcanzables) dio: 287 romperían para
    al menos un rol admin, y `admin_mantenimiento` perdería acceso a las 287.
    Las `allowed_roles` del portafolio se escribieron asumiendo que el bypass
    existía, así que invertirlas de golpe deja gente afuera de su trabajo
    diario. El opt-out cierra el riesgo real tocando 11 vistas en vez de 287.
    """
    allowed_roles = []
    admin_bypass = True

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False

        # Superusers and admin users have full access
        if self.request.user.is_superuser:
            return True

        if self.admin_bypass:
            # Check if user has is_admin property (for custom User model)
            try:
                if getattr(self.request.user, 'is_admin', False):
                    return True
            except Exception:
                pass

            # RBAC v2 (#44): rol admin nivel → pasa
            try:
                from .permissions import user_es_admin
                if user_es_admin(self.request.user):
                    return True
            except Exception:
                pass

        # Check user rol field
        user_rol = getattr(self.request.user, 'rol', None)
        if user_rol and self.allowed_roles:
            return user_rol in self.allowed_roles

        # If no specific roles required, allow authenticated users.
        # #235: pero si la vista desactivó el bypass a propósito, una lista
        # vacía es casi siempre un descuido — ahí se falla CERRADO en vez de
        # abrir la superficie más sensible a cualquier autenticado.
        if not self.allowed_roles:
            return self.admin_bypass

        return False

    def handle_no_permission(self):
        """
        Handle permission denied.
        If user is not authenticated, redirect to login.
        If user is authenticated but doesn't have permission, raise PermissionDenied.
        """
        if not self.request.user.is_authenticated:
            # Not authenticated - redirect to login
            return super().handle_no_permission()
        # Authenticated but no permission - raise 403
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(
            f"Acceso denegado. Su rol ({getattr(self.request.user, 'rol', 'sin rol')}) "
            f"no tiene permisos para esta acción."
        )


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin that requires user to be staff.
    """
    def test_func(self):
        return self.request.user.is_staff


class ModuloRequiredMixin(UserPassesTestMixin):
    """Restringe acceso a una vista al módulo MANTENIMIENTO o CONSTRUCCION (#44).

    Uso:
        class MiVista(LoginRequiredMixin, ModuloRequiredMixin, ListView):
            required_modulo = 'CONSTRUCCION'

    Si `required_modulo` es None la vista queda abierta a cualquier autenticado
    (igual que LoginRequiredMixin).
    """
    required_modulo = None

    def test_func(self):
        from .permissions import user_can_access_modulo
        if not self.request.user.is_authenticated:
            return False
        return user_can_access_modulo(self.request.user, self.required_modulo)

    def handle_no_permission(self):
        from django.core.exceptions import PermissionDenied
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            f"Acceso denegado al módulo {self.required_modulo}. "
            f"Su rol ({getattr(self.request.user, 'rol', 'sin rol')}) no tiene permisos."
        )


class NivelAdminRequiredMixin(UserPassesTestMixin):
    """Restringe acceso a usuarios con nivel `admin` (no operarios)."""

    def test_func(self):
        from .permissions import user_es_admin
        return user_es_admin(self.request.user)

    def handle_no_permission(self):
        from django.core.exceptions import PermissionDenied
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            "Esta acción requiere un rol administrativo."
        )


class SubModuloRequiredMixin(UserPassesTestMixin):
    """Restringe acceso a un sub-módulo CONSTRUCCION (#62 iter 2).

    Uso:
        class FinancieroGridView(LoginRequiredMixin, SubModuloRequiredMixin, ...):
            required_submodulo = 'FINANCIERO'
    """
    required_submodulo = None

    def test_func(self):
        from .permissions import user_can_access_submodulo
        if not self.request.user.is_authenticated:
            return False
        return user_can_access_submodulo(self.request.user, self.required_submodulo)

    def handle_no_permission(self):
        from django.core.exceptions import PermissionDenied
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied(
            f"Su rol no tiene acceso al sub-módulo {self.required_submodulo}."
        )


class HTMXResponseMixin:
    """
    Mixin for handling HTMX responses.
    """
    def htmx_redirect(self, url):
        """Redirect for HTMX requests."""
        response = HttpResponse()
        response['HX-Redirect'] = url
        return response

    def htmx_refresh(self):
        """Refresh page for HTMX requests."""
        response = HttpResponse()
        response['HX-Refresh'] = 'true'
        return response

    def htmx_trigger(self, event_name, event_data=None):
        """Trigger a client-side event."""
        import json
        response = HttpResponse()
        if event_data:
            response['HX-Trigger'] = json.dumps({event_name: event_data})
        else:
            response['HX-Trigger'] = event_name
        return response
