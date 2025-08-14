from __future__ import annotations

import hashlib

from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema  # <-- add

from nursery.models import LabelToken


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@extend_schema(exclude=True)  # exclude from OpenAPI schema to avoid serializer guessing on APIView
class PublicLabelView(APIView):
    """
    Public, human-friendly page for a label token.
    - No authentication required (AllowAny).
    - Renders HTML via TemplateHTMLRenderer.
    - Shows only safe fields by target type.
    """
    permission_classes = [AllowAny]
    renderer_classes = [TemplateHTMLRenderer]
    template_name = "public/label_detail.html"
    throttle_scope = "label-public"  # DRF ScopedRateThrottle applies

    def get(self, request, token: str):
        token_hash = _hash_token(token)
        _now = timezone.now()  # reserved for future expiry logic
        lt = (
            LabelToken.objects
            .select_related("label", "label__content_type")
            .filter(token_hash=token_hash, revoked_at__isnull=True)
            .first()
        )
        if not lt:
            return Response({"status": "not_found"}, status=404, template_name=self.template_name)

        label = lt.label
        target = label.target  # GenericFK

        ctx = {"status": "ok", "token_prefix": lt.prefix, "label_id": label.id, "updated_at": label.updated_at}

        model_name = label.content_type.model
        if model_name == "plant":
            ctx["kind"] = "plant"
            ctx["taxon"] = str(target.taxon)
            ctx["status_text"] = target.get_status_display()
            ctx["acquired_on"] = target.acquired_on
            ctx["last_event"] = (target.events.order_by("-happened_at").first() or None)
        elif model_name == "propagationbatch":
            ctx["kind"] = "batch"
            ctx["taxon"] = str(target.material.taxon)
            ctx["material"] = str(target.material)
            ctx["method"] = target.get_method_display()
            ctx["status_text"] = target.get_status_display()
            ctx["started_on"] = target.started_on
            ctx["quantity_started"] = target.quantity_started
            ctx["last_event"] = (target.events.order_by("-happened_at").first() or None)
        elif model_name == "plantmaterial":
            ctx["kind"] = "material"
            ctx["taxon"] = str(target.taxon)
            ctx["type_text"] = target.get_material_type_display()
            ctx["lot_code"] = target.lot_code
        else:
            ctx["kind"] = model_name

        return Response(ctx, template_name=self.template_name)
