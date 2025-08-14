from __future__ import annotations

from typing import List, Dict

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from core.utils.idempotency import idempotent
from nursery.models import Plant, PlantStatus, Event, EventType


class BulkStatusRequestSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        help_text="List of plant IDs to update.",
    )
    status = serializers.ChoiceField(choices=PlantStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_ids(self, value: List[int]) -> List[int]:
        # Deduplicate to avoid double work
        return sorted(set(value))


class BulkStatusResponseSerializer(serializers.Serializer):
    updated_ids = serializers.ListField(child=serializers.IntegerField())
    missing_ids = serializers.ListField(child=serializers.IntegerField())
    event_ids = serializers.ListField(child=serializers.IntegerField())
    count_updated = serializers.IntegerField()


STATUS_TO_EVENT = {
    PlantStatus.SOLD: EventType.SELL,
    PlantStatus.DISCARDED: EventType.DISCARD,
    PlantStatus.DEAD: EventType.DISCARD,
}


class PlantOpsMixin:
    """
    Adds bulk ops to PlantViewSet:
      - POST /api/plants/bulk/status/
    """

    @extend_schema(
        tags=["Plants: Ops"],
        request=BulkStatusRequestSerializer,
        responses={200: BulkStatusResponseSerializer},
        description=(
            "Bulk update plant statuses. Creates a corresponding Event per plant "
            "(SELL/DISCARD for terminal states; NOTE otherwise). Idempotent per body."
        ),
    )
    @action(detail=False, methods=["post"], url_path="bulk/status")
    @idempotent
    def bulk_status(self, request: Request) -> Response:
        ser = BulkStatusRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["ids"]
        status_value = ser.validated_data["status"]
        notes = ser.validated_data.get("notes", "")

        # Scope to current user
        owned_qs = Plant.objects.filter(user=request.user, id__in=ids).select_related("taxon", "batch")
        found_map: Dict[int, Plant] = {p.id: p for p in owned_qs}
        missing_ids = [i for i in ids if i not in found_map]

        event_type = STATUS_TO_EVENT.get(status_value, EventType.NOTE)

        updated_ids: List[int] = []
        event_ids: List[int] = []

        with transaction.atomic():
            for pid, plant in found_map.items():
                if plant.status == status_value and not notes:
                    # No-op; skip to keep idempotent feel even without header
                    continue
                plant.status = status_value
                plant.save(update_fields=["status", "updated_at"])
                ev = Event.objects.create(
                    user=request.user,
                    plant=plant,
                    event_type=event_type,
                    notes=notes or f"Status → {status_value}",
                )
                updated_ids.append(pid)
                event_ids.append(ev.id)

        return Response(
            {
                "updated_ids": updated_ids,
                "missing_ids": missing_ids,
                "event_ids": event_ids,
                "count_updated": len(updated_ids),
            },
            status=status.HTTP_200_OK,
        )
