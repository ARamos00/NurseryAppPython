from __future__ import annotations

"""
Core data models shared across the project.

This module provides:
- `OwnedQuerySet` and `OwnedModel`: a consistent per-user ownership pattern
  with convenience filtering and audit fields.
- `IdempotencyKey`: persistence for first responses keyed by
  (user, key, method, path, body_hash) to enable request replay semantics.

Security & tenancy
------------------
- All domain models should inherit from `OwnedModel` to enforce per-user ownership.
- Views must scope querysets via `.for_user(request.user)` (or use `IsOwner` at
  the object level) to prevent cross-tenant data leakage.

Concurrency & idempotency
-------------------------
- `IdempotencyKey` stores metadata required to reconstruct a DRF `Response` for
  repeated identical requests bearing the same `Idempotency-Key` header.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class OwnedQuerySet(models.QuerySet):
    """
    Query helpers for user-owned rows.

    Use explicitly in views to avoid accidental data leakage:
        Model.objects.for_user(request.user)

    Notes:
        - Anonymous or unauthenticated users receive `none()` (no rows).
    """

    def for_user(self, user):
        """Return rows owned by `user` or an empty queryset when unauthenticated."""
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(user=user)

    # Alias for readability in call sites.
    def owned(self, user):
        """Alias for `for_user(user)` to improve intent clarity at call sites."""
        return self.for_user(user)


class OwnedModel(models.Model):
    """
    Abstract base for per-user ownership + audit fields.

    Inherit in domain models, e.g.:
        class Taxon(OwnedModel): ...

    Fields:
        user: FK to the owning user (CASCADE on delete).
        created_at / updated_at: standard audit timestamps.

    Manager:
        objects: `OwnedQuerySet` with `.for_user()` and `.owned()` helpers.

    Invariants:
        - `user` must be set (see `clean()`).
        - Default ordering is newest-first by `created_at`.

    Security:
        # SECURITY: Pair this with query scoping in views and object-level checks
        # (`core.permissions.IsOwner`) for robust tenant isolation.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        # NOTE: related_name pattern keeps reverse relations distinct across apps/classes.
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
        """Validate invariants for owned records (must have an owner)."""
        super().clean()
        if self.user_id is None:
            raise ValidationError({"user": "User must be set for owned records."})

    def is_owned_by(self, user) -> bool:
        """Return True if the instance is owned by the given authenticated `user`."""
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and self.user_id == user.id
        )

    def __repr__(self) -> str:
        """Debug-friendly representation including id and user_id."""
        return f"<{self.__class__.__name__} id={getattr(self, 'id', None)} user_id={self.user_id}>"


# -----------------------------------------------------------------------------
# Idempotency persistence (Phase 1b)
# -----------------------------------------------------------------------------

class IdempotencyKey(models.Model):
    """
    Stores the first response for a given (user, key, method, path, body_hash) tuple.

    Purpose:
        Subsequent identical requests can be safely replayed without re-executing
        the underlying action (e.g., POST that created a resource).

    Captured fields:
        - status_code and content_type
        - JSON-serializable body (prefer `Response.data` from DRF)

    Uniqueness:
        The `(user, key, method, path, body_hash)` constraint ensures that replays
        only occur for an exact match of identity and payload.

    Security:
        # SECURITY: Scoping by `user` prevents cross-tenant data exposure even if
        # clients reuse idempotency keys across accounts.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="core_idempotency_keys",
    )
    # Client-provided key from 'Idempotency-Key' header.
    key = models.CharField(max_length=200)
    method = models.CharField(max_length=10)
    # Use TextField in case of long paths; normalize to `request.path`.
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
        """Human-readable summary for admin/debugging."""
        return f"Idem(user={self.user_id}, key={self.key}, {self.method} {self.path})"
