from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, serializers, viewsets
from rest_framework.filters import OrderingFilter

from nursery.models import AuditAction, AuditLog
from nursery.serializers import AuditLogSerializer


class AuditLogWithModelSerializer(AuditLogSerializer):
    """
    Extend the canonical AuditLogSerializer to expose a top-level `model` field
    so tests can assert `item["model"] == "plant"`, etc. The value is the
    lowercased ContentType.model (e.g., "plant", "propagationbatch").
    """
    model = serializers.SerializerMethodField()

    def get_model(self, obj: AuditLog) -> str:
        return obj.content_type.model

    class Meta(AuditLogSerializer.Meta):  # type: ignore[misc]
        fields = AuditLogSerializer.Meta.fields + ["model"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Owner-scoped listing of audit entries with simple filters:

      - ?model=<content_type.model>    (e.g., "plant")
      - ?action=create|update|delete

    Notes:
    - Queryset is per-tenant via the `user` FK.
    - We keep ordering minimal and stable for tests.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AuditLogWithModelSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "id"]
    ordering = ["-id"]

    def get_queryset(self):
        # Explicitly scope by owner; select_related for ContentType to avoid N+1.
        return AuditLog.objects.filter(user=self.request.user).select_related("content_type")

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)

        model = self.request.query_params.get("model")
        if model:
            try:
                ct = ContentType.objects.get_by_natural_key(app_label="nursery", model=model)
                qs = qs.filter(content_type=ct)
            except ContentType.DoesNotExist:
                return qs.none()

        action = self.request.query_params.get("action")
        if action:
            valid = {a.value for a in AuditAction}
            if action not in valid:
                return qs.none()
            qs = qs.filter(action=action)

        return qs
