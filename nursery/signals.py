"""Domain signals: label lifecycle and webhook emitters (feature-flagged).

Label lifecycle
---------------
- On Plant status transitions to a terminal state (SOLD/DEAD/DISCARDED), revoke
  active label tokens so public pages stop resolving.
- On deletion of Plant / PropagationBatch / PlantMaterial, delete their labels.
- Helpers are idempotent; revocation and deletes are safe to call repeatedly.

Webhooks (optional)
-------------------
- Feature-flagged via `WEBHOOKS_ENABLE_AUTO_EMIT` (default False). When enabled:
    * Event created -> enqueue `event.created`
    * Plant status change -> enqueue `plant.status_changed`
    * Batch status change -> enqueue `batch.status_changed`
- `enqueue_for_user()` creates QUEUED deliveries only; a separate worker handles
  HTTPS + signing + retries to keep request latency low.

Security
--------
- All webhook payloads are scoped to the record owner (`instance.user`).
- Do NOT include sensitive fields in payloads; keep them minimal and event-driven.
"""

from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Plant,
    PlantStatus,
    PropagationBatch,
    PlantMaterial,
    Label,
    LabelToken,
    Event,
    WebhookEventType,
)

from core.utils.webhooks import enqueue_for_user


# ==============================================================================
# Label lifecycle handlers (existing behavior preserved)
# ==============================================================================

