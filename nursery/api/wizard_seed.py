from typing import Dict, Optional

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.reverse import reverse as drf_reverse

from drf_spectacular.utils import OpenApiParameter, extend_schema

from core.permissions import IsOwner
from core.utils.idempotency import idempotent
from nursery.models import (
    EventType,
    MaterialType,
    PropagationBatch,
    PropagationMethod,
    Taxon,
    PlantMaterial,
)
from nursery.serializers import (
    EventSerializer,
    PlantMaterialSerializer,
    PropagationBatchSerializer,
    TaxonSerializer,
)


class EmptySerializer(serializers.Serializer):
    """Placeholder to satisfy ViewSet.serializer_class for schema generation."""
    pass


# ---- Schema request/response serializers ----

class SelectTaxonRequestSerializer(serializers.Serializer):
    taxon_id = serializers.IntegerField(required=False)
    taxon = TaxonSerializer(required=False)


class CreateMaterialRequestSerializer(serializers.Serializer):
    taxon_id = serializers.IntegerField()
    material = PlantMaterialSerializer()


class CreateBatchRequestSerializer(serializers.Serializer):
    material_id = serializers.IntegerField()
    batch = PropagationBatchSerializer()


class LogSowRequestSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    event = EventSerializer(required=False)


class ComposeRequestSerializer(serializers.Serializer):
    taxon = TaxonSerializer(required=False)
    material = PlantMaterialSerializer()
    batch = PropagationBatchSerializer()
    event = EventSerializer(required=False)


class SelectTaxonResponseSerializer(serializers.Serializer):
    taxon_id = serializers.IntegerField()
    next = serializers.DictField(child=serializers.CharField())


class CreateMaterialResponseSerializer(serializers.Serializer):
    material_id = serializers.IntegerField()
    next = serializers.DictField(child=serializers.CharField())


class CreateBatchResponseSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    next = serializers.DictField(child=serializers.CharField())


class LogSowResponseSerializer(serializers.Serializer):
    event_id = serializers.IntegerField()
    complete = serializers.BooleanField()
    links = serializers.DictField(child=serializers.CharField())


class ComposeResponseSerializer(serializers.Serializer):
    taxon_id = serializers.IntegerField()
    material_id = serializers.IntegerField()
    batch_id = serializers.IntegerField()
    event_id = serializers.IntegerField()


# Reusable OpenAPI header parameter for Idempotency-Key
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


