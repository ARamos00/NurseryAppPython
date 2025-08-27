from __future__ import annotations

from typing import Optional  # may be used by other ops in this module

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.utils.concurrency import compute_etag, require_if_match
from core.utils.idempotency import idempotent
from nursery.models import (
    PropagationBatch,
    BatchStatus,
    Plant,
    PlantStatus,
    Event,
    EventType,
    Label,
    LabelToken,
)
# Shared OpenAPI components
from nursery.schema import (
    IF_MATCH_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENCY_EXAMPLE,
    VALIDATION_ERROR_RESPONSE,
    ERROR_RESPONSE,
)

# ---------- Serializer definitions (local to ops) ----------

class HarvestRequestSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    acquired_on = serializers.DateField(required=False)
    status = serializers.ChoiceField(choices=PlantStatus.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

class HarvestResponseSerializer(serializers.Serializer):
    plant_id = serializers.IntegerField()
    batch_id = serializers.IntegerField()
    available_quantity = serializers.IntegerField()
    batch_status = serializers.ChoiceField(choices=BatchStatus.choices)
    batch_event_id = serializers.IntegerField()
    plant_event_id = serializers.IntegerField()

class CullRequestSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True)

class CullResponseSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    available_quantity = serializers.IntegerField()
    batch_event_id = serializers.IntegerField()

class CompleteRequestSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=False)

class CompleteResponseSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    batch_status = serializers.ChoiceField(choices=BatchStatus.choices)


# ---------- Mixin with actions ----------

