from __future__ import annotations

from typing import Any, Optional

from rest_framework.renderers import BaseRenderer


class PassthroughCSVRenderer(BaseRenderer):
    """
    Minimal CSV renderer to satisfy DRF's URL format override and content
    negotiation when clients use `?format=csv` or `Accept: text/csv`.

    Views can return a regular `Response(str_or_bytes)` for CSV and let DRF
    render it, or still construct an HttpResponse manually. Register this
    renderer at the view level via `renderer_classes`.

    If a Response() is rendered with this renderer, we encode to UTF-8 bytes.
    For non-string/bytes payloads, we JSON-dump as a best effort to avoid crashes.
    """
    media_type = "text/csv"
    format = "csv"
    charset = None  # send bytes; we handle encoding explicitly

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
