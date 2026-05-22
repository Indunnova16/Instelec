from django.apps import AppConfig


class ContratosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.contratos'
    verbose_name = 'Contratos'

    def ready(self):
        from . import signals  # noqa: F401
