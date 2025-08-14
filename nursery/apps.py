from django.apps import AppConfig


class NurseryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nursery"

    def ready(self) -> None:
        # Import schema extensions & signals so they're registered at startup.
        try:
            from . import schema  # noqa: F401
        except Exception:
            pass
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
