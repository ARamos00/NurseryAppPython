"""
Django admin registrations for Nursery domain models.

Scope & intent
--------------
- Back-office only: this admin is intended for staff operators. It surfaces
  essential fields for browsing and troubleshooting but avoids exposing any
  sensitive secrets.
- Privacy: label/token administration shows **only** non-sensitive attributes.
  Raw label tokens are never stored in the database (only hashed + prefix), so
  nothing here can leak the one-time token value.

Usability notes
---------------
- `list_display` highlights identifiers, relationships, and tenant (`user`).
- `search_fields` traverse common relations (e.g., `taxon__scientific_name`)
  for quick lookup.
- `list_filter` offers status/method filters where appropriate.
- `date_hierarchy` on `LabelVisit` helps slice analytics by day/month.

Security
--------
- Treat admin as an internal tool. Do not grant access to non-staff users.
"""

from __future__ import annotations

from django.contrib import admin

from .models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    Event,
    Label,
    LabelToken,
    LabelVisit,
)


@admin.register(Taxon)
class TaxonAdmin(admin.ModelAdmin):
    """Back-office listing for `Taxon` rows with light tenant/context columns."""
    list_display = ("id", "scientific_name", "cultivar", "clone_code", "user", "created_at")
    search_fields = ("scientific_name", "cultivar", "clone_code")
    list_filter = ("user",)


@admin.register(PlantMaterial)
class PlantMaterialAdmin(admin.ModelAdmin):
    """Admin for materials, emphasizing lot traceability and type."""
    list_display = ("id", "taxon", "material_type", "lot_code", "user", "created_at")
    search_fields = ("lot_code", "taxon__scientific_name", "taxon__cultivar", "taxon__clone_code")
    list_filter = ("material_type", "user")


@admin.register(PropagationBatch)
class PropagationBatchAdmin(admin.ModelAdmin):
    """Admin for batches; shows method, status, and starting quantity/date."""
    list_display = ("id", "material", "method", "status", "quantity_started", "started_on", "user")
    list_filter = ("status", "method", "user")
    search_fields = ("material__lot_code", "material__taxon__scientific_name")


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    """Admin for plants; focuses on status/quantity with batch/taxon context."""
    list_display = ("id", "taxon", "batch", "status", "quantity", "user")
    list_filter = ("status", "user")
    search_fields = ("taxon__scientific_name", "batch__material__lot_code")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """Audit-friendly view of events with type, target, timestamp, and owner."""
    list_display = ("id", "event_type", "batch", "plant", "happened_at", "user")
    list_filter = ("event_type", "user")


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    """
    Admin for labels. Tokens are managed in `LabelToken`; this view shows only
    relationships and the currently attached `active_token` (if any).
    """
    list_display = ("id", "user", "content_type", "object_id", "active_token", "created_at")
    list_filter = ("user", "content_type")


@admin.register(LabelToken)
class LabelTokenAdmin(admin.ModelAdmin):
    """
    Admin for label tokens.

    NOTE:
        Only the non-sensitive `prefix` and revocation metadata are displayed.
        Raw tokens are never persisted; this preserves privacy even in admin.
    """
    list_display = ("id", "label", "prefix", "revoked_at", "created_at")
    list_filter = ("label",)


@admin.register(LabelVisit)
class LabelVisitAdmin(admin.ModelAdmin):
    """Read-only style listing of public label hits for lightweight analytics."""
    list_display = ("id", "label", "token", "requested_at", "ip_address", "user")
    list_filter = ("label", "user")
    search_fields = ("ip_address", "user_agent", "referrer")
    # WHY: quickly navigate high-volume visit logs by date.
    date_hierarchy = "requested_at"
