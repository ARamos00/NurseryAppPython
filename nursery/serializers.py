from rest_framework import serializers
from .models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    Event,
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
