"""
Mixins and helpers shared by API viewsets.

Contents
--------
- ETagConcurrencyMixin
    Adds optimistic concurrency to `ModelViewSet` endpoints using **weak ETags**.
    * GET (retrieve): attaches an `ETag` header derived from a stable fingerprint
      of the row's **persisted** fields (incl. FK `*_id` values).
    * PATCH/PUT/DELETE: validates `If-Match` against the current ETag.
      - If `settings.ENFORCE_IF_MATCH` is True and the header is missing, respond
        `428 Precondition Required` with a hint.
      - If the provided tag doesn't match, respond `412 Precondition Failed`.

    WHY:
      The fingerprint changes whenever any stored field changes (no serializer/
      view involvement required). List endpoints intentionally **do not** add
      ETags to avoid confusing cache semantics.

- Audit helpers
    `_snapshot_model`, `_diff`, `_request_meta`, `_audit_create` are small helpers
    used by owner-scoped viewsets to write `AuditLog` rows without creating import
    cycles. `_audit_create` intentionally does **not** set `content_type`; that is
    done in view code where `ContentType` is available without circular imports.

Security & Safety
-----------------
- `If-Match` enforcement is feature-flagged via `ENFORCE_IF_MATCH`; when False, the
  mixin still performs `412` checks if a client *does* send `If-Match`, but won't
  require it.
- ETag digests include only persisted concrete field values (no secrets rendered).
"""

from __future__ import annotations

import hashlib
import json  # NOTE: kept for parity with original imports (not used here)
import uuid
from typing import Optional

from django.conf import settings
from django.http import Http404
from django.utils.timezone import is_naive, make_aware  # NOTE: imported elsewhere; retained here
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from nursery.models import AuditLog, AuditAction


class ETagConcurrencyMixin(ModelViewSet):
    """
    Adds optimistic concurrency to ModelViewSet endpoints using weak ETags.

    - On GET retrieve: sets `ETag` header computed from a hash of all concrete
      persisted fields (incl. FK ids). This changes whenever any stored field
      changes, regardless of how the update occurred (save(), update(), raw SQL).
    - On PATCH/PUT/DELETE: if client provides `If-Match`, it must match current ETag;
      otherwise 412 Precondition Failed. If strict mode is enabled, missing If-Match
      yields 428 Precondition Required.

    Assumptions:
    - Targets are standard Django models; we hash concrete, non-m2m, non-auto-created
      fields using their stored values (FKs via *_id).
    - We intentionally do NOT add ETags on list responses.
    """

    # ---------- ETag helpers ----------

    def _compute_etag(self, obj) -> str:
        """
        Build a weak ETag from a stable fingerprint of the row's persisted state.

        The fingerprint includes:
          - app_label, model_name, pk
          - all concrete, non-m2m, non-auto-created field values
            (for FKs we use the column value via `attname`, e.g. `<field>_id`)

        Any persisted change alters the fingerprint -> new ETag.

        # WHY:
        # Using `attname` ensures FK ids are hashed even if the relation isn't
        # loaded; hashing strings keeps the digest stable across types.
        """
        meta = obj._meta
        model_label = f"{meta.app_label}.{meta.model_name}"
        pk = getattr(obj, "pk", None)

        # Collect (name, value) pairs deterministically by field name order.
        # Use attname to get the stored column value (e.g. fk_id) for FKs.
        pairs: list[tuple[str, str]] = []
        for f in sorted(
            (f for f in meta.get_fields()
             if getattr(f, "concrete", False) and not f.many_to_many and not f.auto_created),
            key=lambda x: x.name,
        ):
            name = getattr(f, "attname", f.name)
            try:
                val = getattr(obj, name)
            except Exception:
                val = None
            pairs.append((name, "" if val is None else str(val)))

        # Hash the fingerprint
        m = hashlib.sha256()
        m.update(model_label.encode("utf-8"))
        m.update(f":{pk}:".encode("utf-8"))
        for name, sval in pairs:
            m.update(name.encode("utf-8"))
            m.update(b"=")
            m.update(sval.encode("utf-8"))
            m.update(b";")

        digest = m.hexdigest()
        return f'W/"{digest}"'

    def _parse_if_match(self, header_val: Optional[str]) -> set[str]:
        """
        Parse If-Match header values (possibly comma-separated, weak/strong).
        Returns a set of normalized tags (we keep tokens as supplied).

        # NOTE:
        # We don't normalize weak/strong (W/ vs strong) beyond string equality
        # because the mixin always emits weak tags and the client echoes them.
        """
        if not header_val:
            return set()
        parts = [p.strip() for p in header_val.split(",")]
        return {p for p in parts if p}

    def _check_if_match_or_error(self, request, obj) -> Optional[Response]:
        """
        Validate If-Match precondition for PATCH/PUT/DELETE.
        Returns a Response on error, or None when preconditions pass.

        Behavior:
            - If client omits If-Match and strict mode is on -> 428.
            - If client provides `*` -> always pass.
            - If provided tag doesn't match current ETag -> 412.
        """
        client_tags = self._parse_if_match(request.headers.get("If-Match"))
        server_tag = self._compute_etag(obj)
        enforce = bool(getattr(settings, "ENFORCE_IF_MATCH", False))

        if not client_tags:
            if enforce:
                return Response(
                    {
                        "detail": "Precondition Required",
                        "code": "if_match_required",
                        "hint": "Send If-Match header with the current ETag.",
                        "expected_etag": server_tag,
                    },
                    status=status.HTTP_428_PRECONDITION_REQUIRED,
                )
            return None

        # If-Match: * means match any current representation
        if "*" in client_tags:
            return None

        if server_tag not in client_tags:
            return Response(
                {
                    "detail": "Precondition Failed",
                    "code": "stale_resource",
                    "expected_etag": server_tag,
                },
                status=status.HTTP_412_PRECONDITION_FAILED,
            )
        return None

    def _set_response_etag(self, response: Response, obj) -> None:
        """Attach an ETag to the response; never fail the request on errors."""
        try:
            response["ETag"] = self._compute_etag(obj)
        except Exception:
            # Never break the response just for ETag
            pass

    # ---------- ViewSet overrides ----------

    def retrieve(self, request, *args, **kwargs) -> Response:
        """
        Add an ETag to successful retrieve responses.

        # NOTE:
        # We call `get_object()` again to compute the tag; if it 404s in between,
        # we simply return the original response without an ETag.
        """
        response = super().retrieve(request, *args, **kwargs)
        try:
            obj = self.get_object()
        except Http404:
            return response
        self._set_response_etag(response, obj)
        return response

    def update(self, request, *args, **kwargs) -> Response:
        """
        Enforce If-Match (when applicable), perform update, and return new ETag.

        # WHY:
        # Refreshing from DB post-save ensures the tag reflects DB state even if
        # database-side defaults or triggers touched fields.
        """
        obj = self.get_object()
        error = self._check_if_match_or_error(request, obj)
        if error is not None:
            return error
        response = super().update(request, *args, **kwargs)
        try:
            obj.refresh_from_db()
        except Exception:
            pass
        self._set_response_etag(response, obj)
        return response

    def partial_update(self, request, *args, **kwargs) -> Response:
        """Same as `update()` but for PATCH."""
        obj = self.get_object()
        error = self._check_if_match_or_error(request, obj)
        if error is not None:
            return error
        response = super().partial_update(request, *args, **kwargs)
        try:
            obj.refresh_from_db()
        except Exception:
            pass
        self._set_response_etag(response, obj)
        return response

    def destroy(self, request, *args, **kwargs) -> Response:
        """Enforce If-Match (when applicable) before deletion."""
        obj = self.get_object()
        error = self._check_if_match_or_error(request, obj)
        if error is not None:
            return error
        return super().destroy(request, *args, **kwargs)


