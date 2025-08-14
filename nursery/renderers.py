from __future__ import annotations

from typing import Any, Optional

from rest_framework.renderers import BaseRenderer


class PassthroughCSVRenderer(BaseRenderer):
    """
    Minimal CSV renderer to satisfy DRF's URL format override and content
    negotiation when clients use `?format=csv` or `Accept: text/csv`.

    We still return a manually constructed HttpResponse for CSV in our view,
    but exposing this renderer prevents DRF from rejecting the request before
    our handler runs.

    If a Response() is ever rendered with this renderer, we fall back to a
    simple utf-8 encoding or JSON-dump to avoid crashes.
    """
    media_type = "text/csv"
    format = "csv"
    charset = None  # send bytes

    def render(
        self,
        data: Any,
        accepted_media_type: Optional[str] = None,
        renderer_context: Optional[dict] = None,
    ) -> bytes:
        if data is None:
            return b""
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, str):
            return data.encode("utf-8")

        # Best-effort JSON dump for arbitrary structures
        try:
            import json
            return json.dumps(data, ensure_ascii=False).encode("utf-8")
        except Exception:
            return str(data).encode("utf-8")
