from django.apps import AppConfig


class NurseryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nursery"

    def ready(self) -> None:
        # Import schema extensions so drf-spectacular can register them.
        # Keep this import tolerant in dev to not break migrations or admin.
        try:
            from . import schema  # noqa: F401
        except Exception:
            # It's safe to ignore import issues during certain management commands.
            pass
