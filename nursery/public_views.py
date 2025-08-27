from __future__ import annotations

import hashlib
import io
from typing import Optional

from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from nursery.models import LabelToken, LabelVisit

# QR code (SVG) generation
import qrcode
from qrcode.image.svg import SvgImage


def _hash_token(raw: str) -> str:
    """Stable SHA-256 hex digest for raw token strings."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _client_ip(request) -> Optional[str]:
    """
    Best-effort IP extraction. Keeps it simple for dev/tests.
    Prefer REMOTE_ADDR; fall back to first X-Forwarded-For if present.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[0]
    return request.META.get("REMOTE_ADDR") or None


def _qr_svg_bytes(text: str) -> bytes:
    """
    Produce an SVG QR for the given text (absolute URL).
    Returns raw SVG bytes.
    """
    qr = qrcode.QRCode(
        version=None,  # fit automatically
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgImage)  # full <svg> document
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


@extend_schema(exclude=True)  # exclude from OpenAPI schema (APIView without serializer)
class PublicLabelQRView(APIView):
    """
    Public QR image for a given *raw* token.
    - No auth.
    - Purely encodes the public URL `/p/<token>/`.
    - **Immutable**: long-lived cache headers; strong ETag; supports If-None-Match.
    - Throttled via `label-public` scope.
    """
    permission_classes = [AllowAny]
    throttle_scope = "label-public"

    def get(self, request, token: str, *args, **kwargs) -> HttpResponse:
        # Build the absolute URL to the public label page
        url = request.build_absolute_uri(reverse("label-public", kwargs={"token": token}))

        # Strong ETag derived from the *text* the QR encodes.
        etag = hashlib.sha256(("qr:" + url).encode("utf-8")).hexdigest()
        inm = request.META.get("HTTP_IF_NONE_MATCH")
        if inm and etag in inm:
            # Short 304 path for caches
            resp = HttpResponse(status=304)
            resp["ETag"] = etag
            resp["Cache-Control"] = "public, max-age=31536000, immutable"
            resp["Content-Type"] = "image/svg+xml; charset=utf-8"
            return resp

        svg = _qr_svg_bytes(url)
        resp = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8")
        resp["ETag"] = etag
        resp["Cache-Control"] = "public, max-age=31536000, immutable"
        # Optional: filename hint
        resp["Content-Disposition"] = 'inline; filename="label-qr.svg"'
        return resp


@extend_schema(exclude=True)  # exclude from OpenAPI schema (APIView without serializer)
class PublicLabelView(APIView):
    """
    Public, human-friendly page for a label token.
    - No authentication required (AllowAny).
    - Renders HTML via TemplateHTMLRenderer.
    - Accepts either a *full raw token* (hash match) or the 12-char *prefix*.
    - Records a LabelVisit for analytics.
    - If the target object is archived (soft-deleted), respond 404.
    """
    permission_classes = [AllowAny]
    renderer_classes = [TemplateHTMLRenderer]
    template_name = "public/label_detail.html"
    throttle_scope = "label-public"  # DRF ScopedRateThrottle applies

    def get(self, request, token: str):
        now = timezone.now()  # reserved for future expiry logic

        # 1) Try full raw token (hash match)
        token_hash = _hash_token(token)
        lt = (
            LabelToken.objects
            .select_related("label", "label__content_type")
            .filter(token_hash=token_hash, revoked_at__isnull=True)
            .first()
        )

        # 2) Fallback: allow visiting by prefix (used on printed labels)
        if not lt:
            lt = (
                LabelToken.objects
                .select_related("label", "label__content_type")
                .filter(prefix=token, revoked_at__isnull=True)
                .order_by("-created_at")
                .first()
            )

        if not lt:
            # Not found or revoked -> 404 page (HTML)
            return Response({"status": "not_found"}, status=404, template_name=self.template_name)

        label = lt.label
        target = label.target  # GenericFK

        # Stop resolving if the target has been archived (soft-deleted)
        if hasattr(target, "is_deleted") and getattr(target, "is_deleted", False):
            return Response({"status": "not_found"}, status=404, template_name=self.template_name)

        # Record a visit (owned by the label's owner to preserve per-tenant analytics)
        LabelVisit.objects.create(
            user=label.user,
            label=label,
            token=lt,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:256],
            referrer=request.META.get("HTTP_REFERER", "")[:512],
        )

        ctx = {
            "status": "ok",
            "token_prefix": lt.prefix,
            "label_id": label.id,
            "updated_at": label.updated_at,
        }

        model_name = label.content_type.model
        if model_name == "plant":
            ctx["kind"] = "plant"
            ctx["taxon"] = str(getattr(target, "taxon", ""))
            ctx["status_text"] = target.get_status_display() if hasattr(target, "get_status_display") else ""
            ctx["acquired_on"] = getattr(target, "acquired_on", None)
            ctx["last_event"] = (getattr(target, "events", None).order_by("-happened_at").first()
                                 if hasattr(target, "events") else None)
        elif model_name == "propagationbatch":
            ctx["kind"] = "batch"
            material = getattr(target, "material", None)
            taxon = getattr(material, "taxon", None) if material else None
            ctx["taxon"] = str(taxon) if taxon else ""
            ctx["material"] = str(material) if material else ""
            ctx["method"] = target.get_method_display() if hasattr(target, "get_method_display") else ""
            ctx["status_text"] = target.get_status_display() if hasattr(target, "get_status_display") else ""
            ctx["started_on"] = getattr(target, "started_on", None)
            ctx["quantity_started"] = getattr(target, "quantity_started", None)
            ctx["last_event"] = (getattr(target, "events", None).order_by("-happened_at").first()
                                 if hasattr(target, "events") else None)
        elif model_name == "plantmaterial":
            ctx["kind"] = "material"
            ctx["taxon"] = str(getattr(target, "taxon", ""))
            ctx["type_text"] = target.get_material_type_display() if hasattr(target, "get_material_type_display") else ""
            ctx["lot_code"] = getattr(target, "lot_code", "")
        else:
            ctx["kind"] = model_name

        # 200 HTML page with safe fields
        return Response(ctx, template_name=self.template_name)
