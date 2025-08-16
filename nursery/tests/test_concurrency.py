from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from nursery.models import Taxon, Plant, PropagationBatch, PlantMaterial, MaterialType, PropagationMethod


class ConcurrencyETagTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Quercus robur")
        self.material = PlantMaterial.objects.create(
            user=self.user, taxon=self.taxon, material_type=MaterialType.SEED, lot_code="L-001"
        )
        self.batch = PropagationBatch.objects.create(
            user=self.user, material=self.material, method=PropagationMethod.SEED_SOWING, quantity_started=3
        )
        self.plant = Plant.objects.create(user=self.user, taxon=self.taxon, batch=self.batch, quantity=1)

    def test_retrieve_sets_etag_and_allows_update_with_match(self):
        # Retrieve to get ETag
        r = self.client.get(f"/api/plants/{self.plant.id}/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("ETag", r)
        etag = r["ETag"]

        # Update with If-Match -> OK
        r2 = self.client.patch(
            f"/api/plants/{self.plant.id}/",
            {"notes": "updated"},
            format="json",
            HTTP_IF_MATCH=etag,
        )
        self.assertIn(r2.status_code, (200, 202, 204), r2.content)

        # Retrieve again: ETag must change
        r3 = self.client.get(f"/api/plants/{self.plant.id}/")
        self.assertEqual(r3.status_code, 200)
        self.assertIn("ETag", r3)
        self.assertNotEqual(etag, r3["ETag"])

    def test_stale_if_match_returns_412(self):
        # Get a valid ETag
        r = self.client.get(f"/api/plants/{self.plant.id}/")
        etag = r["ETag"]

        # Mutate object to make the ETag stale
        Plant.objects.filter(pk=self.plant.id).update(notes="other change")

        # Try to update with stale tag -> 412
        r2 = self.client.patch(
            f"/api/plants/{self.plant.id}/",
            {"notes": "client change"},
            format="json",
            HTTP_IF_MATCH=etag,
        )
        self.assertEqual(r2.status_code, 412, r2.content)
        self.assertEqual(r2.data.get("code"), "stale_resource")
        self.assertIn("expected_etag", r2.data)
