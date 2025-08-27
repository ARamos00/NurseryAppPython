"""
DRF serializers for Nursery domain objects (taxa, materials, batches, plants, events),
labels (including public tokens), audit logs, and label analytics.

Goals
-----
- Provide thin, explicit serializers over `nursery.models` without altering behavior.
- Enforce critical invariants early (e.g., Event targets exactly one of `batch` XOR
  `plant`) and validate tenant ownership where user-supplied FKs are accepted.

Security & tenancy
------------------
- Creation/mutation serializers never accept a `user` value from the client; views
  must set `instance.user = request.user` (or rely on `perform_create` in ViewSets).
- `LabelTargetField` verifies ownership of the target object so labels cannot be
  attached across tenants.
- Read-only fields include display helpers to avoid leaking sensitive internals.

Concurrency/Idempotency
-----------------------
- ETag/If-Match and idempotency are enforced at the view/util layer, not here.
- These serializers are compatible with those helpers (no side-effecting code).
"""

from __future__ import annotations

from typing import Any, Dict

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from .models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    Event,
    Label,
    LabelToken,
    LabelVisit,
    AuditLog,
)


# ----------------------------
# Core model serializers
# ----------------------------
class TaxonSerializer(serializers.ModelSerializer):
    """CRUD representation of `Taxon` (botanical identity fields only)."""

    class Meta:
        model = Taxon
        fields = [
            "id",
            "scientific_name",
            "cultivar",
            "clone_code",
            "created_at",
            "updated_at",
            "user",
        ]
        # NOTE: `user` is read-only; views set it to `request.user` on create/update.
        read_only_fields = ["id", "created_at", "updated_at", "user"]


class PlantMaterialSerializer(serializers.ModelSerializer):
    """Material lots per taxon; exposes a string display for convenience in UIs."""
    taxon_display = serializers.StringRelatedField(source="taxon", read_only=True)

    class Meta:
        model = PlantMaterial
        fields = [
            "id",
            "taxon",
            "taxon_display",
            "material_type",
            "lot_code",
            "notes",
            "created_at",
            "updated_at",
            "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user", "taxon_display"]


class PropagationBatchSerializer(serializers.ModelSerializer):
    """Batches of starts (seeds/cuttings/etc.) with a friendly material display."""
    material_display = serializers.StringRelatedField(source="material", read_only=True)

    class Meta:
        model = PropagationBatch
        fields = [
            "id",
            "material",
            "material_display",
            "method",
            "status",
            "started_on",
            "quantity_started",
            "notes",
            "created_at",
            "updated_at",
            "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user", "material_display"]


class PlantSerializer(serializers.ModelSerializer):
    """Individual plants or grouped counts; includes taxon/batch string displays."""
    taxon_display = serializers.StringRelatedField(source="taxon", read_only=True)
    batch_display = serializers.StringRelatedField(source="batch", read_only=True)

    class Meta:
        model = Plant
        fields = [
            "id",
            "taxon",
            "taxon_display",
            "batch",
            "batch_display",
            "status",
            "quantity",
            "acquired_on",
            "notes",
            "created_at",
            "updated_at",
            "user",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "user",
            "taxon_display",
            "batch_display",
        ]


class EventSerializer(serializers.ModelSerializer):
    """
    Events target exactly one of (`batch`, `plant`).

    - Serializer-level validation mirrors `Event.clean()` to present clear API errors.
    - Also verifies that the selected target is owned by the current user.
    """
    batch_display = serializers.StringRelatedField(source="batch", read_only=True)
    plant_display = serializers.StringRelatedField(source="plant", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "batch",
            "batch_display",
            "plant",
            "plant_display",
            "event_type",
            "happened_at",
            "notes",
            "quantity_delta",
            "created_at",
            "updated_at",
            "user",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "user",
            "batch_display",
            "plant_display",
        ]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enforce XOR(batch, plant) and per-tenant ownership alignment.

        Args:
            attrs: Incoming attributes for create/update.

        Raises:
            serializers.ValidationError: If both/neither targets are provided or
            if the chosen target doesn't belong to the authenticated user.

        Notes:
            - Model-level `clean()` and a DB CheckConstraint also enforce the XOR
              invariant; validating here yields friendlier API messages.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)

        # Use pending attrs if present, otherwise fall back to instance values.
        batch = attrs.get("batch") if "batch" in attrs else getattr(self.instance, "batch", None)
        plant = attrs.get("plant") if "plant" in attrs else getattr(self.instance, "plant", None)

        if bool(batch) == bool(plant):
            raise serializers.ValidationError("Exactly one of 'batch' or 'plant' must be provided.")

        # SECURITY: Ensure the event cannot reference objects from another tenant.
        if user and getattr(user, "is_authenticated", False):
            if batch and batch.user_id != user.id:
                raise serializers.ValidationError("Selected batch does not belong to the current user.")
            if plant and plant.user_id != user.id:
                raise serializers.ValidationError("Selected plant does not belong to the current user.")

        return attrs


