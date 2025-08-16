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
    list_display = ("id", "scientific_name", "cultivar", "clone_code", "user", "created_at")
    search_fields = ("scientific_name", "cultivar", "clone_code")
    list_filter = ("user",)

@admin.register(PlantMaterial)
class PlantMaterialAdmin(admin.ModelAdmin):
    list_display = ("id", "taxon", "material_type", "lot_code", "user", "created_at")
    search_fields = ("lot_code", "taxon__scientific_name", "taxon__cultivar", "taxon__clone_code")
    list_filter = ("material_type", "user")

@admin.register(PropagationBatch)
class PropagationBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "material", "method", "status", "quantity_started", "started_on", "user")
    list_filter = ("status", "method", "user")
    search_fields = ("material__lot_code", "material__taxon__scientific_name")

@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ("id", "taxon", "batch", "status", "quantity", "user")
    list_filter = ("status", "user")
    search_fields = ("taxon__scientific_name", "batch__material__lot_code")

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "batch", "plant", "happened_at", "user")
    list_filter = ("event_type", "user")

@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "content_type", "object_id", "active_token", "created_at")
    list_filter = ("user", "content_type")

@admin.register(LabelToken)
class LabelTokenAdmin(admin.ModelAdmin):
    list_display = ("id", "label", "prefix", "revoked_at", "created_at")
    list_filter = ("label",)

@admin.register(LabelVisit)
class LabelVisitAdmin(admin.ModelAdmin):
    list_display = ("id", "label", "token", "requested_at", "ip_address", "user")
    list_filter = ("label", "user")
    search_fields = ("ip_address", "user_agent", "referrer")
    date_hierarchy = "requested_at"
