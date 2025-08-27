"""Custom user model for Nursery Tracker.

Why a custom user?
------------------
- Establishes an extension point from day one (recommended by Django docs) so
  we can add fields later without a disruptive migration from `auth.User`.
- Keeps Django's default authentication behavior via `AbstractUser`.

Behavior
--------
- No additional fields or methods are introduced at this time; the model acts
  exactly like Django's built-in user for auth, permissions, etc.
"""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Project's custom user model.

    Keeping Django defaults for now; extend with fields later as needed.
    """
    # NOTE: Add project-specific fields (e.g., organization, display_name) in future
    # iterations. Admin and serializers can evolve without breaking auth flows.
    pass