class BatchOpsMixin:
    """
    Adds stock/flow operations to PropagationBatchViewSet:
      - harvest: promote quantity from batch into a Plant
      - cull: reduce remaining quantity on batch
      - complete: close batch when no remaining quantity (or force)
      - archive: soft-delete the batch and revoke labels
    All actions write Events to maintain derived availability where appropriate.
    """

    @extend_schema(
        tags=["Batches: Ops"],
        parameters=[IF_MATCH_HEADER, IDEMPOTENCY_KEY_HEADER],
        request=HarvestRequestSerializer,
        responses={
            201: HarvestResponseSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            412: ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description=(
            "Move quantity from the batch into a new Plant record. "
            "Writes a negative `quantity_delta` Event on the batch and a positive Event on the plant."
        ),
    )
    @action(detail=True, methods=["post"], url_path="harvest")
    @idempotent
    def harvest(self, request: Request, pk: str | None = None) -> Response:
        batch: PropagationBatch = self.get_object()
        require_if_match(request, batch.updated_at)

        data = HarvestRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        qty = int(data.validated_data["quantity"])
        acquired_on = data.validated_data.get("acquired_on") or timezone.now().date()
        plant_status = data.validated_data.get("status") or PlantStatus.ACTIVE
        notes = data.validated_data.get("notes", "")

        available = batch.available_quantity()
        if qty > available:
            return Response(
                {"quantity": [f"Requested {qty} exceeds available {available}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Create plant from batch.taxon
            plant = Plant.objects.create(
                user=request.user,
                taxon=batch.material.taxon,
                batch=batch,
                status=plant_status,
                quantity=qty,
                acquired_on=acquired_on,
                notes=notes,
            )
            # Batch event: negative delta
            be = Event.objects.create(
                user=request.user,
                batch=batch,
                event_type=EventType.POT_UP,
                happened_at=timezone.now(),
                notes=notes or "Harvest to plant",
                quantity_delta=-qty,
            )
            # Plant event: positive delta
            pe = Event.objects.create(
                user=request.user,
                plant=plant,
                event_type=EventType.POT_UP,
                happened_at=timezone.now(),
                notes=notes or f"Created from batch {batch.id}",
                quantity_delta=qty,
            )

        response = Response(
            {
                "plant_id": plant.id,
                "batch_id": batch.id,
                "available_quantity": batch.available_quantity(),
                "batch_status": batch.status,
                "batch_event_id": be.id,
                "plant_event_id": pe.id,
            },
            status=status.HTTP_201_CREATED,
        )
        etag = compute_etag(batch.updated_at)
        if etag:
            response["ETag"] = etag
        return response

    @extend_schema(
        tags=["Batches: Ops"],
        parameters=[IF_MATCH_HEADER, IDEMPOTENCY_KEY_HEADER],
        request=CullRequestSerializer,
        responses={
            200: CullResponseSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            412: ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description=(
            "Reduce remaining batch quantity (losses/discards). "
            "Writes a negative `quantity_delta` Event on the batch."
        ),
    )
    @action(detail=True, methods=["post"], url_path="cull")
    @idempotent
    def cull(self, request: Request, pk: str | None = None) -> Response:
        batch: PropagationBatch = self.get_object()
        require_if_match(request, batch.updated_at)

        data = CullRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        qty = int(data.validated_data["quantity"])
        notes = data.validated_data.get("notes", "")

        available = batch.available_quantity()
        if qty > available:
            return Response(
                {"quantity": [f"Requested {qty} exceeds available {available}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            be = Event.objects.create(
                user=request.user,
                batch=batch,
                event_type=EventType.DISCARD,
                happened_at=timezone.now(),
                notes=notes or "Cull quantity",
                quantity_delta=-qty,
            )

        response = Response(
            {
                "batch_id": batch.id,
                "available_quantity": batch.available_quantity(),
                "batch_event_id": be.id,
            },
            status=status.HTTP_200_OK,
        )
        etag = compute_etag(batch.updated_at)
        if etag:
            response["ETag"] = etag
        return response

    @extend_schema(
        tags=["Batches: Ops"],
        parameters=[IF_MATCH_HEADER, IDEMPOTENCY_KEY_HEADER],
        request=CompleteRequestSerializer,
        responses={
            200: CompleteResponseSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            412: ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description="Mark a batch as COMPLETED. Requires zero remaining quantity unless `force=true`.",
    )
    @action(detail=True, methods=["post"], url_path="complete")
    @idempotent
    def complete(self, request: Request, pk: str | None = None) -> Response:
        batch: PropagationBatch = self.get_object()
        require_if_match(request, batch.updated_at)

        data = CompleteRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        force = bool(data.validated_data.get("force", False))

        remaining = batch.available_quantity()
        if remaining != 0 and not force:
            return Response(
                {"non_field_errors": [f"Batch has {remaining} remaining. Use force=true to override."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            batch.status = BatchStatus.COMPLETED
            batch.save(update_fields=["status", "updated_at"])

        response = Response({"batch_id": batch.id, "batch_status": batch.status}, status=status.HTTP_200_OK)
        etag = compute_etag(batch.updated_at)
        if etag:
            response["ETag"] = etag
        return response

    # -------- Archive (soft-delete) -------------------------------------------

    class _ArchiveResponse(serializers.Serializer):
        id = serializers.IntegerField()
        archived = serializers.BooleanField()
        deleted_at = serializers.DateTimeField()

        class Meta:
            # Unique component name for OpenAPI to avoid collisions
            ref_name = "BatchArchiveResponse"

    @extend_schema(
        tags=["Batches: Ops"],
        parameters=[IF_MATCH_HEADER, IDEMPOTENCY_KEY_HEADER],
        responses={
            200: _ArchiveResponse,
            412: ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description=(
            "Soft-delete (archive) this batch. Sets is_deleted=true and deleted_at now. "
            "Revokes any active label token so the public page stops resolving. "
            "Idempotent: repeated calls are safe."
        ),
    )
    @action(detail=True, methods=["post"], url_path="archive")
    @idempotent
    def archive(self, request: Request, pk: str | None = None) -> Response:
        batch: PropagationBatch = self.get_object()
        require_if_match(request, batch.updated_at)

        if batch.is_deleted:
            return Response(
                {"id": batch.id, "archived": True, "deleted_at": batch.deleted_at},
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            batch.is_deleted = True
            batch.deleted_at = timezone.now()
            batch.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

            # Revoke active label token if present
            ct = ContentType.objects.get_for_model(PropagationBatch)
            label = (
                Label.objects
                .select_related("active_token")
                .filter(user=request.user, content_type=ct, object_id=batch.id)
                .first()
            )
            if label and label.active_token_id:
                LabelToken.objects.filter(pk=label.active_token_id, revoked_at__isnull=True).update(
                    revoked_at=timezone.now()
                )
                label.active_token = None
                label.save(update_fields=["active_token", "updated_at"])

        return Response(
            {"id": batch.id, "archived": True, "deleted_at": batch.deleted_at},
            status=status.HTTP_200_OK,
        )
