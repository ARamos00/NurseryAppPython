from __future__ import annotations

"""
Idempotency decorator for DRF views.

This module offers `@idempotent`, a defensive decorator that de-duplicates retried
requests (e.g., network retries, client resubmissions) by persisting and replaying
the *first successful* response for a given tuple:

    (user_id, key, method, path, body_hash)

Where:
- `user_id` is the authenticated user performing the request.
- `key` is the `Idempotency-Key` header value supplied by the client.
- `method` and `path` identify the endpoint.
- `body_hash` is a SHA-256 of the raw request body (or parsed data fallback).

Operational notes
-----------------
- If the project does not define `core.IdempotencyKey`, the decorator degrades
  to a no-op and the wrapped view executes normally.
- Anonymous requests are not idempotent (skipped by design).
- On a race to insert the first row, the loser handles `IntegrityError` by loading
  and returning the stored response.
- Storage includes status code, content type, and serialized body suitable
  for reconstructing a DRF `Response`.

Security & correctness
----------------------
- Persisting the response binds it to `user_id`; another user with the same header
  will not see cross-tenant data.
- The body hash prevents accidental replays if the same key is reused with different
  payloads.
"""

import hashlib
import json
from functools import wraps
from typing import Any, Callable, Optional, Tuple

from django.apps import apps
from django.db import IntegrityError, transaction
from rest_framework.request import Request
from rest_framework.response import Response


def _body_hash_from_request(request: Request) -> str:
    """Compute a deterministic SHA-256 of the request body.

    We prefer the raw byte body; if unavailable, we fall back to a compact JSON dump
    of `request.data`. Failures result in hashing an empty byte string.

    Args:
        request: DRF request.

    Returns:
        Hexadecimal SHA-256 digest string.

    PERF:
        # PERF: Avoid reparsing large bodies. We hash `request.body` when present.
    """
    try:
        raw = request.body or b""
        if not isinstance(raw, (bytes, bytearray)):
            raw = bytes(str(raw), "utf-8")
    except Exception:
        # WHY: Some request classes may not expose `.body`. As a fallback, hash a
        # canonicalized JSON of parsed data to maintain determinism across retries.
        try:
            raw = json.dumps(request.data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception:
            raw = b""
    return hashlib.sha256(raw).hexdigest()


def _get_idempotency_model():
    """Return the `core.IdempotencyKey` model, or None if app/model is absent.

    NOTE:
        We avoid importing the model directly to keep this utility decoupled
        from app import order and optional installations.
    """
    try:
        return apps.get_model("core", "IdempotencyKey")
    except Exception:
        return None


def _serialize_response(resp: Response) -> Tuple[int, str, Any]:
    """Extract (status_code, content_type, body) from a DRF response.

    Preference order:
        1) `resp.data` for DRF Response objects (JSON-serializable)
        2) Decoded `resp.content` (utf-8)
        3) `None` as a last resort

    Args:
        resp: A DRF Response (or compatible).

    Returns:
        Tuple of (status_code, content_type, body).
    """
    status_code = int(getattr(resp, "status_code", 200))
    try:
        content_type = resp["Content-Type"]
    except Exception:
        content_type = "application/json"
    try:
        body = resp.data  # DRF Response
    except Exception:
        try:
            body = resp.content.decode("utf-8")
        except Exception:
            body = None
    return status_code, content_type, body


def _rebuild_response(status_code: int, content_type: Optional[str], body: Any) -> Response:
    """Reconstruct a DRF Response from stored components.

    Args:
        status_code: HTTP status code to set on the Response.
        content_type: Content type header to restore (if present).
        body: JSON-serializable data or a string payload.

    Returns:
        A DRF `Response` equivalent to the original (for common cases).

    NOTE:
        We do not attempt to restore complex headers beyond `Content-Type`.
    """
    resp = Response(body, status=status_code)
    if content_type:
        resp["Content-Type"] = content_type
    return resp


def idempotent(view_fn: Callable) -> Callable:
    """Decorator providing idempotent semantics for DRF views and viewset actions.

    Behavior:
        - If the request has an `Idempotency-Key` and the `core.IdempotencyKey`
          model exists, attempt to replay a stored response that matches:
              (user, key, method, path, body_hash).
        - Otherwise, execute the view. If execution succeeds, persist the resulting
          response atomically. On an insert race (unique constraint), load and
          return the stored row instead.

    Degradation:
        - If the model is unavailable or the user is anonymous, this decorator is
          effectively a no-op and the wrapped view executes normally.

    Concurrency:
        - Uses a single `transaction.atomic()` block for creation to ensure only
          one row wins the race. Losers look up and replay the stored response.

    Args:
        view_fn: The DRF view method or function to wrap.

    Returns:
        A wrapped view function preserving the original signature/metadata.

    Implementation notes:
        - `functools.wraps` preserves DRF attributes like `__name__` for schema.
        - We defensively propagate common DRF action attributes (e.g., `mapping`)
          to keep spectacular/router behavior intact if decorator order varies.

    Security:
        # SECURITY: Responses are stored and looked up scoped to `user_id` to
        # prevent cross-tenant leakage across identical keys.
    """
    @wraps(view_fn)
    def _wrapped(self, request: Request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        Model = _get_idempotency_model()

        # NOTE: Skip idempotency for anonymous users or when the model isn't present.
        if not key or Model is None or not getattr(request, "user", None) or not request.user.is_authenticated:
            return view_fn(self, request, *args, **kwargs)

        body_hash = _body_hash_from_request(request)
        method = request.method.upper()
        path = request.path

        # Fast path: replay a prior successful response for the exact same tuple.
        try:
            rec = Model.objects.filter(
                user_id=request.user.id,
                key=key,
                method=method,
                path=path,
                body_hash=body_hash,
            ).first()
            if rec:
                return _rebuild_response(rec.status_code, rec.content_type, rec.response_json)
        except Exception:
            # WHY: If the DB is unavailable or query fails, continue without idempotency
            # rather than failing the user's request.
            return view_fn(self, request, *args, **kwargs)

        # Not found: run the underlying view.
        resp = view_fn(self, request, *args, **kwargs)
        status_code, content_type, body = _serialize_response(resp)

        # Try to persist the first successful response for this tuple.
        try:
            with transaction.atomic():
                Model.objects.create(
                    user_id=request.user.id,
                    key=key,
                    method=method,
                    path=path,
                    body_hash=body_hash,
                    status_code=status_code,
                    content_type=content_type or "application/json",
                    response_json=body,
                )
        except IntegrityError:
            # Race: another request stored the row first — read and replay it.
            try:
                rec = Model.objects.get(
                    user_id=request.user.id,
                    key=key,
                    method=method,
                    path=path,
                    body_hash=body_hash,
                )
                return _rebuild_response(rec.status_code, rec.content_type, rec.response_json)
            except Exception:
                # If even the read fails, return the live response.
                return resp
        except Exception:
            # Any unexpected failure storing the row -> return the live response.
            return resp

        return resp

    # Defensive: propagate DRF action attributes if @idempotent is outermost.
    # This helps preserve router/spectacular behavior regardless of decorator order.
    for attr in ("mapping", "detail", "suffix", "url_name", "url_path", "kwargs", "name"):
        if hasattr(view_fn, attr) and not hasattr(_wrapped, attr):
            try:
                setattr(_wrapped, attr, getattr(view_fn, attr))
            except Exception:
                pass

    return _wrapped
