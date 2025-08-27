"""
Permission classes used across the API.

This module currently exposes:
- `IsOwner`: object-level guard that allows access only when `obj.user` matches
  the authenticated `request.user`.

Usage
-----
- Combine with authentication (e.g., `IsAuthenticated`) and ensure view querysets
  are filtered by `request.user`:
      permission_classes = [IsAuthenticated, IsOwner]
      def get_queryset(self):
          return Model.objects.for_user(self.request.user)

Security
--------
# SECURITY: Always scope list/queryset endpoints by `request.user` in addition to
# object-level checks to avoid leaking object existence via filtering/ordering.
"""

from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """
    Object-level permission: only the owner (obj.user) can access/mutate.

    Use in ViewSets with:
        permission_classes = [IsAuthenticated, IsOwner]

    Notes:
        - Works in tandem with queryset scoping in `get_queryset()`.
        - Returns False for anonymous or unauthenticated users.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        owner_id = getattr(obj, "user_id", None)
        return bool(
            user and getattr(user, "is_authenticated", False) and owner_id == user.id
        )
