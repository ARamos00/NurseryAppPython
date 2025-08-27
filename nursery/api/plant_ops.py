from __future__ import annotations

"""
Custom operations for `Plant` resources.

Actions:
- `POST /api/plants/bulk/status/`: Bulk status update across owned plants; writes
  per-plant `Event` records (SELL/DISCARD for terminal states; NOTE otherwise).
- `POST /api/plants/{id}/archive/`: Soft-delete a plant and revoke its active label.

Cross-cutting concerns
----------------------
- **Idempotency**: `@idempotent` ensures repeated identical requests return the first
  success (user/key/method/path/body-hash).
- **Optimistic concurrency**: Archive requires `If-Match` when header present.

Security
--------
- All lookups and updates are owner-scoped; bulk update resolves only user-owned ids
  and reports non-owned/missing ids in `missing_ids`.
"""

from typing import List, Dict

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.utils.concurrency import require_if_match
from core.utils.idempotency import idempotent
from nursery.models import (
    Plant,
    PlantStatus,
    Event,
    EventType,
    Label,
    LabelToken,
)
# Shared OpenAPI components
from nursery.schema import (
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENCY_EXAMPLE,
    IF_MATCH_HEADER,
    VALIDATION_ERROR_RESPONSE,
    ERROR_RESPONSE,
)

# -----------------------------------------------------------------------------
# Bulk status change
# -----------------------------------------------------------------------------

class BulkStatusRequestSerializer(serializers.Serializer):
    """Request body for bulk status changes."""
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        help_text="List of plant IDs to update.",
    )
    status = serializers.ChoiceField(choices=PlantStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_ids(self, value: List[int]) -> List[int]:
        """Deduplicate and sort IDs to avoid double work and keep stable output."""
        # Deduplicate to avoid double work
        return sorted(set(value))


class BulkStatusResponseSerializer(serializers.Serializer):
    """Response summary for bulk status changes."""
    updated_ids = serializers.ListField(child=serializers.IntegerField())
    missing_ids = serializers.ListField(child=serializers.IntegerField())
    event_ids = serializers.ListField(child=serializers.IntegerField())
    count_updated = serializers.IntegerField()


# Mapping from PlantStatus to corresponding EventType
STATUS_TO_EVENT = {
    PlantStatus.SOLD: EventType.SELL,
    PlantStatus.DISCARDED: EventType.DISCARD,
    PlantStatus.DEAD: EventType.DISCARD,
}


class PlantOpsMixin:
    """
    Adds ops to PlantViewSet:
      - POST /api/plants/bulk/status/
      - POST /api/plants/{id}/archive/

    Concurrency / Idempotency:
        - Bulk status is idempotent per request body.
        - Archive enforces `If-Match` when header present (412 on mismatch).
    """

    @extend_schema(
        tags=["Plants: Ops"],
        parameters=[IDEMPOTENCY_KEY_HEADER],
        request=BulkStatusRequestSerializer,
        responses={
            200: BulkStatusResponseSerializer,
            400: VALIDATION_ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description=(
            "Bulk update plant statuses. Creates a corresponding Event per plant "
            "(SELL/DISCARD for terminal states; NOTE otherwise). Idempotent per body."
        ),
    )
    @action(detail=False, methods=["post"], url_path="bulk/status")
    @idempotent
    def bulk_status(self, request: Request) -> Response:
        """Apply a new status to owned plants; returns updated/missing IDs and Event IDs."""
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

    # -----------------------------------------------------------------------------
    # Archive (soft-delete)
    # -----------------------------------------------------------------------------

    class _ArchiveResponse(serializers.Serializer):
        """Response body for plant `/archive/`."""
        id = serializers.IntegerField()
        archived = serializers.BooleanField()
        deleted_at = serializers.DateTimeField()

        class Meta:
            # Unique component name for OpenAPI to avoid collisions
            ref_name = "PlantArchiveResponse"

    @extend_schema(
        tags=["Plants: Ops"],
        parameters=[IF_MATCH_HEADER],
        responses={
            200: _ArchiveResponse,
            412: ERROR_RESPONSE,  # stale If-Match
        },
        description=(
            "Soft-delete (archive) this plant. Sets is_deleted=true and deleted_at now. "
            "Revokes any active label token so the public page stops resolving. "
            "Idempotent: repeated calls are safe."
        ),
    )
    @action(detail=True, methods=["post"], url_path="archive")
    @idempotent
    def archive(self, request: Request, pk: str | None = None) -> Response:
        """Soft-delete the plant and revoke its active label token, if any."""
        plant: Plant = self.get_object()
        # Concurrency guard (no-op if ENFORCE_IF_MATCH=False)
        require_if_match(request, plant.updated_at)

        if plant.is_deleted:
            return Response(
                {"id": plant.id, "archived": True, "deleted_at": plant.deleted_at},
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            plant.is_deleted = True
            plant.deleted_at = timezone.now()
            plant.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

            # Revoke active label token if present
            ct = ContentType.objects.get_for_model(Plant)
            label = (
                Label.objects
                .select_related("active_token")
                .filter(user=request.user, content_type=ct, object_id=plant.id)
                .first()
            )
            if label and label.active_token_id:
                LabelToken.objects.filter(pk=label.active_token_id, revoked_at__isnull=True).update(
                    revoked_at=timezone.now()
                )
                label.active_token = None
                label.save(update_fields=["active_token", "updated_at"])

        return Response(
            {"id": plant.id, "archived": True, "deleted_at": plant.deleted_at},
            status=status.HTTP_200_OK,
        )
