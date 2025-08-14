from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Plant, PlantStatus, PropagationBatch, PlantMaterial, Label, LabelToken


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
    ct = ContentType.objects.get_for_model(model_cls)
    Label.objects.filter(content_type=ct, object_id=obj_id).delete()


@receiver(pre_save, sender=Plant)
def plant_status_revoke_labels(sender, instance: Plant, **kwargs):
    """
    When a Plant transitions to a terminal status (SOLD/DEAD/DISCARDED),
    revoke any active label tokens so public pages stop resolving.
    """
    if not instance.pk:
        return
    try:
        prior = Plant.objects.get(pk=instance.pk)
    except Plant.DoesNotExist:
        return
    terminal = {PlantStatus.SOLD, PlantStatus.DEAD, PlantStatus.DISCARDED}
    if prior.status in terminal and instance.status in terminal:
        # already terminal -> terminal; nothing to do
        return
    if instance.status in terminal:
        ct = ContentType.objects.get_for_model(Plant)
        for label in Label.objects.filter(content_type=ct, object_id=instance.pk):
            _revoke_active_token(label)


@receiver(post_delete, sender=Plant)
def plant_delete_cleanup_labels(sender, instance: Plant, **kwargs):
    _delete_labels_for_target(Plant, instance.pk)


@receiver(post_delete, sender=PropagationBatch)
def batch_delete_cleanup_labels(sender, instance: PropagationBatch, **kwargs):
    _delete_labels_for_target(PropagationBatch, instance.pk)


@receiver(post_delete, sender=PlantMaterial)
def material_delete_cleanup_labels(sender, instance: PlantMaterial, **kwargs):
    _delete_labels_for_target(PlantMaterial, instance.pk)
