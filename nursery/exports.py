from __future__ import annotations

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
        fmt = (request.query_params.get("format") or "").lower().strip()
        queryset = (
            Event.objects
            .filter(user=request.user)
            .select_related("batch", "plant")
            .order_by("-happened_at", "-created_at")
        )

        if fmt == "json":
            data = serialize_events_to_json(queryset, request)
            return Response(data)

        # Default to CSV for fmt in {"", "csv", anything-else}
        return render_events_to_csv(queryset)
