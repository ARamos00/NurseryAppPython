from django.http import JsonResponse
from django.utils.timezone import now
from django.db import connection


def health(request):
    """
    Lightweight health endpoint (no auth).
    Checks DB connectivity and returns a simple JSON status.
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
