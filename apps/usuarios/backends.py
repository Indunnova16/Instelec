"""
Custom authentication backends.
Allows campo users to login with cedula instead of email.
"""
from django.contrib.auth.backends import ModelBackend
from .models import Usuario


class CedulaOrEmailBackend(ModelBackend):
    """
    Authenticate using either email or documento (cedula).
    Field workers login with cedula, admins with email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            return None

        # Try email first (standard flow)
        try:
            user = Usuario.objects.get(email=username)
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except Usuario.DoesNotExist:
            pass

        # Try documento (cedula) - for campo users
        try:
            user = Usuario.objects.get(documento=username)
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except (Usuario.DoesNotExist, Usuario.MultipleObjectsReturned):
            pass

        return None
