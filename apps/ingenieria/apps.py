from django.apps import AppConfig


class IngenieriaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ingenieria'
    verbose_name = 'Ingeniería'

    def ready(self):
        from . import signals  # noqa: F401
