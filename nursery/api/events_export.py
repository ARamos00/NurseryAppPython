from __future__ import annotations

"""
Mixin to add an `/export/` action to an Events ViewSet.

Overview
--------
- Reuses the hosting ViewSet's `get_queryset()` and `filter_queryset()` so any
  owner scoping, filters, search, and ordering already configured there apply.
- Format negotiation:
    * `?format=json` -> returns a JSON array (unpaginated).
    * `?format=csv` or any other value (default) -> returns a CSV download.
    * The action declares `renderer_classes` for DRF compatibility, but this
      implementation manually returns `HttpResponse` for CSV to control headers.
- CSV contract:
    Columns: id, happened_at (ISO), event_type, target_type, batch_id, plant_id,
    quantity_delta, notes (CR/LF collapsed to spaces).
- Throttling:
    This mixin does not set a throttle scope; rely on the hosting ViewSet's
    class-level `throttle_scope` or the project's global throttles.

Security
--------
- The hosting ViewSet **must** scope `get_queryset()` by `request.user` (e.g.,
  via `OwnedModelViewSet`) to prevent cross-tenant data leakage.
"""

import csv
from io import StringIO
from typing import Iterable

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer

from drf_spectacular.utils import extend_schema, OpenApiParameter

from nursery.serializers import EventSerializer
from nursery.renderers import PassthroughCSVRenderer


class EventsExportMixin:
    """
    Adds `/export/` (GET) to an Events ViewSet.

    Behavior:
        - Respects existing filter/search/order backends via `filter_queryset()`.
        - Emits JSON when `?format=json`; otherwise a CSV download.

    Notes:
        - CSV is streamed from an in-memory buffer; large datasets should prefer
          the canonical export API that supports explicit row caps and headers.
    """

    @extend_schema(
        tags=["Events: Export"],
        parameters=[
            OpenApiParameter(
                name="format",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Export format: csv (default) or json.",
            )
        ],
        responses={200: None},
        description="Export filtered events in CSV or JSON.",
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="export",
        # Keep DRF format override compatible while still returning HttpResponse for CSV.
        renderer_classes=[JSONRenderer, BrowsableAPIRenderer, PassthroughCSVRenderer],
    )
    def export(self, request: Request):
        """
        Export events in the requested format.

        Args:
            request: DRF Request with optional `?format=json|csv`.

        Returns:
            - JSON: `Response([...])` where each item matches `EventSerializer`.
            - CSV: `HttpResponse` with `text/csv; charset=utf-8` and attachment
              filename `events-YYYYMMDD-HHMMSS.csv`.

        PERF:
            Uses `iterator()` for CSV generation to keep memory bounded on large
            querysets.

        SECURITY:
            Relies on the hosting ViewSet's `get_queryset()` to be owner-scoped.
        """
        fmt = (request.query_params.get("format") or "csv").lower().strip()
        # Reuse the view's filters/search to mirror list results
        queryset = self.filter_queryset(self.get_queryset()).select_related("batch", "plant")

        if fmt == "json":
            # JSON: mirror API shape by reusing the canonical serializer
            data = EventSerializer(queryset, many=True, context={"request": request}).data
            return Response(data)

        # Default CSV
        headers = [
            "id",
            "happened_at",
            "event_type",
            "target_type",
            "batch_id",
            "plant_id",
            "quantity_delta",
            "notes",
        ]
        buf = StringIO()
        writer = csv.DictWriter(buf, fieldnames=headers)
        writer.writeheader()

        def rows(qs) -> Iterable[dict]:
            # PERF: iterator() avoids loading all rows at once
            for e in qs.iterator():
                yield {
                    "id": e.id,
                    "happened_at": e.happened_at.isoformat(),
                    "event_type": e.event_type,
                    "target_type": "plant" if e.plant_id else "batch",
                    "batch_id": e.batch_id or "",
                    "plant_id": e.plant_id or "",
                    "quantity_delta": e.quantity_delta if e.quantity_delta is not None else "",
                    # NOTE: collapse CR/LF to keep each record single-line
                    "notes": (e.notes or "").replace("\r", " ").replace("\n", " ").strip(),
                }

        for row in rows(queryset):
            writer.writerow(row)

        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        content = buf.getvalue()
        resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
        # Friendly, timestamped filename for downloads
        resp["Content-Disposition"] = f'attachment; filename="events-{ts}.csv"'
        return resp
