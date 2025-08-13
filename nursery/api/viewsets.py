from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsOwner
from nursery.models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    Event,
)
from nursery.serializers import (
    TaxonSerializer,
    PlantMaterialSerializer,
    PropagationBatchSerializer,
    PlantSerializer,
    EventSerializer,
)


class OwnedModelViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet that:
      - Requires authentication
      - Applies object-level IsOwner permissions
      - Scopes queryset by request.user
      - Sets obj.user on create

    Concrete subclasses must set `queryset` and `serializer_class`.
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        base_qs = super().get_queryset()
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return base_qs.none()
        return base_qs.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TaxonViewSet(OwnedModelViewSet):
    queryset = Taxon.objects.all()
    serializer_class = TaxonSerializer
    filterset_fields = ["scientific_name", "cultivar", "clone_code"]
    search_fields = ["scientific_name", "cultivar", "clone_code"]
    ordering_fields = ["scientific_name", "cultivar", "created_at", "updated_at"]
    ordering = ["scientific_name", "cultivar"]


class PlantMaterialViewSet(OwnedModelViewSet):
    queryset = PlantMaterial.objects.select_related("taxon").all()
    serializer_class = PlantMaterialSerializer
    filterset_fields = ["taxon", "material_type", "lot_code"]
    search_fields = [
        "lot_code",
        "taxon__scientific_name",
        "taxon__cultivar",
        "taxon__clone_code",
    ]
    ordering_fields = ["created_at", "updated_at", "material_type"]
    ordering = ["-created_at"]


class PropagationBatchViewSet(OwnedModelViewSet):
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


class PlantViewSet(OwnedModelViewSet):
    queryset = Plant.objects.select_related("taxon", "batch").all()
    serializer_class = PlantSerializer
    filterset_fields = ["taxon", "batch", "status", "acquired_on"]
    search_fields = ["taxon__scientific_name", "taxon__cultivar", "taxon__clone_code"]
    ordering_fields = ["created_at", "updated_at", "acquired_on", "quantity", "status"]
    ordering = ["-created_at"]


class EventViewSet(OwnedModelViewSet):
    queryset = Event.objects.select_related("batch", "plant").all()
    serializer_class = EventSerializer
    filterset_fields = ["batch", "plant", "event_type", "happened_at"]
    search_fields = ["notes"]
    ordering_fields = ["happened_at", "created_at", "updated_at", "event_type"]
    ordering = ["-happened_at", "-created_at"]
