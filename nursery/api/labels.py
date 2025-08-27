from __future__ import annotations

import hashlib
import io
import secrets
from datetime import timedelta, date
from xml.etree import ElementTree as ET

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from core.permissions import IsOwner
from core.utils.idempotency import idempotent
from nursery.models import Label, LabelToken, LabelVisit
from nursery.serializers import (
    LabelSerializer,
    LabelCreateSerializer,
    LabelStatsSerializer,
    LabelStatsQuerySerializer,
    LabelVisitSeriesPointSerializer,
    LabelStatsWithSeriesSerializer,
)
# QR code (SVG) generation
import qrcode
from qrcode.image.svg import SvgImage

# Shared OpenAPI components
from nursery.schema import (
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENCY_EXAMPLE,
    LABEL_OWNER_QR_TOKEN_PARAM,
    VALIDATION_ERROR_RESPONSE,
)

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


def _hash_token(raw: str) -> str:
    """Create a SHA-256 hex digest for a raw token (never store raw)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_token() -> str:
    """Generate a URL-safe token (~192 bits entropy, ~32–34 chars)."""
    return secrets.token_urlsafe(24)


def _qr_svg_bytes(text: str, *, link_url: str | None = None) -> bytes:
    """
    Generate an SVG QR image for `text` (absolute URL).
    If link_url is provided, wrap all <svg> children in <a xlink:href="...">.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgImage)
    buf = io.BytesIO()
    img.save(buf)
    svg_bytes = buf.getvalue()

    if not link_url:
        return svg_bytes

    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes

    if root.tag != f"{{{SVG_NS}}}svg":
        return svg_bytes

    a_el = ET.Element(f"{{{SVG_NS}}}a")
    a_el.set(f"{{{XLINK_NS}}}href", link_url)
    a_el.set("target", "_blank")

    children = list(root)
    for child in children:
        root.remove(child)
        a_el.append(child)
    root.append(a_el)

    return ET.tostring(root, encoding="utf-8", method="xml")


