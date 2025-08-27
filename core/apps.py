"""AppConfig for the `core` app.

Scope
-----
Holds shared infrastructure pieces used across the project:
- middleware (observability and size limits),
- logging helpers (request-id),
- base models/perms/throttles (in this app, see other modules).
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Standard Django AppConfig; keep defaults lightweight."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
