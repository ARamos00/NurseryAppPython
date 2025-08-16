from __future__ import annotations

import secrets
from typing import List

from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, mixins, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.permissions import IsOwner
from nursery.models import (
    WebhookEndpoint,
    WebhookDelivery,
    WebhookEventType,
    WebhookDeliveryStatus,
)
from .viewsets import OwnedModelViewSet


# ------------------------------- Serializers ----------------------------------

class WebhookEndpointSerializer(serializers.ModelSerializer):
    # secret is write-only; expose only last4 on reads
    secret = serializers.CharField(write_only=True, required=True, max_length=128)
    secret_last4 = serializers.CharField(read_only=True)

    class Meta:
        model = WebhookEndpoint
        fields = [
            "id", "name", "url", "event_types", "is_active",
            "secret", "secret_last4",
            "created_at", "updated_at", "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user", "secret_last4"]

    def validate_url(self, value: str) -> str:
        require_https = getattr(settings, "WEBHOOKS_REQUIRE_HTTPS", not settings.DEBUG)
        if require_https and not value.lower().startswith("https://"):
            raise serializers.ValidationError("HTTPS is required for webhooks in this environment.")
        return value

    def validate_event_types(self, value: List[str]) -> List[str]:
        if not value:
            return value  # empty = all
        if "*" in value:
            return ["*"]  # normalize
        valid = {c for c, _ in WebhookEventType.choices}
        invalid = [v for v in value if v not in valid]
        if invalid:
            raise serializers.ValidationError(f"Unknown event type(s): {invalid}")
        return value

    def create(self, validated_data):
        # set user via OwnedModelViewSet.perform_create; ensure secret_last4
        ep = WebhookEndpoint(**validated_data)
        ep.user = self.context["request"].user
        ep.full_clean()
        ep.save()
        return ep

    def update(self, instance, validated_data):
        # if secret provided, rotate it
        secret = validated_data.pop("secret", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if secret is not None:
            instance.secret = secret
            instance.secret_last4 = secret[-4:]
        instance.full_clean()
        instance.save()
        return instance


class WebhookDeliverySerializer(serializers.ModelSerializer):
    endpoint_url = serializers.CharField(source="endpoint.url", read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = [
            "id", "endpoint", "endpoint_url", "event_type", "payload",
            "status", "attempt_count", "last_attempt_at", "next_attempt_at",
            "response_status", "response_headers", "response_body",
            "last_error", "request_duration_ms",
            "created_at", "updated_at", "user",
        ]
        read_only_fields = fields


# -------------------------------- ViewSets ------------------------------------

@extend_schema(tags=["Webhooks"])
class WebhookEndpointViewSet(OwnedModelViewSet):
    """
    Manage webhook endpoints for the current user.
    """
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = WebhookEndpointSerializer
    queryset = WebhookEndpoint.objects.all()
    filterset_fields = ["is_active"]
    search_fields = ["name", "url"]
    ordering_fields = ["created_at", "updated_at", "name"]
    ordering = ["-created_at"]


@extend_schema(tags=["Webhooks"])
class WebhookDeliveryViewSet(OwnedModelViewSet):
    """
    Read-only view of deliveries. (No create/update/delete via API.)
    """
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = WebhookDeliverySerializer
    queryset = WebhookDelivery.objects.select_related("endpoint").all()
    filterset_fields = ["status", "event_type", "endpoint"]
    search_fields = []
    ordering_fields = ["created_at", "last_attempt_at", "next_attempt_at", "status", "attempt_count"]
    ordering = ["-created_at"]
    http_method_names = ["get", "head", "options"]
