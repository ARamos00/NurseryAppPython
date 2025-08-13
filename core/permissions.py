from rest_framework.permissions import BasePermission

class IsOwner(BasePermission):
    """
    Object-level permission: only the owner (obj.user) can access/mutate.
    Use in ViewSets with: permission_classes = [IsAuthenticated, IsOwner]
    and ensure get_queryset() filters by request.user to avoid leakage.
    """
    def has_object_permission(self, request, view, obj) -> bool:
        user = getattr(request, "user", None)
        owner_id = getattr(obj, "user_id", None)
        return bool(user and getattr(user, "is_authenticated", False) and owner_id == user.id)
