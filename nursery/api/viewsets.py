from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema_view, extend_schema

from core.permissions import IsOwner
from nursery.models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    Event,
    AuditLog,
    AuditAction,
)
from nursery.serializers import (
    TaxonSerializer,
    PlantMaterialSerializer,
    PropagationBatchSerializer,
    PlantSerializer,
    EventSerializer,
)

from .batch_ops import BatchOpsMixin
from .plant_ops import PlantOpsMixin
from .mixins import ETagConcurrencyMixin, _snapshot_model, _diff, _request_meta


class OwnedModelViewSet(ETagConcurrencyMixin, viewsets.ModelViewSet):
    """
    Base ViewSet that:
      - Requires authentication
      - Applies object-level IsOwner permissions
      - Scopes queryset by request.user
      - Sets obj.user on create
      - Adds optimistic concurrency (ETag/If-Match)
      - Writes AuditLog entries for create/update/delete (API-originated only)
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        base_qs = super().get_queryset()
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return base_qs.none()
        return base_qs.filter(user=user)

    def _audit_write(self, instance, action: str, before: dict | None, after: dict | None):
        # Minimal, inline to avoid import cycles
        owner = getattr(instance, "user", None) or self.request.user
        rid, ip, ua = _request_meta(self.request)
        ct = ContentType.objects.get_for_model(instance, for_concrete_model=False)
        AuditLog.objects.create(
            user=owner,
            actor=self.request.user if self.request.user.is_authenticated else None,
            content_type=ct,
            object_id=getattr(instance, "pk", None) or 0,
            action=action,
            changes=_diff(before, after),
            request_id=rid,
            ip=ip,
            user_agent=ua,
        )

    def perform_create(self, serializer):
        instance = serializer.save(user=self.request.user)
        self._audit_write(instance, AuditAction.CREATE, None, _snapshot_model(instance))

    def perform_update(self, serializer):
        # Capture "before" snapshot from DB to detect real changes
        model = serializer.Meta.model
        pk = self.get_object().pk  # call get_object once to respect IsOwner
        before_obj = model.objects_all.get(pk=pk) if hasattr(model, "objects_all") else model.objects.get(pk=pk)
        before = _snapshot_model(before_obj)

        instance = serializer.save()
        after = _snapshot_model(instance)

        # Only write if something actually changed
        if any(v[0] != v[1] for v in _diff(before, after).values()):
            self._audit_write(instance, AuditAction.UPDATE, before, after)

    def perform_destroy(self, instance):
        before = _snapshot_model(instance)
        obj_id = instance.pk
        self._audit_write(instance, AuditAction.DELETE, before, None)
        super().perform_destroy(instance)


@extend_schema_view(
    list=extend_schema(tags=["Taxa"], description="List taxa (owner scoped)."),
    retrieve=extend_schema(tags=["Taxa"], description="Retrieve a single taxon."),
    create=extend_schema(tags=["Taxa"], description="Create a taxon."),
    update=extend_schema(tags=["Taxa"], description="Update a taxon."),
    partial_update=extend_schema(tags=["Taxa"], description="Partial update a taxon."),
)
class TaxonViewSet(OwnedModelViewSet):
    lookup_value_regex = r"\d+"
    queryset = Taxon.objects.all()
    serializer_class = TaxonSerializer
    filterset_fields = ["scientific_name", "cultivar", "clone_code"]
    search_fields = ["scientific_name", "cultivar", "clone_code"]
    ordering_fields = ["scientific_name", "cultivar", "created_at", "updated_at"]
    ordering = ["scientific_name", "cultivar"]


@extend_schema_view(
    list=extend_schema(tags=["Materials"], description="List plant materials."),
    retrieve=extend_schema(tags=["Materials"], description="Retrieve a plant material."),
    create=extend_schema(tags=["Materials"], description="Create a plant material."),
    update=extend_schema(tags=["Materials"], description="Update a plant material."),
    partial_update=extend_schema(tags=["Materials"], description="Partial update a plant material."),
)
class PlantMaterialViewSet(OwnedModelViewSet):
    lookup_value_regex = r"\d+"
    queryset = PlantMaterial.objects.select_related("taxon").all()
    serializer_class = PlantMaterialSerializer
    filterset_fields = ["taxon", "material_type", "lot_code"]
    search_fields = ["lot_code", "taxon__scientific_name", "taxon__cultivar", "taxon__clone_code"]
    ordering_fields = ["created_at", "updated_at", "material_type"]
    ordering = ["-created_at"]


@extend_schema_view(
    list=extend_schema(tags=["Batches"], description="List propagation batches."),
    retrieve=extend_schema(tags=["Batches"], description="Retrieve a propagation batch."),
    create=extend_schema(tags=["Batches"], description="Create a propagation batch."),
    update=extend_schema(tags=["Batches"], description="Update a propagation batch."),
    partial_update=extend_schema(tags=["Batches"], description="Partial update a propagation batch."),
)
class PropagationBatchViewSet(BatchOpsMixin, OwnedModelViewSet):
    lookup_value_regex = r"\d+"
    queryset = PropagationBatch.objects.select_related("material", "material__taxon").all()
    serializer_class = PropagationBatchSerializer
    filterset_fields = ["material", "method", "status", "started_on"]
    search_fields = [
        "material__lot_code",
        "material__taxon__scientific_name",
        "material__taxon__cultivar",
        "material__taxon__clone_code",
    ]
    ordering_fields = ["started_on", "created_at", "updated_at", "quantity_started", "status"]
    ordering = ["-started_on", "-created_at"]

    # Disallow hard DELETE; use /archive/ action instead.
    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Hard delete is disabled. Use POST /api/batches/{id}/archive/."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)


@extend_schema_view(
    list=extend_schema(tags=["Plants"], description="List plants."),
    retrieve=extend_schema(tags=["Plants"], description="Retrieve a plant."),
    create=extend_schema(tags=["Plants"], description="Create a plant."),
    update=extend_schema(tags=["Plants"], description="Update a plant."),
    partial_update=extend_schema(tags=["Plants"], description="Partial update a plant."),
)
class PlantViewSet(PlantOpsMixin, OwnedModelViewSet):
    lookup_value_regex = r"\d+"
    queryset = Plant.objects.select_related("taxon", "batch").all()
    serializer_class = PlantSerializer
    filterset_fields = ["taxon", "batch", "status", "acquired_on"]
    search_fields = ["taxon__scientific_name", "taxon__cultivar", "taxon__clone_code"]
    ordering_fields = ["created_at", "updated_at", "acquired_on", "quantity", "status"]
    ordering = ["-created_at"]

    # Disallow hard DELETE; use /archive/ action instead.
    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Hard delete is disabled. Use POST /api/plants/{id}/archive/."},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)


@extend_schema_view(
    list=extend_schema(tags=["Events"], description="List events (plant or batch)."),
    retrieve=extend_schema(tags=["Events"], description="Retrieve an event."),
    create=extend_schema(tags=["Events"], description="Create an event."),
    update=extend_schema(tags=["Events"], description="Update an event."),
    partial_update=extend_schema(tags=["Events"], description="Partial update an event."),
)
class EventViewSet(OwnedModelViewSet):
    lookup_value_regex = r"\d+"
    queryset = Event.objects.select_related("batch", "plant").all()
    serializer_class = EventSerializer
    filterset_fields = ["batch", "plant", "event_type", "happened_at"]
    search_fields = ["notes"]
    ordering_fields = ["happened_at", "created_at", "updated_at", "event_type"]
    ordering = ["-happened_at", "-created_at"]
