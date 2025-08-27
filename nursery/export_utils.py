from __future__ import annotations

"""
Utilities for exporting Event data as JSON or CSV.

CSV
---
- Fixed header order in `CSV_HEADERS` to keep downstream parsers stable.
- Values are normalized:
    * `happened_at` uses ISO 8601.
    * `target_type` is "plant" if `plant_id` is set else "batch".
    * Missing numeric fields render as empty strings (not "null").
    * `notes` collapses CR/LF into spaces to keep rows one-line.

Limits & headers
----------------
- Row cap defaults to `settings.EXPORT_MAX_ROWS` (100k if unset).
- Response sets:
    * `Content-Disposition` with a timestamped filename.
    * `X-Export-Total`, `X-Export-Limit`, `X-Export-Truncated` for observability.

Notes
-----
- Queryset must already be owner-scoped and ordered by the caller.
- JSON export delegates to `EventSerializer` to keep shape aligned with the API.
"""

import csv
from io import StringIO
from typing import Iterable, List, Dict, Optional

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from nursery.models import Event
from nursery.serializers import EventSerializer


CSV_HEADERS = [
    "id",
    "happened_at",
    "event_type",
    "target_type",
    "batch_id",
    "plant_id",
    "quantity_delta",
    "notes",
]


def serialize_events_to_json(queryset, request) -> List[Dict]:
    """
    Return a plain list of event dicts (unpaginated) suitable for export.

    Args:
        queryset: Owner-scoped queryset of `Event` rows.
        request: DRF request (used for serializer context/auth).

    Returns:
        List[dict]: Serialized events as they appear in the API.
    """
    return EventSerializer(queryset, many=True, context={"request": request}).data  # type: ignore[no-any-return]


def render_events_to_csv(queryset, *, limit: Optional[int] = None) -> HttpResponse:
    """
    Render the given queryset (already owner-scoped and filtered) as a CSV download.
    Adds X-Export-* headers for observability. Does not alter CSV shape.

    Args:
        queryset: Owner-scoped queryset of `Event` rows.
        limit: Optional row cap (defaults to `EXPORT_MAX_ROWS`).

    Returns:
        HttpResponse: CSV attachment with headers and observability metadata.

    PERF:
        # PERF: We use `iterator()` to keep memory bounded for large exports and
        # respect `limit` inside the generator.
    """
    if limit is None:
        limit = int(getattr(settings, "EXPORT_MAX_ROWS", 100_000))

    total = queryset.count()

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_HEADERS)
    writer.writeheader()

    def rows(qs) -> Iterable[dict]:
        written = 0
        for e in qs.iterator():
            if limit and written >= limit:
                break
            yield {
                "id": e.id,
                "happened_at": e.happened_at.isoformat(),
                "event_type": e.event_type,
                "target_type": "plant" if e.plant_id else "batch",
                "batch_id": e.batch_id or "",
                "plant_id": e.plant_id or "",
                "quantity_delta": e.quantity_delta if e.quantity_delta is not None else "",
                "notes": (e.notes or "").replace("\r", " ").replace("\n", " ").strip(),
            }
            written += 1

    for row in rows(queryset):
        writer.writerow(row)

    ts = timezone.now().strftime("%Y%m%d-%H%M%S")
    content = buf.getvalue()
    resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="events-{ts}.csv"'
    resp["X-Export-Total"] = str(total)
    resp["X-Export-Limit"] = str(limit)
    resp["X-Export-Truncated"] = "true" if (limit and total > limit) else "false"
    return resp
