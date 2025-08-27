from __future__ import annotations

from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware
from rest_framework import permissions, serializers, viewsets
from rest_framework.request import Request

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema

from nursery.models import AuditLog, AuditAction
from nursery.serializers import AuditLogSerializer
from nursery.schema import ERROR_RESPONSE


class AuditLogWithModelSerializer(AuditLogSerializer):
    """
    Extend the canonical AuditLogSerializer to expose a top-level `model` field
    (lowercased ContentType.model, e.g., "plant"). Tests assert on this key.
    """
    model = serializers.SerializerMethodField()

    def get_model(self, obj: AuditLog) -> str:
        return obj.content_type.model

    class Meta(AuditLogSerializer.Meta):  # type: ignore[misc]
        fields = AuditLogSerializer.Meta.fields + ["model"]


@extend_schema(
    tags=["Audit"],
    parameters=[
        OpenApiParameter(name="model", type=OpenApiTypes.STR, required=False, description='e.g. "plant" or "nursery.plant"'),
        OpenApiParameter(name="object_id", type=OpenApiTypes.INT, required=False),
        OpenApiParameter(name="action", type=OpenApiTypes.STR, required=False, description="create|update|delete"),
        OpenApiParameter(name="date_from", type=OpenApiTypes.DATETIME, required=False),
        OpenApiParameter(name="date_to", type=OpenApiTypes.DATETIME, required=False),
        OpenApiParameter(name="user_id", type=OpenApiTypes.INT, required=False, description="Staff only"),
    ],
    responses={200: OpenApiResponse(description="Paginated audit logs"), 400: ERROR_RESPONSE},
    description="Read-only audit logs, owner-scoped for non-staff users.",
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit logs, owner-scoped for non-staff users.

    Filters (query params):
      - model: "plant" (or "app.model")
      - object_id: integer
      - action: create|update|delete
      - date_from, date_to: ISO8601 datetimes (inclusive)
      - user_id: (staff only)
    """

    # Provide harmless baseline so schema generation never errors.
    queryset = AuditLog.objects.none()
    serializer_class = AuditLogWithModelSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "audit-read"

    # Help routers/schema type the path param as integer.
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        """
        During schema generation drf-spectacular sets `swagger_fake_view=True`.
        Avoid request-dependent filtering in that mode to prevent errors.
        """
        if getattr(self, "swagger_fake_view", False):
            return AuditLog.objects.none()

        qs = AuditLog.objects.select_related("actor", "content_type", "user").all()
        user = self.request.user
        if not getattr(user, "is_staff", False):
            qs = qs.filter(user=user)
        return qs

    # ---- helpers for filtering ------------------------------------------------

    def _parse_dt(self, s: str | None) -> datetime | None:
        if not s:
            return None
        dt = parse_datetime(s)
        if dt and is_naive(dt):
            dt = make_aware(dt)
        return dt

    def filter_queryset(self, queryset):
        request: Request = self.request
        params = request.query_params

        # model filter: accept "model" or "app.model"
        model_param = (params.get("model") or "").strip().lower()
        if model_param:
            if "." in model_param:
                app_label, model_name = model_param.split(".", 1)
            else:
                app_label, model_name = "nursery", model_param
            try:
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
                queryset = queryset.filter(content_type=ct)
            except ContentType.DoesNotExist:
                return queryset.none()

        # object_id
        object_id = params.get("object_id")
        if object_id:
            try:
                queryset = queryset.filter(object_id=int(object_id))
            except ValueError:
                return queryset.none()

        # action
        action = (params.get("action") or "").strip().lower()
        if action:
            valid = {a.value for a in AuditAction}
            if action not in valid:
                return queryset.none()
            queryset = queryset.filter(action=action)

        # date window (inclusive)
        df = self._parse_dt(params.get("date_from"))
        dt = self._parse_dt(params.get("date_to"))
        if df:
            queryset = queryset.filter(created_at__gte=df)
        if dt:
            queryset = queryset.filter(created_at__lte=dt)

        # staff-only: filter by user_id if provided
        if getattr(request.user, "is_staff", False):
            uid = params.get("user_id")
            if uid:
                try:
                    queryset = queryset.filter(user_id=int(uid))
                except ValueError:
                    return queryset.none()

        return queryset
