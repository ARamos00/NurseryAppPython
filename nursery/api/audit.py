from __future__ import annotations

from datetime import datetime
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, is_naive
from rest_framework import permissions, viewsets
from rest_framework.request import Request

from core.permissions import IsOwner
from nursery.models import AuditLog
from nursery.serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit logs.
    - Non-staff users see only their own (`user=request.user`).
    - Staff can see all and filter by `user_id`.
    Filters (query params):
      - model: "app.model" or just "model" (case-insensitive)
      - object_id: int
      - action: create|update|delete
      - date_from, date_to: ISO8601 timestamps (inclusive)
      - user_id: only for staff
    """
    queryset = AuditLog.objects.select_related("actor", "content_type", "user").all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "audit-read"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_staff:
            qs = qs.filter(user=user)
        return qs

    def _parse_date(self, s: str | None) -> datetime | None:
        if not s:
            return None
        dt = parse_datetime(s)
        if dt and is_naive(dt):
            dt = make_aware(dt)
        return dt

    def filter_queryset(self, queryset):
        request: Request = self.request
        params = request.query_params

        # model filter (accept "app.model" or "model")
        model_param = (params.get("model") or "").strip().lower()
        if model_param:
            if "." in model_param:
                app_label, model_name = model_param.split(".", 1)
            else:
                # assume our app if not given
                app_label, model_name = "nursery", model_param
            try:
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
                queryset = queryset.filter(content_type=ct)
            except ContentType.DoesNotExist:
                return queryset.none()

        # object_id
        obj_id = params.get("object_id")
        if obj_id:
            try:
                queryset = queryset.filter(object_id=int(obj_id))
            except ValueError:
                queryset = queryset.none()

        # action
        action = (params.get("action") or "").strip().lower()
        if action:
            queryset = queryset.filter(action=action)

        # date range
        df = self._parse_date(params.get("date_from"))
        dt = self._parse_date(params.get("date_to"))
        if df:
            queryset = queryset.filter(created_at__gte=df)
        if dt:
            queryset = queryset.filter(created_at__lte=dt)

        # staff-only user_id
        if self.request.user.is_staff:
            user_id = params.get("user_id")
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    queryset = queryset.none()

        return queryset
