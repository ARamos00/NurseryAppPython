from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import OwnedModel


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
    started_on = models.DateField(default=timezone.now)  # consider timezone.localdate later
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

    # ---- Phase 2b helper: derived availability ----
    def available_quantity(self) -> int:
        """
        Remaining units available in the batch (not yet harvested or culled).
        Computed as: quantity_started + sum(quantity_delta for events on this batch)
        where harvest/cull write negative deltas.
        """
        agg = self.events.aggregate(total=Sum("quantity_delta"))
        total_delta = agg["total"] or 0
        return int(self.quantity_started + total_delta)


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
    acquired_on = models.DateField(default=timezone.now)  # consider timezone.localdate later
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


# ---- Labels & Tokens (Phase 2a) ----
from django.contrib.contenttypes.fields import GenericForeignKey  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402


class Label(OwnedModel):
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
    label = models.ForeignKey(Label, on_delete=models.CASCADE, related_name="tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=12)
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


class LabelVisit(OwnedModel):
    """
    A single scan of a Label's public URL.
    Privacy: no linkage to an authenticated viewer; only coarse request metadata.
    """
    label = models.ForeignKey("nursery.Label", on_delete=models.CASCADE, related_name="visits")
    token = models.ForeignKey("nursery.LabelToken", on_delete=models.SET_NULL, null=True, blank=True, related_name="visits")

    requested_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    referrer = models.CharField(max_length=512, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("label", "-requested_at")),
            models.Index(fields=("user", "-requested_at")),
        ]

    def __str__(self) -> str:
        return f"Visit #{self.pk} • Label {self.label_id} @ {self.requested_at:%Y-%m-%d %H:%M:%S}"


class AuditAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"


class AuditLog(models.Model):
    """
    Lightweight audit trail for API-originated mutations.
    - `user` is the *owner* of the mutated record (for tenancy scoping).
    - `actor` is the authenticated user who performed the mutation (usually the same as `user`).
    - `content_type` + `object_id` identifies the mutated object.
    - `action` ∈ {"create","update","delete"}.
    - `changes`: JSON dictionary of field diffs; for updates stores {field: [old, new]}.
      For creates, stores {"_after": {...snapshot...}}; for deletes, {"_before": {...snapshot...}}.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actor_logs",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.BigIntegerField()
    action = models.CharField(max_length=12, choices=AuditAction.choices)
    changes = models.JSONField(default=dict, blank=True)

    request_id = models.CharField(max_length=64, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "content_type", "object_id"]),
            models.Index(fields=["action"]),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover (repr aid)
        return f"AuditLog<{self.action} {self.content_type.app_label}.{self.content_type.model}:{self.object_id}>"


from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

class WebhookEventType(models.TextChoices):
    EVENT_CREATED = "event.created", "Event created"
    PLANT_STATUS_CHANGED = "plant.status_changed", "Plant status changed"
    BATCH_STATUS_CHANGED = "batch.status_changed", "Batch status changed"

class WebhookDeliveryStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"

class WebhookEndpoint(OwnedModel):
    """
    A user-owned webhook endpoint. `secret` is used to compute HMAC-SHA256
    signatures for each POST. Never return `secret` via API; only allow write.
    """
    name = models.CharField(max_length=100, blank=True, default="")
    url = models.URLField(max_length=500)
    # List of event type strings (TextChoices values). [] or ["*"] means "all".
    event_types = models.JSONField(default=list, blank=True)
    secret = models.CharField(max_length=128)  # stored as-is; do NOT expose
    secret_last4 = models.CharField(max_length=8, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "url"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="webhook_url_https_or_allowed",
                check=Q(url__startswith="https://") | Q(url__startswith="http://"),
            )
        ]

    def clean(self):
        super().clean()
        # App-level HTTPS enforcement happens in serializer (has settings access).
        # Keep model clean permissive (so tests/dev can store http:// if allowed).

        # Validate URL shape early
        try:
            URLValidator()(self.url)
        except DjangoValidationError as e:
            raise ValidationError({"url": e.messages})

        # Normalize event_types
        if not isinstance(self.event_types, list):
            raise ValidationError({"event_types": "Must be a list of event type strings."})

        # Cache secret tail for display
        if self.secret and not self.secret_last4:
            self.secret_last4 = self.secret[-4:]

    def __str__(self) -> str:
        return f"WebhookEndpoint<{self.id}> → {self.url} ({'active' if self.is_active else 'inactive'})"


class WebhookDelivery(OwnedModel):
    """
    A single delivery attempt payload for an endpoint. Immutable payload, mutable
    attempt/response fields. Owner equals endpoint.user (duplicated for scoping).
    """
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    event_type = models.CharField(max_length=48, choices=WebhookEventType.choices)
    payload = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=10, choices=WebhookDeliveryStatus.choices, default=WebhookDeliveryStatus.QUEUED)
    attempt_count = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    response_status = models.IntegerField(null=True, blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    response_body = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    request_duration_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "event_type"]),
            models.Index(fields=["endpoint", "status"]),
            models.Index(fields=["-next_attempt_at"]),
        ]

    def __str__(self) -> str:
        return f"Delivery<{self.id}> {self.event_type} → ep#{self.endpoint_id} [{self.status}]"