class WizardSeedViewSet(viewsets.ViewSet):
    """
    Seed onboarding wizard: Taxon -> PlantMaterial(SEED) -> PropagationBatch(SEED_SOWING) -> initial SOW Event.

    Security & QoS
    - Owner-scoped (IsAuthenticated + explicit IsOwner checks on fetched objects).
    - Scoped throttling via `throttle_scope = "wizard-seed"` (see DEFAULT_THROTTLE_RATES).
    - Optional idempotency via 'Idempotency-Key' header (persistent replay when model exists).
    """
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = EmptySerializer
    throttle_scope = "wizard-seed"

    # ---- helpers ----

    def _ensure_owner(self, obj, request: Request) -> None:
        """Raise 404 for non-owned objects (consistent with IsOwner)."""
        if getattr(obj, "user_id", None) != request.user.id:
            from rest_framework.exceptions import NotFound
            raise NotFound()

    def _next_link(self, request: Request, friendly: str) -> Dict[str, Dict[str, str]]:
        """
        Build the next-step link using DRF route names for robustness.
        Falls back to a stable relative path if reversing fails.

        friendly: one of {"material","batch","sow"}
        """
        action_map = {"material": "create-material", "batch": "create-batch", "sow": "log-sow"}
        url_path = action_map[friendly]
        route_name = f"wizard-seed-{url_path}"
        try:
            url = drf_reverse(route_name, request=request)
        except Exception:
            url = f"/api/wizard/seed/{url_path}/"
        return {"next": {friendly: url}}

    # ---- steps ----
    # IMPORTANT: @action MUST be the OUTERMOST decorator so DRF sees its attributes.

    @extend_schema(
        tags=["Wizard: Seed"],
        parameters=[IDEMPOTENCY_PARAM],
        request=SelectTaxonRequestSerializer,
        responses={200: SelectTaxonResponseSerializer, 201: SelectTaxonResponseSerializer},
        description="Step 1: Select an existing Taxon by ID or create a new one.",
    )
    @action(detail=False, methods=["post"], url_path="select-taxon")
    @idempotent
    def select_taxon(self, request: Request) -> Response:
        data = request.data or {}
        taxon_id = data.get("taxon_id")
        taxon_payload = data.get("taxon")

        if taxon_id is None and not isinstance(taxon_payload, dict):
            return Response(
                {"non_field_errors": ["Provide either taxon_id or taxon payload."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if taxon_id is not None and taxon_payload:
            return Response(
                {"non_field_errors": ["Provide only one of taxon_id or taxon."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if taxon_id is not None:
            try:
                taxon = Taxon.objects.get(pk=taxon_id)
            except Taxon.DoesNotExist:
                return Response({"taxon_id": ["Not found."]}, status=status.HTTP_404_NOT_FOUND)
            self._ensure_owner(taxon, request)
            return Response({"taxon_id": taxon.id, **self._next_link(request, "material")}, status=status.HTTP_200_OK)

        serializer = TaxonSerializer(data=taxon_payload)
        serializer.is_valid(raise_exception=True)
        taxon = serializer.save(user=request.user)
        return Response({"taxon_id": taxon.id, **self._next_link(request, "material")}, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Wizard: Seed"],
        parameters=[IDEMPOTENCY_PARAM],
        request=CreateMaterialRequestSerializer,
        responses={201: CreateMaterialResponseSerializer},
        description='Step 2: Create a PlantMaterial tied to the Taxon. Enforces material_type="SEED".',
    )
    @action(detail=False, methods=["post"], url_path="create-material")
    @idempotent
    def create_material(self, request: Request) -> Response:
        data = request.data or {}
        taxon_id = data.get("taxon_id")
        material = data.get("material") or {}

        if not taxon_id:
            return Response({"taxon_id": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            taxon = Taxon.objects.get(pk=taxon_id)
        except Taxon.DoesNotExist:
            return Response({"taxon_id": ["Not found."]}, status=status.HTTP_404_NOT_FOUND)
        self._ensure_owner(taxon, request)

        if material.get("material_type") != MaterialType.SEED:
            return Response(
                {"material.material_type": [f'Must be "{MaterialType.SEED}".']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = dict(material)
        payload["taxon"] = taxon.id

        serializer = PlantMaterialSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(user=request.user)
        return Response({"material_id": obj.id, **self._next_link(request, "batch")}, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Wizard: Seed"],
        parameters=[IDEMPOTENCY_PARAM],
        request=CreateBatchRequestSerializer,
        responses={201: CreateBatchResponseSerializer},
        description='Step 3: Create a PropagationBatch from the material. Enforces method="SEED_SOWING".',
    )
    @action(detail=False, methods=["post"], url_path="create-batch")
    @idempotent
    def create_batch(self, request: Request) -> Response:
        data = request.data or {}
        material_id = data.get("material_id")
        batch = data.get("batch") or {}

        if not material_id:
            return Response({"material_id": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            material = PlantMaterial.objects.select_related("taxon").get(pk=material_id)
        except PlantMaterial.DoesNotExist:
            return Response({"material_id": ["Not found."]}, status=status.HTTP_404_NOT_FOUND)
        self._ensure_owner(material, request)

        if batch.get("method") != PropagationMethod.SEED_SOWING:
            return Response(
                {"batch.method": [f'Must be "{PropagationMethod.SEED_SOWING}".']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qty = batch.get("quantity_started")
        if not isinstance(qty, int) or qty < 1:
            return Response(
                {"batch.quantity_started": ["Must be an integer >= 1."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = dict(batch)
        payload["material"] = material.id

        serializer = PropagationBatchSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(user=request.user)
        return Response({"batch_id": obj.id, **self._next_link(request, "sow")}, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Wizard: Seed"],
        parameters=[IDEMPOTENCY_PARAM],
        request=LogSowRequestSerializer,
        responses={201: LogSowResponseSerializer},
        description='Step 4: Log the initial "SOW" event on the created batch.',
    )
    @action(detail=False, methods=["post"], url_path="log-sow")
    @idempotent
    def log_sow(self, request: Request) -> Response:
        data = request.data or {}
        batch_id = data.get("batch_id")
        event = (data.get("event") or {}).copy()

        if not batch_id:
            return Response({"batch_id": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            batch = PropagationBatch.objects.get(pk=batch_id)
        except PropagationBatch.DoesNotExist:
            return Response({"batch_id": ["Not found."]}, status=status.HTTP_404_NOT_FOUND)
        self._ensure_owner(batch, request)

        event.setdefault("event_type", EventType.SOW)
        event.setdefault("happened_at", timezone.now().isoformat())
        event["batch"] = batch.id
        event.pop("plant", None)

        serializer = EventSerializer(data=event)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(user=request.user)
        return Response(
            {
                "event_id": obj.id,
                "complete": True,
                "links": {"batch": f"/api/batches/{batch.id}/"},
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["Wizard: Seed"],
        parameters=[IDEMPOTENCY_PARAM],
        request=ComposeRequestSerializer,
        responses={201: ComposeResponseSerializer},
        description=(
            "One-shot: Create (optional) Taxon, PlantMaterial(SEED), PropagationBatch(SEED_SOWING), "
            "and a SOW Event atomically."
        ),
    )
    @action(detail=False, methods=["post"], url_path="compose")
    @idempotent
    def compose(self, request: Request) -> Response:
        payload = request.data or {}
        taxon_spec = payload.get("taxon") or {}
        material_spec = payload.get("material") or {}
        batch_spec = payload.get("batch") or {}
        event_spec = (payload.get("event") or {}).copy()

        if material_spec.get("material_type") != MaterialType.SEED:
            return Response({"material.material_type": [f'Must be "{MaterialType.SEED}".']}, status=status.HTTP_400_BAD_REQUEST)
        if batch_spec.get("method") != PropagationMethod.SEED_SOWING:
            return Response({"batch.method": [f'Must be "{PropagationMethod.SEED_SOWING}".']}, status=status.HTTP_400_BAD_REQUEST)
        qty = batch_spec.get("quantity_started")
        if not isinstance(qty, int) or qty < 1:
            return Response({"batch.quantity_started": ["Must be an integer >= 1."]}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            taxon_id: Optional[int] = taxon_spec.get("id")
            if taxon_id:
                try:
                    taxon = Taxon.objects.get(pk=taxon_id)
                except Taxon.DoesNotExist:
                    return Response({"taxon.id": ["Not found."]}, status=status.HTTP_404_NOT_FOUND)
                self._ensure_owner(taxon, request)
            else:
                ts = TaxonSerializer(data=taxon_spec)
                ts.is_valid(raise_exception=True)
                taxon = ts.save(user=request.user)

            m_payload = dict(material_spec)
            m_payload["taxon"] = taxon.id
            ms = PlantMaterialSerializer(data=m_payload)
            ms.is_valid(raise_exception=True)
            material = ms.save(user=request.user)

            b_payload = dict(batch_spec)
            b_payload["material"] = material.id
            bs = PropagationBatchSerializer(data=b_payload)
            bs.is_valid(raise_exception=True)
            batch = bs.save(user=request.user)

            event_spec.setdefault("event_type", EventType.SOW)
            event_spec.setdefault("happened_at", timezone.now().isoformat())
            event_spec["batch"] = batch.id
            event_spec.pop("plant", None)

            es = EventSerializer(data=event_spec)
            es.is_valid(raise_exception=True)
            event = es.save(user=request.user)

        return Response(
            {
                "taxon_id": taxon.id,
                "material_id": material.id,
                "batch_id": batch.id,
                "event_id": event.id,
            },
            status=status.HTTP_201_CREATED,
        )
