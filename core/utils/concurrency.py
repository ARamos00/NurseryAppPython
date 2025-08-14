from __future__ import annotations

from datetime import datetime
from typing import Optional

from rest_framework.exceptions import APIException
from rest_framework.request import Request


class PreconditionFailed(APIException):
    status_code = 412
    default_detail = "Precondition failed (If-Match does not match current resource state)."
    default_code = "precondition_failed"


def compute_etag(updated_at: Optional[datetime]) -> Optional[str]:
    """
    Weak ETag derived from updated_at seconds precision.
    Example: W/"1723591234"
    """
    if not updated_at:
        return None
    return f'W/"{int(updated_at.timestamp())}"'


def require_if_match(request: Request, updated_at: Optional[datetime]) -> None:
    """
    Enforce optimistic concurrency if the client supplies If-Match.
    If-Match header present and mismatched -> 412 Precondition Failed.
    If absent -> allow (best-effort concurrency).
    """
    header = request.headers.get("If-Match")
    if not header:
        return
    current = compute_etag(updated_at)
    if not current or header != current:
        raise PreconditionFailed()
