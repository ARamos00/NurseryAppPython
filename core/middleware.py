"""
Core middleware for request safety and observability.

Components
----------
- `RequestSizeLimitMiddleware`:
    * Rejects large request bodies early with a pre-rendered 413 JSON response.
    * Applies to POST/PUT/PATCH only and relies on `Content-Length` when present.
    * Limit is configurable via `MAX_REQUEST_BYTES` (default 2,000,000 bytes).

- `RequestIDLogMiddleware`:
    * Reads `X-Request-ID` (or generates one) and reflects it in the response.
    * Stores the id in a contextvar for use by `core.logging.RequestIDFilter`.
    * Logs one structured line per request including latency (ms) and user id.

Security & UX
-------------
- The request-size rejection uses a DRF `Response` rendered to JSON so tests and
  clients get consistent error shapes. CSRF remains enabled upstream.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Callable, Optional

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from rest_framework.response import Response  # DRF Response so APIClient exposes .data
from rest_framework.renderers import JSONRenderer  # To render Response content for tests

# Keep the contextvar in a small logging helper module so all loggers can access it.
from .logging import request_id_var  # noqa: F401  (imported for side effects / reference)

logger = logging.getLogger("nursery.request")

# Allow simple, safe request-id tokens coming from clients
_ALLOWED_CHARS = re.compile(r"^[A-Za-z0-9._\-]{1,200}$")


def _coerce_request_id(raw: str | None) -> str:
    """
    Coerce a client-provided request id to a safe token, or generate a new one.
    """
    if raw and _ALLOWED_CHARS.match(raw):
        return raw
    # uuid4 hex (no hyphens) to keep it compact and URL/header safe
    return uuid.uuid4().hex


class RequestSizeLimitMiddleware:
    """
    Reject overly large request bodies with 413, before any parsing.

    - Uses Content-Length if present; if missing or unparsable we allow through.
    - Applies to POST/PUT/PATCH only.
    - Configured via settings.MAX_REQUEST_BYTES (default: 2_000_000).
    - Returns a DRF Response (pre-rendered) so APIClient exposes .data and .content.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.max_bytes: int = int(getattr(settings, "MAX_REQUEST_BYTES", 2_000_000))

    def __call__(self, request: HttpRequest) -> HttpResponse:
        method = request.method.upper()
        if method in {"POST", "PUT", "PATCH"} and self.max_bytes > 0:
            raw_len: Optional[str] = request.META.get("CONTENT_LENGTH")
            try:
                content_length = int(raw_len) if raw_len is not None else None
            except ValueError:
                content_length = None

            if content_length is not None and content_length > self.max_bytes:
                # Build a DRF Response and render it so tests can access r.content and r.data
                payload = {
                    "detail": f"Request entity too large. Max {self.max_bytes} bytes.",
                    "code": "request_too_large",
                    "max_bytes": self.max_bytes,
                }
                resp = Response(payload, status=413)
                resp.accepted_renderer = JSONRenderer()
                resp.accepted_media_type = "application/json"
                resp.renderer_context = {}
                resp.render()  # ensure .content is available
                return resp

        return self.get_response(request)


class RequestIDLogMiddleware:
    """
    - Reads `X-Request-ID` (if provided) or generates one.
    - Adds `request.request_id` and response header `X-Request-ID`.
    - Logs one structured line per request with latency (ms) and key attributes.
    - Stores request_id in a `contextvar` so other logs can include it.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        rid = _coerce_request_id(request.headers.get("X-Request-ID"))
        # Expose on request
        setattr(request, "request_id", rid)
        # Bind to contextvar for downstream log records
        request_id_var.set(rid)

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        # Always reflect the request id back to the client
        response.headers["X-Request-ID"] = rid

        # Best-effort user id (avoid touching DB): only when authenticated
        user = getattr(request, "user", None)
        user_id = getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None

        # Structured key=value logging without extra deps
        logger.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.path,
                "status": getattr(response, "status_code", 0),
                "user_id": user_id,
                "duration_ms": duration_ms,
            },
        )
        return response
