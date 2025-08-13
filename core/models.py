from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class OwnedQuerySet(models.QuerySet):
    """
    Query helpers for user-owned rows.
    Use explicitly in views: Model.objects.for_user(request.user)
    """
    def for_user(self, user):
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(user=user)

    # Alias for readability
    def owned(self, user):
        return self.for_user(user)


class OwnedModel(models.Model):
    """
    Abstract base for per-user ownership + audit fields.
    Inherit in domain models: class Taxon(OwnedModel): ...
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Expose helpers like .for_user()
    objects = OwnedQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if self.user_id is None:
            raise ValidationError({"user": "User must be set for owned records."})

    def is_owned_by(self, user) -> bool:
        return bool(user and getattr(user, "is_authenticated", False) and self.user_id == user.id)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={getattr(self, 'id', None)} user_id={self.user_id}>"


# -----------------------------------------------------------------------------
# Idempotency persistence (Phase 1b)
# -----------------------------------------------------------------------------

class IdempotencyKey(models.Model):
    """
    Stores the first response for a given (user, key, method, path, body_hash) tuple.
    Subsequent identical requests can be safely replayed.

    This model is intentionally simple and storage-efficient. It captures:
      - status_code and content_type
      - a JSON-serializable body (Response.data preferred)
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="core_idempotency_keys",
    )
    # Client-provided key from 'Idempotency-Key' header.
    key = models.CharField(max_length=200)
    method = models.CharField(max_length=10)
    # Use TextField in case of long paths; normalize to the request.path as stored by DRF.
    path = models.TextField()
    # SHA-256 hex of the raw request body (or parsed data fallback).
    body_hash = models.CharField(max_length=64)

    status_code = models.PositiveSmallIntegerField()
    content_type = models.CharField(max_length=100, default="application/json")
    # Store DRF Response.data where possible; must be JSON-serializable.
    response_json = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "key", "method", "path", "body_hash"),
                name="unique_idempotency_request_tuple",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "created_at")),
            models.Index(fields=("created_at",)),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Idem(user={self.user_id}, key={self.key}, {self.method} {self.path})"
