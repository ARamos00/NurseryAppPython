from __future__ import annotations

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
    """
    return EventSerializer(queryset, many=True, context={"request": request}).data  # type: ignore[no-any-return]


def render_events_to_csv(queryset, *, limit: Optional[int] = None) -> HttpResponse:
    """
    Render the given queryset (already owner-scoped and filtered) as a CSV download.
    Adds X-Export-* headers for observability. Does not alter CSV shape.
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
