from __future__ import annotations

import hashlib
import secrets

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from drf_spectacular.utils import OpenApiParameter, extend_schema

from core.permissions import IsOwner
from core.utils.idempotency import idempotent
from nursery.models import Label, LabelToken
from nursery.serializers import LabelCreateSerializer, LabelSerializer


IDEMPOTENCY_PARAM = OpenApiParameter(
    name="Idempotency-Key",
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "If provided, the server will replay the first stored response for the same "
        "user + method + path + body hash within the retention window."
    ),
)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_token() -> str:
    # ~192 bits entropy; URL-safe; ~32-34 chars
    return secrets.token_urlsafe(24)


class LabelViewSet(viewsets.ModelViewSet):
    """
    Owner-scoped CRUD for Labels plus rotate/revoke actions.
    Raw token is only returned on create/rotate and is never stored.
    """
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = LabelSerializer
    queryset = Label.objects.select_related("active_token").all()
    filterset_fields = []
    search_fields = []
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

    def _public_url(self, request: Request, raw_token: str) -> str:
        return request.build_absolute_uri(f"/p/{raw_token}/")

    @extend_schema(
        tags=["Labels"],
        parameters=[IDEMPOTENCY_PARAM],
        request=LabelCreateSerializer,
        responses={201: LabelCreateSerializer},
        description="Create a label for a target (plant, batch, or material). Returns a raw token once.",
    )
    @idempotent  # standard create; no @action needed
    def create(self, request: Request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_obj = serializer.validated_data["target"]
        ct = ContentType.objects.get_for_model(type(target_obj))

        # If label exists: 409 unless ?force=true
        existing = Label.objects.filter(user=request.user, content_type=ct, object_id=target_obj.pk).first()
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
            # Issue token and rotate active
            token, raw = self._issue_token(label)
            if label.active_token_id and label.active_token_id != token.id:
                LabelToken.objects.filter(pk=label.active_token_id, revoked_at__isnull=True).update(
                    revoked_at=timezone.now()
                )
            label.active_token = token
            label.save(update_fields=["active_token", "updated_at"])

        out = LabelCreateSerializer(label, context={"request": request}).data
        out["token"] = raw
        out["public_url"] = self._public_url(request, raw)
        return Response(out, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Labels"],
        responses={200: LabelSerializer},
        description="Retrieve a label. Does not return raw token.",
    )
    def retrieve(self, request: Request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["Labels"],
        parameters=[IDEMPOTENCY_PARAM],
        responses={200: LabelCreateSerializer},
        description="Rotate the label token. Revokes previous token and returns a new raw token once.",
    )
    @action(detail=True, methods=["post"], url_path="rotate")
    @idempotent
    def rotate(self, request: Request, pk=None) -> Response:
        label = self.get_object()
        with transaction.atomic():
            token, raw = self._issue_token(label)
            if label.active_token_id and label.active_token_id != token.id:
                LabelToken.objects.filter(pk=label.active_token_id, revoked_at__isnull=True).update(
                    revoked_at=timezone.now()
                )
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
    def revoke(self, request: Request, pk=None) -> Response:
        label = self.get_object()
        with transaction.atomic():
            if label.active_token_id:
                LabelToken.objects.filter(pk=label.active_token_id, revoked_at__isnull=True).update(
                    revoked_at=timezone.now()
                )
                label.active_token = None
                label.save(update_fields=["active_token", "updated_at"])
        return Response({"id": label.id, "revoked": True}, status=status.HTTP_200_OK)
