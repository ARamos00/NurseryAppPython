"""
Modular API package for Nursery.

Exports:
- CRUD ViewSets (viewsets.py)
- Wizard endpoints (wizard_seed.py)
"""

from .viewsets import (
    OwnedModelViewSet,
    TaxonViewSet,
    PlantMaterialViewSet,
    PropagationBatchViewSet,
    PlantViewSet,
    EventViewSet,
)
from .wizard_seed import WizardSeedViewSet

__all__ = [
    # CRUD
    "OwnedModelViewSet",
    "TaxonViewSet",
    "PlantMaterialViewSet",
    "PropagationBatchViewSet",
    "PlantViewSet",
    "EventViewSet",
    # Wizard
    "WizardSeedViewSet",
]
