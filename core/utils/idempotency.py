from __future__ import annotations

import hashlib
import json
from functools import wraps
from typing import Any, Callable, Optional, Tuple

from django.apps import apps
from django.db import IntegrityError, transaction
from rest_framework.request import Request
from rest_framework.response import Response


def _body_hash_from_request(request: Request) -> str:
    """
    Compute a deterministic hash of the raw request body (bytes).
    Falls back to hashing the parsed data if raw body is unavailable.
    """
    try:
        raw = request.body or b""
        if not isinstance(raw, (bytes, bytearray)):
            raw = bytes(str(raw), "utf-8")
    except Exception:
        try:
            raw = json.dumps(request.data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception:
            raw = b""
    return hashlib.sha256(raw).hexdigest()


def _get_idempotency_model():
    """Return the IdempotencyKey model or None if not installed."""
    try:
        return apps.get_model("core", "IdempotencyKey")
    except Exception:
        return None


def _serialize_response(resp: Response) -> Tuple[int, str, Any]:
    """Prefer DRF Response.data; fallback to string content."""
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
    resp = Response(body, status=status_code)
    if content_type:
        resp["Content-Type"] = content_type
    return resp


def idempotent(view_fn: Callable) -> Callable:
    """
    Decorator for DRF View/ViewSet methods.

    Behavior:
    - If request has 'Idempotency-Key' header and the core.IdempotencyKey model exists,
      attempts to replay the first stored response matching (user, key, method, path, body_hash).
    - If not stored, runs the view, stores the response atomically, then returns it.
      On a race (IntegrityError), fetch the stored row and return it.

    Degrades to a no-op if the model is unavailable or the user is unauthenticated.

    Implementation notes:
    - Uses functools.wraps to preserve metadata.
    - Also copies DRF action attributes if present (defensive). In general, prefer
      applying @idempotent *under* @action so the action wrapper is outermost.
    """
    @wraps(view_fn)
    def _wrapped(self, request: Request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        Model = _get_idempotency_model()
        if not key or Model is None or not getattr(request, "user", None) or not request.user.is_authenticated:
            return view_fn(self, request, *args, **kwargs)

        body_hash = _body_hash_from_request(request)
        method = request.method.upper()
        path = request.path

        # Fast path: replay if found
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
            # Any DB issue -> proceed without idempotency
            return view_fn(self, request, *args, **kwargs)

        # Not found -> run view
        resp = view_fn(self, request, *args, **kwargs)
        status_code, content_type, body = _serialize_response(resp)

        # Try to store
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
            # Race: read existing and replay
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
                return resp
        except Exception:
            return resp

        return resp

    # Defensive: propagate DRF action attributes if @idempotent is the outermost decorator.
    for attr in ("mapping", "detail", "suffix", "url_name", "url_path", "kwargs", "name"):
        if hasattr(view_fn, attr) and not hasattr(_wrapped, attr):
            try:
                setattr(_wrapped, attr, getattr(view_fn, attr))
            except Exception:
                pass

    return _wrapped
