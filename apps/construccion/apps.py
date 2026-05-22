from django.apps import AppConfig


class ConstruccionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.construccion'

    def ready(self):
        from . import signals  # noqa: F401
