from django.apps import AppConfig


class TripsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trips"
    verbose_name = "Trip planning & community"

    def ready(self):
        from . import signals  # noqa: F401  registers the login signal handler
