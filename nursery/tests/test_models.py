from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from nursery.models import (
    Taxon,
    PlantMaterial,
    MaterialType,
    PropagationBatch,
    PropagationMethod,
    BatchStatus,
    Plant,
    PlantStatus,
    Event,
    EventType,
)


class ModelBasicsTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(username="alice", password="pass12345")
        self.u2 = User.objects.create_user(username="bob", password="pass12345")

    def test_taxon_unique_per_user(self):
        t1 = Taxon.objects.create(
            user=self.u1, scientific_name="Acer palmatum", cultivar="", clone_code=""
        )
        self.assertEqual(str(t1), "Acer palmatum")

        # Same user + same identity -> unique constraint triggers (atomic to avoid broken tx)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Taxon.objects.create(
                    user=self.u1,
                    scientific_name="Acer palmatum",
                    cultivar="",
                    clone_code="",
                )

        # Different user can create the same identity
        t2 = Taxon.objects.create(
            user=self.u2, scientific_name="Acer palmatum", cultivar="", clone_code=""
        )
        self.assertIsNotNone(t2.pk)

    def test_owned_queryset_for_user(self):
        t1 = Taxon.objects.create(
            user=self.u1, scientific_name="Pinus thunbergii", cultivar="", clone_code=""
        )
        Taxon.objects.create(
            user=self.u2, scientific_name="Pinus thunbergii", cultivar="Nishiki", clone_code=""
        )
        qs = Taxon.objects.for_user(self.u1)
        self.assertEqual(list(qs), [t1])

    def test_event_constraints_and_clean(self):
        # Build a small graph for u1
        taxon = Taxon.objects.create(
            user=self.u1, scientific_name="Acer palmatum", cultivar="Seiryu", clone_code=""
        )
        material = PlantMaterial.objects.create(
            user=self.u1, taxon=taxon, material_type=MaterialType.SEED, lot_code="LOT1"
        )
        batch = PropagationBatch.objects.create(
            user=self.u1,
            material=material,
            method=PropagationMethod.SEED_SOWING,
            status=BatchStatus.STARTED,
            started_on=timezone.now().date(),
            quantity_started=10,
        )
        plant = Plant.objects.create(
            user=self.u1,
            taxon=taxon,
            batch=batch,
            status=PlantStatus.ACTIVE,
            quantity=5,
            acquired_on=timezone.now().date(),
        )

        # XOR: both set -> should fail at full_clean()
        ev = Event(
            user=self.u1,
            batch=batch,
            plant=plant,
            event_type=EventType.NOTE,
            happened_at=timezone.now(),
            notes="Invalid both",
        )
        with self.assertRaisesMessage(ValidationError, "Choose either a batch or a plant"):
            ev.full_clean()

        # Owner mismatch should fail at clean()
        other_taxon = Taxon.objects.create(
            user=self.u2, scientific_name="Betula", cultivar="", clone_code=""
        )
        other_material = PlantMaterial.objects.create(
            user=self.u2, taxon=other_taxon, material_type=MaterialType.CUTTING
        )
        other_batch = PropagationBatch.objects.create(
            user=self.u2,
            material=other_material,
            method=PropagationMethod.CUTTING_ROOTING,
            status=BatchStatus.STARTED,
            started_on=timezone.now().date(),
            quantity_started=3,
        )
        ev2 = Event(
            user=self.u1,
            batch=other_batch,  # belongs to u2
            event_type=EventType.NOTE,
            happened_at=timezone.now(),
        )
        with self.assertRaisesMessage(ValidationError, "must match the selected batch owner"):
            ev2.full_clean()

        # Valid: exactly one target set
        ok = Event.objects.create(
            user=self.u1,
            batch=batch,
            event_type=EventType.SOW,
            happened_at=timezone.now(),
            notes="Started",
            quantity_delta=+5,
        )
        self.assertIsNotNone(ok.pk)
