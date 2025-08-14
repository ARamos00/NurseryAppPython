from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from nursery.models import (
    Taxon,
    PlantMaterial,
    MaterialType,
    PropagationBatch,
    PropagationMethod,
    BatchStatus,
    Event,
    EventType,
    Plant,
)


def etag_for(obj) -> str:
    return f'W/"{int(obj.updated_at.timestamp())}"'


class HarvestOpsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Pinus ponderosa")
        self.material = PlantMaterial.objects.create(
            user=self.user, taxon=self.taxon, material_type=MaterialType.SEED, lot_code="LOT-A"
        )
        self.batch = PropagationBatch.objects.create(
            user=self.user,
            material=self.material,
            method=PropagationMethod.SEED_SOWING,
            quantity_started=10,
        )

    def test_harvest_then_cull_then_complete(self):
        # Initial availability
        self.assertEqual(self.batch.available_quantity(), 10)

        # HARVEST 4
        etag = etag_for(self.batch)
        r1 = self.client.post(
            f"/api/batches/{self.batch.id}/harvest/",
            {"quantity": 4, "notes": "potted 4"},
            format="json",
            HTTP_IF_MATCH=etag,
            HTTP_IDEMPOTENCY_KEY="harv-1",
        )
        self.assertEqual(r1.status_code, 201, r1.content)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.available_quantity(), 6)

        plant_id = r1.data["plant_id"]
        plant = Plant.objects.get(pk=plant_id)
        self.assertEqual(plant.quantity, 4)
        self.assertEqual(plant.batch_id, self.batch.id)

        # Verify events
        be = Event.objects.filter(batch=self.batch, event_type=EventType.POT_UP).first()
        self.assertIsNotNone(be)
        self.assertEqual(be.quantity_delta, -4)

        # CULL 2
        etag2 = etag_for(self.batch)
        r2 = self.client.post(
            f"/api/batches/{self.batch.id}/cull/",
            {"quantity": 2, "notes": "losses"},
            format="json",
            HTTP_IF_MATCH=etag2,
            HTTP_IDEMPOTENCY_KEY="cull-1",
        )
        self.assertEqual(r2.status_code, 200, r2.content)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.available_quantity(), 4)

        # COMPLETE should fail without force because remaining=4
        etag3 = etag_for(self.batch)
        r3 = self.client.post(
            f"/api/batches/{self.batch.id}/complete/",
            {"force": False},
            format="json",
            HTTP_IF_MATCH=etag3,
            HTTP_IDEMPOTENCY_KEY="comp-0",
        )
        self.assertEqual(r3.status_code, 400)

        # COMPLETE with force
        etag4 = etag_for(self.batch)
        r4 = self.client.post(
            f"/api/batches/{self.batch.id}/complete/",
            {"force": True},
            format="json",
            HTTP_IF_MATCH=etag4,
            HTTP_IDEMPOTENCY_KEY="comp-1",
        )
        self.assertEqual(r4.status_code, 200, r4.content)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, BatchStatus.COMPLETED)

    def test_if_match_precondition(self):
        # Send stale ETag -> expect 412
        stale = 'W/"1"'
        r = self.client.post(
            f"/api/batches/{self.batch.id}/cull/",
            {"quantity": 1},
            format="json",
            HTTP_IF_MATCH=stale,
        )
        self.assertEqual(r.status_code, 412)
