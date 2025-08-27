from __future__ import annotations

"""
Custom DRF renderer for CSV passthrough.

Purpose
-------
- Allow `?format=csv` or `Accept: text/csv` to negotiate cleanly with DRF without
  forcing every CSV view to build raw `HttpResponse` manually.
- Views may still return an `HttpResponse` they construct themselves; this renderer
  only affects cases where a `Response(...)` with a string/bytes payload is used.

Notes
-----
- We emit UTF-8 bytes and do not set a charset on the media type (common for CSV).
- For non-str/bytes payloads, we JSON-dump as a best-effort rather than crash.

Security:
    No special considerations; renderer performs no serialization of model
    instances on its own and trusts the view's payload.
"""

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
        # NOTE: DRF passes the Response.data here; we assume the view already
        # constructed a valid CSV string or bytes. We avoid adding BOM.
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
