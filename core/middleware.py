from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

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
