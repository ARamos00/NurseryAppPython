from __future__ import annotations

"""
Concurrency helpers for optimistic locking via HTTP preconditions.

This module provides a small surface to:
- Compute a *weak* ETag from a model's `updated_at` timestamp (seconds precision).
- Enforce `If-Match` on modifying requests to prevent lost updates.

Design notes
-----------
- ETags are intentionally weak (e.g., W/"1723591234") so they remain cheap to compute
  and stable across serialization differences. They are suitable for optimistic
  concurrency, not byte-for-byte cache validation.
- `require_if_match()` *only* enforces the precondition when the client supplies the
  `If-Match` header. Enforcement of "header required for updates" can be done at the
  view/policy level (e.g., a setting like ENFORCE_IF_MATCH) without changing this
  module's behavior.

Security
--------
- Clients must echo back the ETag from a fresh GET in `If-Match` to modify a resource.
  A mismatch yields HTTP 412 Precondition Failed.
"""

from datetime import datetime
from typing import Optional

from rest_framework.exceptions import APIException
from rest_framework.request import Request


class PreconditionFailed(APIException):
    """HTTP 412 Precondition Failed raised on stale `If-Match` values.

    This DRF exception maps to RFC 9110 semantics where an update is rejected if the
    client's precondition doesn't match the server's current representation.

    See also:
        - RFC 9110 §13.1 "Conditional Requests"
        - RFC 9110 §8.8.3 "If-Match"
    """
    status_code = 412
    default_detail = "Precondition failed (If-Match does not match current resource state)."
    default_code = "precondition_failed"


def compute_etag(updated_at: Optional[datetime]) -> Optional[str]:
    """Return a weak ETag derived from seconds-precision `updated_at`.

    Example:
        W/"1723591234"

    Args:
        updated_at: Timestamp of the model's last update (or None).

    Returns:
        A weak ETag string or None if no timestamp is available.

    Notes:
        - We intentionally drop sub-second precision to avoid false negatives from
          trivial updates and to keep the value readable and cache-friendly.
    """
    if not updated_at:
        return None
    return f'W/"{int(updated_at.timestamp())}"'


def require_if_match(request: Request, updated_at: Optional[datetime]) -> None:
    """Enforce optimistic concurrency when a client supplies `If-Match`.

    Behavior:
        - If `If-Match` header is present and does not equal the current ETag,
          raise `PreconditionFailed` (HTTP 412).
        - If `If-Match` is absent, allow the request to proceed (best-effort).

    Args:
        request: DRF request containing headers.
        updated_at: Current server-side timestamp used to compute the ETag.

    Raises:
        PreconditionFailed: When `If-Match` is provided and mismatches the current ETag.

    Security:
        # SECURITY: If your policy requires `If-Match` on updates, enforce that
        # requirement at the view/permission layer before calling this helper.
    """
    header = request.headers.get("If-Match")
    if not header:
        return

    current = compute_etag(updated_at)
    # WHY: If no ETag can be computed (missing timestamp) or it differs from the header,
    # we treat it as a failed precondition to avoid silent overwrites.
    if not current or header != current:
        raise PreconditionFailed()