# ----------------------------
# Labels (Phase 2a)
# ----------------------------
class LabelTargetField(serializers.Field):
    """
    Polymorphic target selector for labels.

    Shape (input & output):
        {"type": "plant" | "batch" | "material", "id": <int>}

    Behavior:
        - Serializes a model instance to the same compact shape.
        - Validates that the target exists and is owned by the current user.
    """
    default_error_messages = {
        "invalid": "Expected an object with 'type' and 'id'.",
        "unknown_type": "Unknown target type.",
        "not_found": "Target not found.",
        "forbidden": "Target does not belong to the current user.",
    }

    _type_map = {
        "plant": Plant,
        "batch": PropagationBatch,
        "material": PlantMaterial,
    }

    def to_representation(self, value):
        """Return {"type": <key>, "id": <pk>} for the given model instance."""
        model = type(value)
        for k, v in self._type_map.items():
            if v is model:
                return {"type": k, "id": value.pk}
        return {"type": "unknown", "id": None}

    def to_internal_value(self, data):
        """Validate shape, resolve instance, and enforce tenant ownership."""
        if not isinstance(data, dict) or "type" not in data or "id" not in data:
            self.fail("invalid")
        target_type = data["type"]
        pk = data["id"]
        Model = self._type_map.get(target_type)
        if not Model:
            self.fail("unknown_type")
        try:
            obj = Model.objects.get(pk=pk)
        except Model.DoesNotExist:
            self.fail("not_found")

        # SECURITY: Labels can only attach to objects owned by the requester.
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False) or obj.user_id != user.id:
            self.fail("forbidden")
        return obj


class LabelSerializer(serializers.ModelSerializer):
    """
    Minimal label surface for index/detail: exposes target and whether a token is active.

    Notes:
        - `target` is polymorphic via `LabelTargetField`.
        - `active` reflects presence of `active_token_id` (no token contents exposed).
    """
    # Do not set source="target"; DRF infers it by default. This avoids assertion errors.
    target = LabelTargetField()
    active = serializers.SerializerMethodField()

    class Meta:
        model = Label
        fields = ["id", "target", "active", "created_at", "updated_at", "user"]
        read_only_fields = ["id", "created_at", "updated_at", "user", "active"]

    def get_active(self, obj: Label) -> bool:
        """Return True when the label currently has a non-revoked active token."""
        return bool(obj.active_token_id)


class LabelCreateSerializer(serializers.ModelSerializer):
    """
    Response shape for label creation/rotation.

    - Returns `token` (raw secret) and `public_url` **once** so the owner can save it.
    - Subsequent reads should use `LabelSerializer` and never reveal the token again.
    """
    target = LabelTargetField()
    token = serializers.CharField(read_only=True)
    public_url = serializers.CharField(read_only=True)

    class Meta:
        model = Label
        fields = ["id", "target", "token", "public_url", "created_at", "updated_at", "user"]
        read_only_fields = ["id", "token", "public_url", "created_at", "updated_at", "user"]


# ----------------------------
# Audit log
# ----------------------------
class AuditActorSerializer(serializers.Serializer):
    """Compact representation of an actor (usually equals the owner)."""
    id = serializers.IntegerField()
    username = serializers.CharField()


class AuditTargetSerializer(serializers.Serializer):
    """Polymorphic reference to the mutated object (app_label.model + id)."""
    model = serializers.CharField()
    id = serializers.IntegerField()


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only audit entries with actor/target expansions.

    Notes:
        - `changes` payload is model- and action-dependent (see model docstring).
        - Intended for dashboards and CSV/JSON exports; no writes via API.
    """
    when = serializers.DateTimeField(source="created_at", read_only=True)
    actor = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "when",
            "actor",
            "target",
            "action",
            "changes",
            "request_id",
            "ip",
            "user_agent",
        ]
        read_only_fields = fields

    def get_actor(self, obj: AuditLog) -> Dict[str, Any] | None:
        """Inline the actor as {id, username} or null when missing."""
        if not obj.actor_id:
            return None
        return {"id": obj.actor_id, "username": getattr(obj.actor, "username", "")}

    def get_target(self, obj: AuditLog) -> Dict[str, Any]:
        """Inline the content type + object id as {model, id}."""
        ct: ContentType = obj.content_type
        model_label = f"{ct.app_label}.{ct.model}"
        return {"model": model_label, "id": obj.object_id}


# ----------------------------
# Label analytics
# ----------------------------
class LabelStatsSerializer(serializers.Serializer):
    """
    Compact counts used when no `?days` param is provided.

    Fields:
        - label_id: DB id of the label
        - total_visits: all-time
        - last_7d / last_30d: recent windows for quick cards
    """
    label_id = serializers.IntegerField()
    total_visits = serializers.IntegerField()
    last_7d = serializers.IntegerField()
    last_30d = serializers.IntegerField()


class LabelStatsQuerySerializer(serializers.Serializer):
    """
    Optional stats query params.

    Args:
        days (int, 1..365): When present, the API returns a windowed series payload.
    """
    days = serializers.IntegerField(min_value=1, max_value=365, required=False)


class LabelVisitSeriesPointSerializer(serializers.Serializer):
    """Single (date, visits) point in a windowed time series."""
    date = serializers.DateField()
    visits = serializers.IntegerField()


class LabelStatsWithSeriesSerializer(serializers.Serializer):
    """
    Full payload when `?days` is present: legacy counts + window metadata + series.

    Shape:
        {
          "label_id": int,
          "total_visits": int,
          "last_7d": int,
          "last_30d": int,
          "window_days": int,
          "start_date": "YYYY-MM-DD",
          "end_date": "YYYY-MM-DD",
          "series": [{"date": "...", "visits": int}, ...]
        }
    """
    # legacy counts
    label_id = serializers.IntegerField()
    total_visits = serializers.IntegerField()
    last_7d = serializers.IntegerField()
    last_30d = serializers.IntegerField()

    # window + series
    window_days = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    series = LabelVisitSeriesPointSerializer(many=True)