class LabelViewSet(viewsets.ModelViewSet):
    """
    Owner-scoped CRUD for QR Labels with token rotation and stats.

    Security:
      - Objects are owner-scoped (IsAuthenticated + IsOwner).
      - Raw tokens are returned only on create/rotate and are never persisted.
      - Public page is separate (`/p/<token>/`) and handled elsewhere.

    Concurrency:
      - Token rotation happens within a transaction; we lock the Label row
        to prevent racing rotates.

    API:
      - POST /api/labels/              -> 201 with {token, public_url, ...}
      - POST /api/labels/{id}/rotate/  -> 200 with {token, public_url, ...}
      - POST /api/labels/{id}/revoke/  -> 200 {"revoked": true}
      - GET  /api/labels/{id}/stats/   -> 200 owner-only analytics
      - GET  /api/labels/{id}/qr/?token=<RAW> -> 200 SVG (owner-only; no-store; clickable)
    """

    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = LabelSerializer
    queryset = Label.objects.select_related("active_token").all()
    filterset_fields: list[str] = []
    search_fields: list[str] = []
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return qs.none()
        return qs.filter(user=user)

    def get_serializer_class(self):
        if self.action in {"create", "rotate"}:
            return LabelCreateSerializer
        return LabelSerializer

    def _issue_token(self, label: Label) -> tuple[LabelToken, str]:
        raw = _new_token()
        token = LabelToken.objects.create(
            label=label,
            token_hash=_hash_token(raw),
            prefix=raw[:12],
        )
        return token, raw

    def _revoke_active(self, label: Label) -> None:
        if label.active_token_id:
            LabelToken.objects.filter(
                pk=label.active_token_id,
                revoked_at__isnull=True,
            ).update(revoked_at=timezone.now())

    def _public_url(self, request: Request, raw_token: str) -> str:
        url = reverse("label-public", kwargs={"token": raw_token})
        return request.build_absolute_uri(url)

    @extend_schema(
        tags=["Labels"],
        parameters=[IDEMPOTENCY_KEY_HEADER],
        request=LabelCreateSerializer,
        responses={201: LabelCreateSerializer, 400: VALIDATION_ERROR_RESPONSE},
        examples=[IDEMPOTENCY_EXAMPLE],
        description="Create a label for a target (plant, batch, or material). Returns a raw token once.",
    )
    @idempotent
    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_obj = serializer.validated_data["target"]
        ct = ContentType.objects.get_for_model(type(target_obj))

        existing = Label.objects.filter(
            user=request.user,
            content_type=ct,
            object_id=target_obj.pk,
        ).first()
        if existing and request.query_params.get("force") != "true":
            return Response(
                {"non_field_errors": ["Label already exists for this target. Use ?force=true to rotate."]},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            label = existing or Label.objects.create(
                user=request.user,
                content_type=ct,
                object_id=target_obj.pk,
            )
            if label.pk and existing:
                label = Label.objects.select_for_update().get(pk=label.pk)

            token, raw = self._issue_token(label)
            if label.active_token_id and label.active_token_id != token.id:
                self._revoke_active(label)
            label.active_token = token
            label.save(update_fields=["active_token", "updated_at"])

        out = LabelCreateSerializer(label, context={"request": request}).data
        out["token"] = raw
        out["public_url"] = self._public_url(request, raw)
        return Response(out, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["Labels"], responses={200: LabelSerializer}, description="Retrieve a label.")
    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["Labels"],
        parameters=[IDEMPOTENCY_KEY_HEADER],
        responses={200: LabelCreateSerializer},
        examples=[IDEMPOTENCY_EXAMPLE],
        description="Rotate the label token. Revokes previous token and returns a new raw token once.",
    )
    @action(detail=True, methods=["post"], url_path="rotate")
    @idempotent
    def rotate(self, request: Request, pk: str | None = None) -> Response:
        label = self.get_object()
        with transaction.atomic():
            label = Label.objects.select_for_update().get(pk=label.pk)
            token, raw = self._issue_token(label)
            if label.active_token_id and label.active_token_id != token.id:
                self._revoke_active(label)
            label.active_token = token
            label.save(update_fields=["active_token", "updated_at"])

        out = LabelCreateSerializer(label, context={"request": request}).data
        out["token"] = raw
        out["public_url"] = self._public_url(request, raw)
        return Response(out, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Labels"],
        responses={200: dict},
        description="Revoke the active token. Public URL will stop working. Safe to call multiple times.",
    )
    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request: Request, pk: str | None = None) -> Response:
        label = self.get_object()
        with transaction.atomic():
            label = Label.objects.select_for_update().get(pk=label.pk)
            self._revoke_active(label)
            if label.active_token_id:
                label.active_token = None
                label.save(update_fields=["active_token", "updated_at"])
        return Response({"id": label.id, "revoked": True}, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Labels"],
        parameters=[LABEL_OWNER_QR_TOKEN_PARAM],
        responses={200: dict},
        description=(
            "Return an SVG QR that encodes the public URL for this label's *raw* token. "
            "Requires `?token=<RAW>` for the **current active token** of this label. "
            "Response is **not cacheable** (no-store). The SVG is fully clickable and "
            "opens the encoded URL in a new tab."
        ),
    )
    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request: Request, pk: str | None = None):
        label = self.get_object()  # IsOwner enforced
        raw = (request.query_params.get("token") or "").strip()
        if not raw:
            return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate proof-of-possession: must match the current active token
        if not label.active_token_id or _hash_token(raw) != label.active_token.token_hash:
            return Response({"detail": "Invalid token for this label."}, status=status.HTTP_403_FORBIDDEN)

        url = self._public_url(request, raw)
        svg = _qr_svg_bytes(url, link_url=url)

        resp = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8")
        # Owner QR should never be cached
        resp["Cache-Control"] = "no-store"
        resp["Content-Disposition"] = 'inline; filename="label-qr.svg"'
        return resp

    @extend_schema(
        tags=["Labels"],
        parameters=[
            # keep param explicit for docs
            # (LabelStatsQuerySerializer also handles it as query serializer)
        ],
        responses={200: LabelStatsWithSeriesSerializer},
        description=(
            "Owner-only analytics for a label.\n"
            "- No `days`: returns legacy counts only.\n"
            "- `?days=N` (1–365): returns counts + per-day dense series with window metadata."
        ),
    )
    @action(detail=True, methods=["get"], url_path="stats")
    def stats(self, request: Request, pk: str | None = None) -> Response:
        label = self.get_object()  # IsOwner enforces ownership

        now = timezone.now()
        visits = LabelVisit.objects.filter(label=label)

        # Legacy counters (always computed)
        base = {
            "label_id": label.id,
            "total_visits": visits.count(),
            "last_7d": visits.filter(requested_at__gte=now - timedelta(days=7)).count(),
            "last_30d": visits.filter(requested_at__gte=now - timedelta(days=30)).count(),
        }

        # If no days provided -> return legacy-only serializer
        qser = LabelStatsQuerySerializer(data=request.query_params)
        qser.is_valid(raise_exception=False)  # optional param; fall back if invalid
        days = qser.validated_data.get("days") if hasattr(qser, "validated_data") else None
        if not days:
            return Response(LabelStatsSerializer(base).data, status=status.HTTP_200_OK)

        # Compute inclusive window
        end_date: date = now.date()
        start_date: date = (now - timedelta(days=days - 1)).date()

        # Group by date in DB
        agg = (
            visits.filter(requested_at__date__gte=start_date, requested_at__date__lte=end_date)
            .annotate(d=TruncDate("requested_at"))
            .values("d")
            .annotate(visits=Count("id"))
        )
        by_day = {row["d"]: int(row["visits"]) for row in agg}

        # Fill dense series covering every day in the window
        series: list[dict] = []
        cursor = start_date
        while cursor <= end_date:
            series.append({"date": cursor, "visits": by_day.get(cursor, 0)})
            cursor += timedelta(days=1)

        payload = {
            **base,
            "window_days": days,
            "start_date": start_date,
            "end_date": end_date,
            "series": series,
        }
        return Response(LabelStatsWithSeriesSerializer(payload).data, status=status.HTTP_200_OK)
