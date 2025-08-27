"""
AppConfig for the `nursery` domain app.

Startup responsibilities
------------------------
- Import **signals** at startup (required): label lifecycle handlers and optional
  webhook emitters depend on these to keep invariants (e.g., revoking tokens on
  terminal status changes).
- Import **audit_hooks** at startup (required): ensures model lifecycle events
  (including soft-delete) record audit entries.
- Import **schema** (optional): drf-spectacular OpenAPI tweaks. In DEBUG we still
  surface errors to catch schema issues early.

Reliability notes
-----------------
- Django’s autoreloader may call `ready()` multiple times; all receivers use
  `dispatch_uid`, and imports are idempotent, so repeated calls are safe.
"""

from __future__ import annotations

import logging
from importlib import import_module

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class NurseryConfig(AppConfig):
    """Primary app configuration for Nursery domain models and APIs."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "nursery"

    def ready(self) -> None:  # pragma: no cover
        """
        Register startup hooks.

        Notes:
        - Signals are **required** for runtime behavior (label lifecycle, webhooks when enabled).
        - Schema extensions are **optional** (OpenAPI tweaks); in DEBUG we still surface errors.
        - Django’s dev autoreloader may call ready() more than once; our signal receivers use
          `dispatch_uid`, so repeated imports are safe and idempotent.
        """
        self._import_startup_module("nursery.signals", required=True)
        # NEW: load audit hooks so soft-delete emits a DELETE audit entry.
        self._import_startup_module("nursery.audit_hooks", required=True)
        self._import_startup_module("nursery.schema", required=False)

    @staticmethod
    def _import_startup_module(dotted_path: str, *, required: bool) -> None:
        """
        Import a module at startup with sensible error handling.

        - If `required` and import fails: log and re-raise (fail fast).
        - If not required:
            * In DEBUG: log and re-raise to surface issues early.
            * In non-DEBUG: log a warning and continue.
        """
        try:
            import_module(dotted_path)
        except Exception:
            if required or settings.DEBUG:
                logger.exception("Failed to import startup module: %s", dotted_path)
                # Re-raise to surface the problem in dev/tests or for required modules.
                raise
            logger.warning("Optional startup module failed to import and was skipped: %s", dotted_path)
