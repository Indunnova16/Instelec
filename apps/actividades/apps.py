from django.apps import AppConfig


class ActividadesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.actividades'
    verbose_name = 'Actividades'

    def ready(self):
        from . import signals  # noqa: F401
