from __future__ import annotations

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
    Adds /api/events/export/?format=csv|json
    Re-uses the viewset filter backends through filter_queryset().
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
        renderer_classes=[JSONRenderer, BrowsableAPIRenderer, PassthroughCSVRenderer],
    )
    def export(self, request: Request):
        fmt = (request.query_params.get("format") or "csv").lower().strip()
        queryset = self.filter_queryset(self.get_queryset()).select_related("batch", "plant")

        if fmt == "json":
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
            for e in qs.iterator():
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

        for row in rows(queryset):
            writer.writerow(row)

        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        content = buf.getvalue()
        resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="events-{ts}.csv"'
        return resp
