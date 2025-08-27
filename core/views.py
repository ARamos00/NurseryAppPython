"""Core utility views (unauthenticated).

Currently exposes:
- `health`: lightweight readiness endpoint that checks DB connectivity and
  returns a minimal JSON payload. Intended for load balancers/k8s probes.

Security
--------
- Public by design; payload contains no sensitive data and no per-request state.
"""

from django.http import JsonResponse
from django.utils.timezone import now
from django.db import connection


def health(request):
    """
    Lightweight health endpoint (no auth).
    Checks DB connectivity and returns a simple JSON status.

    Returns:
        200 JSON when DB is reachable; 503 JSON when a DB error is raised.

    NOTE:
        This endpoint avoids caching and complex dependencies to remain dependable
        for container orchestration health checks.
    """
    status = 200
    payload = {
        "app": "nursery-tracker",
        "time": now().isoformat(),
        "db": "ok",
    }
    try:
        connection.ensure_connection()
    except Exception as exc:  # pragma: no cover (covered by tests via mocking)
        payload["db"] = "down"
        payload["error"] = str(exc)
        status = 503
    return JsonResponse(payload, status=status)
