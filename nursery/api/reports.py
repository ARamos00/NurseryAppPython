from __future__ import annotations

import csv
from io import StringIO
from typing import Any, Dict, Iterable, List

from django.db.models import Count, Sum, QuerySet
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import make_aware, is_naive
from rest_framework import permissions, status
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema

from nursery.models import Plant, Event
from nursery.renderers import PassthroughCSVRenderer


def _csv_payload(headers: List[str], rows: Iterable[Dict[str, Any]]) -> str:
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # sanitize newlines
        safe = {k: ("" if v is None else str(v).replace("\r", " ").replace("\n", " ").strip()) for k, v in row.items()}
        writer.writerow(safe)
    return buf.getvalue()


def _fmt_param(request: Request) -> str:
    return (request.query_params.get("format") or "json").lower().strip()


def _parse_date_param(s: str | None):
    if not s:
        return None
    return parse_date(s)


def _parse_dt_param(s: str | None):
    if not s:
        return None
    dt = parse_datetime(s)
    if dt and is_naive(dt):
        dt = make_aware(dt)
    return dt


class BaseReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "reports-read"
    # Enable csv via DRF's format override (?format=csv)
    renderer_classes = (JSONRenderer, BrowsableAPIRenderer, PassthroughCSVRenderer)

    # owner-scoped helpers
    def _plants(self, request: Request) -> QuerySet[Plant]:
        return Plant.objects.for_user(request.user).select_related("taxon")

    def _events(self, request: Request) -> QuerySet[Event]:
        return Event.objects.for_user(request.user)


# ---------------------------------------------------------------------------
# Inventory Report
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Reports"],
    parameters=[
        OpenApiParameter(name="format", type=OpenApiTypes.STR, required=False, description="json (default) or csv"),
        OpenApiParameter(name="taxon", type=OpenApiTypes.INT, required=False, description="Filter by taxon id"),
        OpenApiParameter(name="status", type=OpenApiTypes.STR, required=False, description="Filter by plant status"),
        OpenApiParameter(name="acquired_from", type=OpenApiTypes.DATE, required=False),
        OpenApiParameter(name="acquired_to", type=OpenApiTypes.DATE, required=False),
    ],
    responses={200: OpenApiResponse(description="Inventory report")},
    description="Inventory summary grouped by Taxon and Plant status, with totals.",
)
class InventoryReportView(BaseReportView):
    def get(self, request: Request) -> Response:
        fmt = _fmt_param(request)
        qs = self._plants(request)

        # filters
        taxon_id = request.query_params.get("taxon")
        status_f = (request.query_params.get("status") or "").strip()
        d_from = _parse_date_param(request.query_params.get("acquired_from"))
        d_to = _parse_date_param(request.query_params.get("acquired_to"))

        if taxon_id:
            try:
                qs = qs.filter(taxon_id=int(taxon_id))
            except ValueError:
                return Response({"taxon": ["Invalid id."]}, status=status.HTTP_400_BAD_REQUEST)
        if status_f:
            qs = qs.filter(status=status_f)
        if d_from:
            qs = qs.filter(acquired_on__gte=d_from)
        if d_to:
            qs = qs.filter(acquired_on__lte=d_to)

        grouped = (
            qs.values("taxon_id", "taxon__scientific_name", "taxon__cultivar", "status")
            .annotate(plants_count=Count("id"), quantity_sum=Sum("quantity"))
            .order_by("taxon__scientific_name", "status")
        )

        # totals
        totals = qs.aggregate(plants=Count("id"), quantity=Sum("quantity"))
        totals = {"plants": totals["plants"] or 0, "quantity": totals["quantity"] or 0}

        rows = [
            {
                "taxon_id": r["taxon_id"],
                "scientific_name": r["taxon__scientific_name"],
                "cultivar": r["taxon__cultivar"] or "",
                "status": r["status"],
                "plants": r["plants_count"],
                "quantity": r["quantity_sum"] or 0,
            }
            for r in grouped
        ]

        if fmt == "csv":
            headers = ["taxon_id", "scientific_name", "cultivar", "status", "plants", "quantity"]
            csv_text = _csv_payload(headers, rows)
            resp = Response(csv_text)
            resp["Content-Type"] = "text/csv; charset=utf-8"
            resp["Content-Disposition"] = 'attachment; filename="inventory.csv"'
            return resp

        return Response({"rows": rows, "totals": totals})


# ---------------------------------------------------------------------------
# Production Report
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Reports"],
    parameters=[
        OpenApiParameter(name="format", type=OpenApiTypes.STR, required=False, description="json (default) or csv"),
        OpenApiParameter(name="date_from", type=OpenApiTypes.DATETIME, required=False, description="Filter start"),
        OpenApiParameter(name="date_to", type=OpenApiTypes.DATETIME, required=False, description="Filter end"),
        OpenApiParameter(
            name="group_by",
            type=OpenApiTypes.STR,
            required=False,
            description="Optional timeseries bucket: day | week | month",
        ),
    ],
    responses={200: OpenApiResponse(description="Production (events) report")},
    description="Production summary aggregated by event type, with optional time-bucketed series.",
)
class ProductionReportView(BaseReportView):
    def get(self, request: Request) -> Response:
        fmt = _fmt_param(request)
        qs = self._events(request)

        d_from = _parse_dt_param(request.query_params.get("date_from"))
        d_to = _parse_dt_param(request.query_params.get("date_to"))
        if d_from:
            qs = qs.filter(happened_at__gte=d_from)
        if d_to:
            qs = qs.filter(happened_at__lte=d_to)

        # overall by event_type
        by_type = qs.values("event_type").annotate(events=Count("id"), qty=Sum("quantity_delta")).order_by("event_type")
        by_type_rows = [{"event_type": r["event_type"], "events": r["events"], "quantity": r["qty"] or 0} for r in by_type]

        # optional timeseries
        group_by = (request.query_params.get("group_by") or "").lower().strip()
        timeseries_rows: List[Dict[str, Any]] = []
        bucket_header = None
        if group_by in {"day", "week", "month"}:
            if group_by == "day":
                trunc = TruncDate("happened_at")
                bucket_header = "date"
            elif group_by == "week":
                trunc = TruncWeek("happened_at")
                bucket_header = "week"
            else:
                trunc = TruncMonth("happened_at")
                bucket_header = "month"

            ts = (
                qs.annotate(bucket=trunc)
                .values("bucket", "event_type")
                .annotate(events=Count("id"), qty=Sum("quantity_delta"))
                .order_by("bucket", "event_type")
            )
            for r in ts:
                timeseries_rows.append(
                    {
                        bucket_header: r["bucket"].date().isoformat() if hasattr(r["bucket"], "date") else str(r["bucket"]),
                        "event_type": r["event_type"],
                        "events": r["events"],
                        "quantity": r["qty"] or 0,
                    }
                )

        if fmt == "csv":
            if group_by in {"day", "week", "month"}:
                headers = [bucket_header or "bucket", "event_type", "events", "quantity"]
                csv_text = _csv_payload(headers, timeseries_rows)
                filename = f"production_timeseries_{group_by or 'bucket'}.csv"
            else:
                headers = ["event_type", "events", "quantity"]
                csv_text = _csv_payload(headers, by_type_rows)
                filename = "production.csv"
            resp = Response(csv_text)
            resp["Content-Type"] = "text/csv; charset=utf-8"
            resp["Content-Disposition"] = f'attachment; filename="{filename}"'
            return resp

        payload: Dict[str, Any] = {"summary_by_type": by_type_rows}
        if timeseries_rows:
            payload["timeseries"] = timeseries_rows
        return Response(payload)
