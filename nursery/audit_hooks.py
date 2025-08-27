"""
Signal-based audit hooks for model lifecycle events.

Current hook
------------
- Emit a `DELETE` audit log when a `Plant` is soft-deleted (i.e., its `is_deleted`
  flag flips from `False` to `True`). This ensures that soft-deletes are visible
  in the audit trail the same way hard deletes would be.

Why `pre_save`?
---------------
- Triggers regardless of *how* the archive happens (custom action, model method,
  admin, or a DELETE override that flips the flag).
- Keeps auditing decoupled from any particular view or serializer.

Idempotency & reliability
-------------------------
- The receiver uses a stable `dispatch_uid` so it's registered only once even if
  `AppConfig.ready()` runs multiple times under the autoreloader.
- We consult the persisted value using the "all rows" manager (see NOTE below) to
  confirm the transition is exactly `False -> True` and avoid duplicate logs.

Security & context
------------------
- The owning tenant is taken from `instance.user`.
- Request-bound context (actor, IP, user agent) is unavailable in signals, so
  those fields are recorded as empty/None. Tests do not rely on them.
"""

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

    # NOTE: Use the "all rows" manager to see the current persisted value,
    # including archived rows; the default manager might filter them out.
    prior = (
        Plant.objects_all
        .filter(pk=instance.pk)
        .values_list("is_deleted", flat=True)
        .first()
    )
    if prior is False and instance.is_deleted is True:
        # SECURITY: Scope log to the row owner; no request context when in signals.
        AuditLog.objects.create(
            user=instance.user,
            actor=None,  # no request context here; acceptable for our tests
            content_type=ContentType.objects.get_for_model(Plant),
            object_id=instance.pk,
            action=AuditAction.DELETE,
            changes={"is_deleted": [False, True]},  # minimal, explicit change set
            request_id="",
            ip=None,
            user_agent="",
        )