def _revoke_active_token(label: Label) -> None:
    """
    Revoke active token (if any) and detach from label.
    Safe to call multiple times.
    """
    if label.active_token_id:
        LabelToken.objects.filter(pk=label.active_token_id, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        label.active_token = None
        label.save(update_fields=["active_token", "updated_at"])


def _delete_labels_for_target(model_cls, obj_id: int) -> None:
    """Delete all labels for the given model/primary key pair."""
    ct = ContentType.objects.get_for_model(model_cls)
    Label.objects.filter(content_type=ct, object_id=obj_id).delete()


@receiver(pre_save, sender=Plant, dispatch_uid="nursery.labels.plant_status_revoke_labels")
def plant_status_revoke_labels(sender, instance: Plant, **kwargs):
    """
    When a Plant transitions to a terminal status (SOLD/DEAD/DISCARDED),
    revoke any active label tokens so public pages stop resolving.
    """
    if not instance.pk:
        return
    try:
        prior = Plant.objects.only("status").get(pk=instance.pk)
    except Plant.DoesNotExist:
        return

    terminal = {PlantStatus.SOLD, PlantStatus.DEAD, PlantStatus.DISCARDED}
    if prior.status in terminal and instance.status in terminal:
        # already terminal -> terminal; nothing to do
        return
    if instance.status in terminal:
        # SECURITY: revoke owner's public tokens eagerly to avoid stale public access.
        ct = ContentType.objects.get_for_model(Plant)
        for label in Label.objects.filter(content_type=ct, object_id=instance.pk):
            _revoke_active_token(label)


@receiver(post_delete, sender=Plant, dispatch_uid="nursery.labels.plant_delete_cleanup")
def plant_delete_cleanup_labels(sender, instance: Plant, **kwargs):
    """Delete labels for a Plant once it's hard-deleted."""
    _delete_labels_for_target(Plant, instance.pk)


@receiver(post_delete, sender=PropagationBatch, dispatch_uid="nursery.labels.batch_delete_cleanup")
def batch_delete_cleanup_labels(sender, instance: PropagationBatch, **kwargs):
    """Delete labels for a PropagationBatch once it's hard-deleted."""
    _delete_labels_for_target(PropagationBatch, instance.pk)


@receiver(post_delete, sender=PlantMaterial, dispatch_uid="nursery.labels.material_delete_cleanup")
def material_delete_cleanup_labels(sender, instance: PlantMaterial, **kwargs):
    """Delete labels for a PlantMaterial once it's hard-deleted."""
    _delete_labels_for_target(PlantMaterial, instance.pk)


# ==============================================================================
# Webhook emitters (feature-flagged; default OFF)
# ==============================================================================

def _auto_emit_enabled() -> bool:
    """
    Feature flag (default False). Turn on by setting WEBHOOKS_ENABLE_AUTO_EMIT=True.
    """
    return bool(getattr(settings, "WEBHOOKS_ENABLE_AUTO_EMIT", False))


# ---- Event.created → webhook --------------------------------------------------

@receiver(post_save, sender=Event, dispatch_uid="nursery.webhooks.event_created")
def webhook_event_created(sender, instance: Event, created: bool, **kwargs) -> None:
    """Emit `event.created` when a new Event row is inserted."""
    if not _auto_emit_enabled():
        return
    if not created:
        return
    payload = {
        "id": instance.id,
        "event_type": instance.event_type,
        "happened_at": instance.happened_at.isoformat(),
        "batch": instance.batch_id,
        "plant": instance.plant_id,
        "quantity_delta": instance.quantity_delta,
        "notes": instance.notes or "",
    }
    # WHY: enqueue only; worker handles HTTPS/signing/retries to keep writes fast.
    enqueue_for_user(instance.user, WebhookEventType.EVENT_CREATED, {"event": payload})


# ---- Plant.status change → webhook -------------------------------------------

@receiver(pre_save, sender=Plant, dispatch_uid="nursery.webhooks.plant_capture_old_status")
def plant_capture_old_status(sender, instance: Plant, **kwargs) -> None:
    """Capture previous Plant.status for comparison in post_save."""
    # Only capture for updates
    if not instance.pk:
        instance.__old_status = None  # type: ignore[attr-defined]
        return
    try:
        old = Plant.objects.only("status").get(pk=instance.pk).status
    except Plant.DoesNotExist:
        old = None
    instance.__old_status = old  # type: ignore[attr-defined]


@receiver(post_save, sender=Plant, dispatch_uid="nursery.webhooks.plant_status_changed")
def webhook_plant_status_changed(sender, instance: Plant, created: bool, **kwargs) -> None:
    """Emit `plant.status_changed` on status change (feature-flagged)."""
    if not _auto_emit_enabled():
        return
    old: Optional[str] = getattr(instance, "__old_status", None)  # type: ignore[attr-defined]
    if old is None or old == instance.status:
        return

    payload = {
        "id": instance.id,
        "old_status": old,
        "new_status": instance.status,
        "changed_at": instance.updated_at.isoformat(),
        "batch": instance.batch_id,
        "taxon": instance.taxon_id,
    }
    enqueue_for_user(instance.user, WebhookEventType.PLANT_STATUS_CHANGED, {"plant": payload})


# ---- PropagationBatch.status change → webhook --------------------------------

@receiver(pre_save, sender=PropagationBatch, dispatch_uid="nursery.webhooks.batch_capture_old_status")
def batch_capture_old_status(sender, instance: PropagationBatch, **kwargs) -> None:
    """Capture previous PropagationBatch.status for comparison in post_save."""
    if not instance.pk:
        instance.__old_status = None  # type: ignore[attr-defined]
        return
    try:
        old = PropagationBatch.objects.only("status").get(pk=instance.pk).status
    except PropagationBatch.DoesNotExist:
        old = None
    instance.__old_status = old  # type: ignore[attr-defined]


@receiver(post_save, sender=PropagationBatch, dispatch_uid="nursery.webhooks.batch_status_changed")
def webhook_batch_status_changed(sender, instance: PropagationBatch, created: bool, **kwargs) -> None:
    """Emit `batch.status_changed` on status change (feature-flagged)."""
    if not _auto_emit_enabled():
        return
    old: Optional[str] = getattr(instance, "__old_status", None)  # type: ignore[attr-defined]
    if old is None or old == instance.status:
        return

    payload = {
        "id": instance.id,
        "old_status": old,
        "new_status": instance.status,
        "changed_at": instance.updated_at.isoformat(),
        "material": instance.material_id,
        "method": instance.method,
        "started_on": instance.started_on.isoformat(),
    }
    enqueue_for_user(instance.user, WebhookEventType.BATCH_STATUS_CHANGED, {"batch": payload})
