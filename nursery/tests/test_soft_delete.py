from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from nursery.models import (
    Taxon,
    PlantMaterial,
    MaterialType,
    PropagationBatch,
    PropagationMethod,
    Plant,
)


class SoftDeleteArchiveTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="arch", password="pw")
        self.client = APIClient()
        self.client.login(username="arch", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Acer palmatum", cultivar="")
        self.material = PlantMaterial.objects.create(
            user=self.user, taxon=self.taxon, material_type=MaterialType.SEED, lot_code="LOTX"
        )
        self.batch = PropagationBatch.objects.create(
            user=self.user,
            material=self.material,
            method=PropagationMethod.SEED_SOWING,
            quantity_started=10,
        )
        self.plant = Plant.objects.create(
            user=self.user,
            taxon=self.taxon,
            batch=self.batch,
            quantity=3,
        )

    def _create_label(self, kind: str, obj_id: int) -> str:
        r = self.client.post(
            "/api/labels/",
            {"target": {"type": kind, "id": obj_id}},
            format="json",
        )
        assert r.status_code in (200, 201), r.content
        return r.data["token"]

    def test_archive_batch_hides_from_lists_and_invalidates_public_label(self):
        token = self._create_label("batch", self.batch.id)
        pub_ok = self.client.get(f"/p/{token}/")
        self.assertEqual(pub_ok.status_code, 200, pub_ok.content)

        # Archive
        r = self.client.post(f"/api/batches/{self.batch.id}/archive/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["archived"])

        # Public label stops resolving
        pub_404 = self.client.get(f"/p/{token}/")
        self.assertEqual(pub_404.status_code, 404)

        # List excludes archived
        lst = self.client.get("/api/batches/")
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(lst.data["count"], 0)

        # Retrieve archived -> 404
        det = self.client.get(f"/api/batches/{self.batch.id}/")
        self.assertEqual(det.status_code, 404)

    def test_archive_plant_hides_from_lists_and_invalidates_public_label(self):
        token = self._create_label("plant", self.plant.id)
        pub_ok = self.client.get(f"/p/{token}/")
        self.assertEqual(pub_ok.status_code, 200, pub_ok.content)

        # Archive
        r = self.client.post(f"/api/plants/{self.plant.id}/archive/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["archived"])

        # Public label stops resolving
        pub_404 = self.client.get(f"/p/{token}/")
        self.assertEqual(pub_404.status_code, 404)

        # List excludes archived
        lst = self.client.get("/api/plants/")
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(lst.data["count"], 0)

        # Retrieve archived -> 404
        det = self.client.get(f"/api/plants/{self.plant.id}/")
        self.assertEqual(det.status_code, 404)

    def test_hard_delete_disallowed_for_plants_and_batches(self):
        d1 = self.client.delete(f"/api/plants/{self.plant.id}/")
        self.assertEqual(d1.status_code, 405, d1.content)
        d2 = self.client.delete(f"/api/batches/{self.batch.id}/")
        self.assertEqual(d2.status_code, 405, d2.content)
