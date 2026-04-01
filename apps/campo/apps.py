from django.apps import AppConfig


class CampoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.campo'
    verbose_name = 'Campo'

    def ready(self):
        """Import signals when app is ready."""
        import apps.campo.signals  # noqa
