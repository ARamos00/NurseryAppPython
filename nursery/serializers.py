from __future__ import annotations

from typing import Any, Dict

from django.contrib.auth import get_user_model
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


class TaxonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Taxon
        fields = [
            "id", "scientific_name", "cultivar", "clone_code",
            "created_at", "updated_at", "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user"]


class PlantMaterialSerializer(serializers.ModelSerializer):
    taxon_display = serializers.StringRelatedField(source="taxon", read_only=True)

    class Meta:
        model = PlantMaterial
        fields = [
            "id", "taxon", "taxon_display", "material_type", "lot_code", "notes",
            "created_at", "updated_at", "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user", "taxon_display"]


class PropagationBatchSerializer(serializers.ModelSerializer):
    material_display = serializers.StringRelatedField(source="material", read_only=True)

    class Meta:
        model = PropagationBatch
        fields = [
            "id", "material", "material_display", "method", "status",
            "started_on", "quantity_started", "notes",
            "created_at", "updated_at", "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user", "material_display"]


class PlantSerializer(serializers.ModelSerializer):
    taxon_display = serializers.StringRelatedField(source="taxon", read_only=True)
    batch_display = serializers.StringRelatedField(source="batch", read_only=True)

    class Meta:
        model = Plant
        fields = [
            "id", "taxon", "taxon_display", "batch", "batch_display",
            "status", "quantity", "acquired_on", "notes",
            "created_at", "updated_at", "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user", "taxon_display", "batch_display"]


class EventSerializer(serializers.ModelSerializer):
    batch_display = serializers.StringRelatedField(source="batch", read_only=True)
    plant_display = serializers.StringRelatedField(source="plant", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id", "batch", "batch_display", "plant", "plant_display",
            "event_type", "happened_at", "notes", "quantity_delta",
            "created_at", "updated_at", "user",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "user", "batch_display", "plant_display"]

    def validate(self, attrs):
        """
        Enforce XOR(batch, plant) and ownership alignment at the serializer level
        for clear API errors (model.clean also enforces).
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)

        batch = attrs.get("batch") if "batch" in attrs else getattr(self.instance, "batch", None)
        plant = attrs.get("plant") if "plant" in attrs else getattr(self.instance, "plant", None)

        if bool(batch) == bool(plant):
            raise serializers.ValidationError("Exactly one of 'batch' or 'plant' must be provided.")

        if user and getattr(user, "is_authenticated", False):
            if batch and batch.user_id != user.id:
                raise serializers.ValidationError("Selected batch does not belong to the current user.")
            if plant and plant.user_id != user.id:
                raise serializers.ValidationError("Selected plant does not belong to the current user.")

        return attrs


# ---- Phase 2a: Labels ----

class LabelTargetField(serializers.Field):
    """
    {"type": "plant"|"batch"|"material", "id": <int>}
    Serializes to the same shape. Validates ownership.
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
        model = type(value)
        for k, v in self._type_map.items():
            if v is model:
                return {"type": k, "id": value.pk}
        return {"type": "unknown", "id": None}

    def to_internal_value(self, data):
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
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False) or obj.user_id != user.id:
            self.fail("forbidden")
        return obj


class LabelSerializer(serializers.ModelSerializer):
    # Do not set source="target"; DRF infers it by default. This avoids assertion errors.
    target = LabelTargetField()
    active = serializers.SerializerMethodField()

    class Meta:
        model = Label
        fields = ["id", "target", "active", "created_at", "updated_at", "user"]
        read_only_fields = ["id", "created_at", "updated_at", "user", "active"]

    def get_active(self, obj: Label) -> bool:
        return bool(obj.active_token_id)


class LabelCreateSerializer(serializers.ModelSerializer):
    """
    Used for create and rotate responses — returns raw token once.
    """
    # Do not set source="target" here either.
    target = LabelTargetField()
    token = serializers.CharField(read_only=True)
    public_url = serializers.CharField(read_only=True)

    class Meta:
        model = Label
        fields = ["id", "target", "token", "public_url", "created_at", "updated_at", "user"]
        read_only_fields = ["id", "token", "public_url", "created_at", "updated_at", "user"]

class AuditActorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()


class AuditTargetSerializer(serializers.Serializer):
    model = serializers.CharField()
    id = serializers.IntegerField()


class AuditLogSerializer(serializers.ModelSerializer):
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
        if not obj.actor_id:
            return None
        return {"id": obj.actor_id, "username": getattr(obj.actor, "username", "")}

    def get_target(self, obj: AuditLog) -> Dict[str, Any]:
        ct: ContentType = obj.content_type
        model_label = f"{ct.app_label}.{ct.model}"
        return {"model": model_label, "id": obj.object_id}

class LabelStatsSerializer(serializers.Serializer):
    label_id = serializers.IntegerField()
    total_visits = serializers.IntegerField()
    last_7d = serializers.IntegerField()
    last_30d = serializers.IntegerField()