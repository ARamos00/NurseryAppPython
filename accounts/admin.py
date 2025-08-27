"""Admin registrations for the accounts app.

Notes
-----
- Admin is back-office only (not a public UI). We register the project's custom
  `User` model using Django's built-in `UserAdmin` for standard behavior.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Use Django's built-in UserAdmin for our custom user."""
    # NOTE: We intentionally keep defaults; customize list_display/fieldsets later
    # if/when the custom user grows additional fields.
    pass
