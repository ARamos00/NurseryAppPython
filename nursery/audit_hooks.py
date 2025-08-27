from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import pre_save
from django.dispatch import receiver

from nursery.models import AuditAction, AuditLog, Plant


@receiver(pre_save, sender=Plant, dispatch_uid="audit_soft_delete_plant")
def audit_on_soft_delete_plant(sender, instance: Plant, **kwargs):
    """
    Emit a DELETE audit log when a Plant flips is_deleted: False -> True.

    Why pre_save?
    - Works regardless of *how* the archive happens (custom action or DELETE override).
    - Avoids coupling audit semantics to any single view action.

    Actor/IP/UA are unknown at signal time; tests do not rely on those fields.
    """
    if not instance.pk:
        # brand new object; cannot be transitioning from False->True yet
        return

    # Use the "all rows" manager to see the current persisted value, including archived.
    prior = Plant.objects_all.filter(pk=instance.pk).values_list("is_deleted", flat=True).first()
    if prior is False and instance.is_deleted is True:
        AuditLog.objects.create(
            user=instance.user,
            actor=None,  # no request context here; acceptable for our tests
            content_type=ContentType.objects.get_for_model(Plant),
            object_id=instance.pk,
            action=AuditAction.DELETE,
            changes={"is_deleted": [False, True]},
            request_id="",
            ip=None,
            user_agent="",
        )
