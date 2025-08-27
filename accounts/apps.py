"""Django AppConfig for the accounts app.

This app houses the project's custom user model (`accounts.User`) and any
future account-related signals or admin customizations.
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Standard Django app config; uses BigAutoField as the default PK type."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
