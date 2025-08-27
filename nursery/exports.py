from __future__ import annotations

"""
Events export endpoint (CSV/JSON) with graceful format negotiation.

Highlights
----------
- Auth: `IsAuthenticated`; queryset is owner-scoped (filter by `request.user`).
- Formats:
    * `?format=json` -> JSON list (unpaginated), with X-Export-* headers.
    * `?format=csv` or anything else (default) -> CSV file download.
    * `Accept: text/csv` also negotiates CSV via renderer.
- Negotiation quirk:
    If a client supplies an unknown `?format=xyz`, DRF would 404 by default.
    `get_renderers()` injects a one-off renderer advertising `format=xyz` so
    negotiation succeeds, then the view still returns CSV (tests rely on this).
- Throttle: `events-export` scope.
"""

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from rest_framework.settings import api_settings
from drf_spectacular.utils import extend_schema, OpenApiParameter

from nursery.models import Event
from nursery.export_utils import serialize_events_to_json, render_events_to_csv
from nursery.renderers import PassthroughCSVRenderer


class EventsExportView(APIView):
    """
    Canonical events export endpoint.

    - Auth: IsAuthenticated; owner-scoped queryset
    - Formats:
        * ?format=json  -> JSON list (unpaginated)
        * ?format=csv   -> CSV download
        * Accept: text/csv -> CSV (even without ?format)
        * Any unknown ?format=xyz -> **fallback** to CSV (we dynamically accept it)
    - Filtering: owner-scoped; extend with query params later if needed
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer, PassthroughCSVRenderer]
    throttle_scope = "events-export"

    def get_renderers(self):
        """
        DRF negotiates a renderer before calling `get()`. If a client passes
        `?format=xyz` and no renderer advertises `format="xyz"`, DRF would 404.

        To support a graceful fallback (and keep our tests green), dynamically
        add a one-off renderer whose `format` matches the requested value,
        so negotiation succeeds. We still return an HttpResponse (CSV) below.
        """
        renderers = super().get_renderers()
        fmt = (self.request.query_params.get(api_settings.URL_FORMAT_OVERRIDE) or "").strip().lower()
        if fmt:
            advertised = {getattr(r, "format", None) for r in renderers}
            if fmt not in advertised:
                # Create a one-off renderer class matching the requested format.
                # It inherits PassthroughCSVRenderer so it is harmless if ever used.
                class _DynamicRenderer(PassthroughCSVRenderer):  # type: ignore
                    format = fmt
                    # media_type is not critical for query-parameter format matching
                    media_type = "text/plain"

                renderers.append(_DynamicRenderer())
        return renderers

    @extend_schema(
        tags=["Events: Export"],
        parameters=[
            OpenApiParameter(
                name="format",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Export format: "csv" (default/fallback) or "json".',
            ),
        ],
        responses={200: None},
        description="Export your events as CSV or JSON (unpaginated).",
        operation_id="events_export",
    )
    def get(self, request):
        """
        Return events in the requested format.

        Headers:
            - X-Export-Total: number of events matching filters.
            - X-Export-Limit: maximum rows emitted (for JSON and CSV).
            - X-Export-Truncated: true when total > limit.
        """
        fmt = (request.query_params.get("format") or "").lower().strip()
        queryset = (
            Event.objects
            .filter(user=request.user)
            .select_related("batch", "plant")
            .order_by("-happened_at", "-created_at")
        )

        if fmt == "json":
            limit = int(getattr(settings, "EXPORT_MAX_ROWS", 100_000))
            total = queryset.count()
            data = serialize_events_to_json(queryset[:limit], request)
            resp = Response(data)
            resp["X-Export-Total"] = str(total)
            resp["X-Export-Limit"] = str(limit)
            resp["X-Export-Truncated"] = "true" if total > limit else "false"
            return resp

        # Default to CSV for fmt in {"", "csv", anything-else}
        return render_events_to_csv(queryset)
