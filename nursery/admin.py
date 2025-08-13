from django.contrib import admin
from django.db.models import QuerySet
from typing import Optional

from .models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    Event,
)


class OwnerScopedAdmin(admin.ModelAdmin):
    """
    Limits queryset/choices to request.user for non-superusers and auto-sets user on save.
    """
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request) -> QuerySet:
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Limit FK choices to the current user's records
        if not request.user.is_superuser and db_field.name in {"taxon", "material", "batch", "plant"}:
            Model = db_field.remote_field.model
            kwargs.setdefault("queryset", Model.objects.filter(user=request.user))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, "user_id", None):
            obj.user = request.user
        super().save_model(request, obj, form, change)


@admin.register(Taxon)
class TaxonAdmin(OwnerScopedAdmin):
    list_display = ("scientific_name", "cultivar", "clone_code", "user", "created_at")
    list_filter = ("cultivar",)
    search_fields = ("scientific_name", "cultivar", "clone_code")


@admin.register(PlantMaterial)
class PlantMaterialAdmin(OwnerScopedAdmin):
    list_display = ("material_type", "taxon", "lot_code", "user", "created_at")
    list_filter = ("material_type",)
    search_fields = ("lot_code", "taxon__scientific_name", "taxon__cultivar")
    raw_id_fields = ("taxon",)


class EventInlineForBatch(admin.TabularInline):
    model = Event
    extra = 0
    fk_name = "batch"
    fields = ("event_type", "happened_at", "notes", "quantity_delta")


@admin.register(PropagationBatch)
class PropagationBatchAdmin(OwnerScopedAdmin):
    list_display = (
        "id", "material", "method", "status", "started_on", "quantity_started", "user", "created_at"
    )
    list_filter = ("method", "status", "started_on")
    search_fields = ("material__lot_code", "material__taxon__scientific_name")
    raw_id_fields = ("material",)
    inlines = [EventInlineForBatch]


class EventInlineForPlant(admin.TabularInline):
    model = Event
    extra = 0
    fk_name = "plant"
    fields = ("event_type", "happened_at", "notes", "quantity_delta")


@admin.register(Plant)
class PlantAdmin(OwnerScopedAdmin):
    list_display = ("id", "taxon", "batch", "status", "quantity", "acquired_on", "user", "created_at")
    list_filter = ("status", "acquired_on")
    search_fields = ("taxon__scientific_name", "taxon__cultivar")
    raw_id_fields = ("taxon", "batch")
    inlines = [EventInlineForPlant]


@admin.register(Event)
class EventAdmin(OwnerScopedAdmin):
    list_display = ("id", "event_type", "happened_at", "batch", "plant", "user")
    list_filter = ("event_type", "happened_at")
    search_fields = ("notes",)
    raw_id_fields = ("batch", "plant")
