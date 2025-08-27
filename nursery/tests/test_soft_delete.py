"""
Tests for soft-delete/archive behavior and public label invalidation.

What these tests verify
-----------------------
- Archiving a **batch**:
    * Public label page for the batch returns 404 afterward.
    * Default list endpoints exclude archived rows.
    * Direct retrieve of an archived row returns 404.
- Archiving a **plant**: same expectations as batch.
- Hard DELETE on plants/batches is disallowed (405); archive is the supported
  path to hide records while preserving history.

Notes
-----
- Labels expose a **public** page at `/p/<token>/`; these tests create an owner
  label first, then verify the public page status before/after archive.
- The helper `_create_label` uses the owner-facing labels API and returns the
  raw token (shown exactly once at creation/rotation time).
"""

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
    """End-to-end assertions for archive flows and public label invalidation."""

    def setUp(self):
        """Create a user and a minimal Taxon → Material → Batch → Plant chain."""
        User = get_user_model()
        self.user = User.objects.create_user(username="arch", password="pw")
        self.client = APIClient()
        self.client.login(username="arch", password="pw")

        # Domain objects owned by the caller (tenancy: user field set explicitly)
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
        """
        Create an owner label for a target and return the **raw** token string.

        Args:
            kind: "batch" or "plant"
            obj_id: Primary key of the target object.

        Returns:
            Raw token string usable at `/p/<token>/`.

        NOTE:
            The raw token is only returned at creation/rotation time; subsequent
            reads expose prefix/metadata only (privacy by design).
        """
        r = self.client.post(
            "/api/labels/",
            {"target": {"type": kind, "id": obj_id}},
            format="json",
        )
        assert r.status_code in (200, 201), r.content
        return r.data["token"]

    def test_archive_batch_hides_from_lists_and_invalidates_public_label(self):
        """Archiving a batch hides it and 404s the public label page."""
        token = self._create_label("batch", self.batch.id)

        # Public page resolves before archive
        pub_ok = self.client.get(f"/p/{token}/")
        self.assertEqual(pub_ok.status_code, 200, pub_ok.content)

        # Archive action
        r = self.client.post(f"/api/batches/{self.batch.id}/archive/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["archived"])

        # Public label stops resolving after archive
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
        """Archiving a plant hides it and 404s the public label page."""
        token = self._create_label("plant", self.plant.id)

        # Public page resolves before archive
        pub_ok = self.client.get(f"/p/{token}/")
        self.assertEqual(pub_ok.status_code, 200, pub_ok.content)

        # Archive action
        r = self.client.post(f"/api/plants/{self.plant.id}/archive/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["archived"])

        # Public label stops resolving after archive
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
        """Hard DELETE is not supported; use archive instead (expect 405)."""
        d1 = self.client.delete(f"/api/plants/{self.plant.id}/")
        self.assertEqual(d1.status_code, 405, d1.content)
        d2 = self.client.delete(f"/api/batches/{self.batch.id}/")
        self.assertEqual(d2.status_code, 405, d2.content)