# --------- Audit helpers (used by OwnedModelViewSet) ---------


def _snapshot_model(instance) -> dict:
    """
    Snapshot concrete field values (FKs via attname).

    Values are JSON-serializable:
        - datetimes -> isoformat strings
        - None preserved as None

    # PERF:
    # Avoids following relations and only touches concrete fields for a compact
    # audit payload.
    """
    meta = instance._meta
    snap = {}
    for f in meta.concrete_fields:
        if f.auto_created:
            continue
        name = getattr(f, "attname", f.name)
        try:
            val = getattr(instance, name)
        except Exception:
            val = None
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        snap[name] = val
    return snap


def _diff(before: Optional[dict], after: Optional[dict]) -> dict:
    """
    Compute a shallow diff mapping field -> [old, new].

    Special cases:
        - create: {"_after": {<snapshot>}}
        - delete: {"_before": {<snapshot>}}
    """
    if before is None and after is not None:
        return {"_after": after}
    if after is None and before is not None:
        return {"_before": before}
    before = before or {}
    after = after or {}
    changed = {}
    keys = set(before) | set(after)
    for k in sorted(keys):
        if before.get(k) != after.get(k):
            changed[k] = [before.get(k), after.get(k)]
    return changed


def _request_meta(request):
    """
    Extract basic request metadata for audit logging.

    Returns:
        (request_id, ip, user_agent)
    """
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")
    return rid, ip, ua


def _audit_create(request, instance):
    """
    Create a minimal `AuditLog` row for a new instance.

    NOTE:
        We avoid importing `ContentType` here to prevent cycles; the correct
        `content_type` is assigned in the view layer where it's readily available.

    # SECURITY:
    # The owning tenant is determined from the instance (`instance.user`) and
    # falls back to `request.user` only if the instance doesn't have `user`.
    """
    owner = getattr(instance, "user", None) or request.user
    rid, ip, ua = _request_meta(request)
    return AuditLog.objects.create(
        user=owner,
        actor=request.user if request.user.is_authenticated else None,
        content_type=instance._meta.app_config.get_model(instance._meta.model_name)._meta.app_config.get_model(instance._meta.model_name)._meta.model._meta.model._meta.model._meta if False else None,  # placeholder guarded (not used)
        # Correct content_type fetched via ContentType in viewset to avoid import here.
        # We'll set it in view since we know the instance there.
        action=AuditAction.CREATE,
        changes=_diff(None, _snapshot_model(instance)),
        request_id=rid,
        ip=ip,
        user_agent=ua,
    )
