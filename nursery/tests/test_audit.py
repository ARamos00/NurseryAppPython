"""
Audit trail API tests: creation, update, and soft-delete visibility.

What these tests verify
-----------------------
- API writes emit audit entries with action codes:
  * `create` on POST (e.g., creating a Taxon),
  * `update` on PATCH (e.g., editing a Plant),
  * `delete` when a Plant is **archived** (soft-delete).
- The audit listing endpoint returns a collection with change diffs whose values
  are two-element lists `[old, new]`.
- Server-side filtering by `model` and `action` works as expected.

Notes
-----
- Tests authenticate as a real user to exercise owner-scoped querysets.
- Soft-delete (`archive`) is recorded as a `delete` action to keep semantics
  aligned with hard deletes in the audit log.
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
    AuditLog,
    AuditAction,
)


class AuditLogApiTests(TestCase):
    """End-to-end assertions for audit entries emitted by API writes."""

    def setUp(self):
        """
        Create a user and a minimal Taxon → Material(SEED) → Batch → Plant chain.

        WHY:
            We need concrete domain objects to exercise update/archive flows that
            produce audit entries tied to real model instances.
        """
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Quercus robur")
        self.material = PlantMaterial.objects.create(
            user=self.user, taxon=self.taxon, material_type=MaterialType.SEED, lot_code="LOT-AUD"
        )
        self.batch = PropagationBatch.objects.create(
            user=self.user,
            material=self.material,
            method=PropagationMethod.SEED_SOWING,
            quantity_started=5,
        )
        self.plant = Plant.objects.create(user=self.user, taxon=self.taxon, batch=self.batch, quantity=2)

    def test_create_update_delete_emit_audit(self):
        """
        Creating, updating, and archiving objects emit `create`, `update`, `delete`.
        """
        # Create via API to ensure request context integration in the audit layer
        r_create = self.client.post(
            "/api/taxa/",
            {"scientific_name": "Acer palmatum", "cultivar": "", "clone_code": ""},
            format="json",
        )
        self.assertEqual(r_create.status_code, 201, r_create.content)
        taxon_id = r_create.data["id"]
        self.assertIsInstance(taxon_id, int)

        # Update via API (PATCH)
        r_update = self.client.patch(f"/api/plants/{self.plant.id}/", {"notes": "trimmed"}, format="json")
        self.assertIn(r_update.status_code, (200, 202, 204), r_update.content)

        # Soft-delete via API (archive replaces DELETE) -> should log as "delete"
        r_archive = self.client.post(f"/api/plants/{self.plant.id}/archive/", {}, format="json")
        self.assertEqual(r_archive.status_code, 200, r_archive.content)

        # Fetch audit logs (pagination may or may not be enabled in settings)
        r_logs = self.client.get("/api/audit/")
        self.assertEqual(r_logs.status_code, 200, r_logs.content)
        # NOTE: Support both list and paginated responses to keep tests resilient.
        items = r_logs.data.get("results") or r_logs.data
        self.assertGreaterEqual(len(items), 3)

        # Ensure actions present (archive recorded as "delete")
        actions = {item["action"] for item in items}
        self.assertTrue({"create", "update", "delete"} <= actions)

        # Spot-check one diff structure: expect two-element [old, new] lists
        upd = next((i for i in items if i["action"] == "update"), None)
        self.assertIsNotNone(upd)
        self.assertIn("changes", upd)
        self.assertTrue(any(isinstance(v, list) and len(v) == 2 for v in upd["changes"].values()))

    def test_filter_by_model_and_action(self):
        """
        Filtering by `model=plant&action=update` returns only matching entries.
        """
        # Produce an update so there is something to filter
        self.client.patch(f"/api/plants/{self.plant.id}/", {"notes": "x"}, format="json")

        r = self.client.get("/api/audit/?model=plant&action=update")
        self.assertEqual(r.status_code, 200, r.content)
        items = r.data.get("results") or r.data
        self.assertTrue(all(i["action"] == "update" for i in items))
        self.assertTrue(all(i["model"] == "plant" for i in items))
