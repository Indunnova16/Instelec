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
    """
    allowed_roles = []

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False

        # Superusers and admin users have full access
        if self.request.user.is_superuser:
            return True

        # Check if user has is_admin property (for custom User model)
        try:
            if getattr(self.request.user, 'is_admin', False):
                return True
        except Exception:
            pass

        # Check user rol field
        user_rol = getattr(self.request.user, 'rol', None)
        if user_rol and self.allowed_roles:
            return user_rol in self.allowed_roles

        # If no specific roles required, allow authenticated users
        if not self.allowed_roles:
            return True

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
