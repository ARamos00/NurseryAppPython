from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import OwnedModel

# ---- existing domain models ----

class Taxon(OwnedModel):
    scientific_name = models.CharField(max_length=200)
    cultivar = models.CharField(max_length=100, blank=True)
    clone_code = models.CharField(max_length=50, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scientific_name", "cultivar", "clone_code"],
                name="uniq_taxon_per_user_sc_cultivar_clone",
            )
        ]
        ordering = ["scientific_name", "cultivar", "clone_code"]
        indexes = [
            models.Index(fields=["user", "scientific_name"]),
        ]

    def __str__(self) -> str:
        parts = [self.scientific_name]
        if self.cultivar:
            parts.append(f"‘{self.cultivar}’")
        if self.clone_code:
            parts.append(f"[{self.clone_code}]")
        return " ".join(parts)


class MaterialType(models.TextChoices):
    SEED = "SEED", "Seed"
    CUTTING = "CUTTING", "Cutting"
    SCION = "SCION", "Scion"
    LAYER = "LAYER", "Layer"
    DIVISION = "DIVISION", "Division"
    TISSUE = "TISSUE", "Tissue Culture"
    OTHER = "OTHER", "Other"


class PlantMaterial(OwnedModel):
    taxon = models.ForeignKey(Taxon, on_delete=models.CASCADE, related_name="materials")
    material_type = models.CharField(max_length=16, choices=MaterialType.choices)
    lot_code = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional supplier/batch code for traceability.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "taxon"]),
            models.Index(fields=["user", "material_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "taxon", "material_type", "lot_code"],
                name="uniq_material_per_user_taxon_type_lot",
                condition=~Q(lot_code=""),
            )
        ]

    def __str__(self) -> str:
        label = f"{self.get_material_type_display()} • {self.taxon}"
        if self.lot_code:
            label += f" • {self.lot_code}"
        return label


class PropagationMethod(models.TextChoices):
    SEED_SOWING = "SEED_SOWING", "Seed sowing"
    CUTTING_ROOTING = "CUTTING_ROOTING", "Cutting rooting"
    GRAFTING = "GRAFTING", "Grafting"
    AIR_LAYER = "AIR_LAYER", "Air layering"
    DIVISION = "DIVISION", "Division"
    TISSUE_CULTURE = "TISSUE_CULTURE", "Tissue culture"
    OTHER = "OTHER", "Other"


class BatchStatus(models.TextChoices):
    STARTED = "STARTED", "Started"
    GERMINATING = "GERMINATING", "Germinating/Rooting"
    POTTED = "POTTED", "Potted up"
    GROWING = "GROWING", "Growing"
    DORMANT = "DORMANT", "Dormant"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    DISCARDED = "DISCARDED", "Discarded"


class PropagationBatch(OwnedModel):
    material = models.ForeignKey(PlantMaterial, on_delete=models.CASCADE, related_name="batches")
    method = models.CharField(max_length=24, choices=PropagationMethod.choices)
    status = models.CharField(max_length=16, choices=BatchStatus.choices, default=BatchStatus.STARTED)
    started_on = models.DateField(default=timezone.now)
    quantity_started = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_on", "-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "material"]),
            models.Index(fields=["user", "started_on"]),
        ]

    def __str__(self) -> str:
        return f"Batch #{self.pk} • {self.get_method_display()} • {self.material}"


class PlantStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DORMANT = "DORMANT", "Dormant"
    SOLD = "SOLD", "Sold"
    DEAD = "DEAD", "Dead"
    DISCARDED = "DISCARDED", "Discarded"


class Plant(OwnedModel):
    taxon = models.ForeignKey(Taxon, on_delete=models.CASCADE, related_name="plants")
    batch = models.ForeignKey(
        PropagationBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="plants"
    )
    status = models.CharField(max_length=12, choices=PlantStatus.choices, default=PlantStatus.ACTIVE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    acquired_on = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "taxon"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        b = f" (batch {self.batch_id})" if self.batch_id else ""
        return f"{self.quantity} × {self.taxon}{b} [{self.get_status_display()}]"


class EventType(models.TextChoices):
    NOTE = "NOTE", "Note"
    SOW = "SOW", "Sow / Start"
    GERMINATE = "GERMINATE", "Germination"
    POT_UP = "POT_UP", "Pot up / Transplant"
    PRUNE = "PRUNE", "Prune"
    MOVE = "MOVE", "Move / Location change"
    WATER = "WATER", "Water"
    FERTILIZE = "FERTILIZE", "Fertilize"
    SELL = "SELL", "Sold"
    DISCARD = "DISCARD", "Discard"


class Event(OwnedModel):
    """
    Timestamped action/observation for either a batch OR a plant.
    Exactly one of (batch, plant) must be set; enforced by constraint + clean().
    """
    batch = models.ForeignKey(
        PropagationBatch, on_delete=models.CASCADE, null=True, blank=True, related_name="events"
    )
    plant = models.ForeignKey(
        Plant, on_delete=models.CASCADE, null=True, blank=True, related_name="events"
    )
    event_type = models.CharField(max_length=16, choices=EventType.choices, default=EventType.NOTE)
    happened_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    quantity_delta = models.IntegerField(
        null=True,
        blank=True,
        help_text="Optional: record changes (+/-) to counts (e.g., +5 germinated, -2 losses).",
    )

    class Meta:
        ordering = ["-happened_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                name="event_xor_batch_or_plant",
                check=(
                    (Q(batch__isnull=False) & Q(plant__isnull=True)) |
                    (Q(batch__isnull=True) & Q(plant__isnull=False))
                ),
            )
        ]
        indexes = [
            models.Index(fields=["user", "happened_at"]),
            models.Index(fields=["user", "event_type"]),
            models.Index(fields=["user", "batch"]),
            models.Index(fields=["user", "plant"]),
        ]

    def clean(self):
        super().clean()
        if self.batch_id and self.plant_id:
            raise ValidationError("Choose either a batch or a plant, not both.")
        owner_id = self.user_id
        if self.batch_id and self.batch.user_id != owner_id:
            raise ValidationError("Event.user must match the selected batch owner.")
        if self.plant_id and self.plant.user_id != owner_id:
            raise ValidationError("Event.user must match the selected plant owner.")

    def __str__(self) -> str:
        target = f"batch {self.batch_id}" if self.batch_id else f"plant {self.plant_id}"
        return f"{self.get_event_type_display()} @ {self.happened_at:%Y-%m-%d %H:%M} → {target}"


# ---- Phase 2a: Labels & Tokens (QR) ----
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Label(OwnedModel):
    """
    A perpetual label attached to a user-owned target (Plant, PropagationBatch, or PlantMaterial).
    Exactly one active token at a time (managed at the application level).
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")

    active_token = models.OneToOneField(
        "LabelToken",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="is_active_for",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content_type", "object_id"],
                name="uniq_label_per_user_target",
            )
        ]
        indexes = [
            models.Index(fields=["user", "content_type", "object_id"]),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Label<{self.id}> for {self.content_type.model}:{self.object_id}"


class LabelToken(models.Model):
    """
    A public token for a label. We store only SHA-256 of the raw token; raw value is never persisted.
    """
    label = models.ForeignKey(Label, on_delete=models.CASCADE, related_name="tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=12)  # first characters of the raw token for support
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["token_hash"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"LabelToken<{self.prefix}> ({state}) for label {self.label_id}"
