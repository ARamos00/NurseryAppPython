from __future__ import annotations

"""
Bulk operations and export tests.

What these tests verify
-----------------------
- **Bulk status update** (`/api/plants/bulk/status/`):
  * Updates the status of multiple plants in one request.
  * Emits corresponding `Event` rows (e.g., `SELL`) for each updated plant.
  * Accepts an idempotency key to make the bulk action safe to retry.

- **Events export** (`/api/events/export/`):
  * CSV variant returns `text/csv` and includes a `target_type` column.
  * JSON variant returns an array of serialized events.

- **Label revocation on terminal status**:
  * When a plant transitions to a terminal status (e.g., SOLD), any attached
    active label token is revoked and detached from the label.

Notes
-----
- Tests authenticate as a real user to exercise owner-scoped querysets and
  permission checks.
- Minimal domain graph is created in `setUp()` to keep assertions focused.
"""

import csv
import io

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
    PlantStatus,
    Event,
    EventType,
    Label,
    LabelToken,
)
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


class BulkAndExportTests(TestCase):
    """End-to-end assertions for bulk plant updates, events export, and label revocation."""

    def setUp(self):
        """Create a user and a minimal Taxon → Material(SEED) → Batch → Plants chain."""
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Quercus robur")
        self.material = PlantMaterial.objects.create(
            user=self.user, taxon=self.taxon, material_type=MaterialType.SEED, lot_code="LOT-EXP"
        )
        self.batch = PropagationBatch.objects.create(
            user=self.user,
            material=self.material,
            method=PropagationMethod.SEED_SOWING,
            quantity_started=12,
        )
        self.p1 = Plant.objects.create(user=self.user, taxon=self.taxon, batch=self.batch, quantity=3)
        self.p2 = Plant.objects.create(user=self.user, taxon=self.taxon, batch=self.batch, quantity=5)

    def test_bulk_status_updates_and_events(self):
        """
        Bulk status endpoint updates multiple plants and records SELL events.

        Also verifies that idempotency is supported via `HTTP_IDEMPOTENCY_KEY`;
        (we do not re-post in this test—the server must still accept the header).
        """
        resp = self.client.post(
            "/api/plants/bulk/status/",
            {"ids": [self.p1.id, self.p2.id], "status": PlantStatus.SOLD, "notes": "Sold batch"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="bulk-1",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(set(resp.data["updated_ids"]), {self.p1.id, self.p2.id})
        self.assertEqual(resp.data["count_updated"], 2)

        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.assertEqual(self.p1.status, PlantStatus.SOLD)
        self.assertEqual(self.p2.status, PlantStatus.SOLD)

        # Events created (one per updated plant)
        evs = Event.objects.filter(user=self.user, event_type=EventType.SELL)
        self.assertEqual(evs.count(), 2)

    def test_events_export_csv_and_json(self):
        """Events export supports CSV (with headers) and JSON formats."""
        # Create a couple of events to export
        Event.objects.create(user=self.user, batch=self.batch, event_type=EventType.SOW, quantity_delta=12)
        Event.objects.create(user=self.user, plant=self.p1, event_type=EventType.NOTE, notes="Check")

        # CSV
        r_csv = self.client.get("/api/events/export/?format=csv")
        self.assertEqual(r_csv.status_code, 200)
        self.assertTrue(r_csv["Content-Type"].startswith("text/csv"))

        content = r_csv.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 2)
        # Export includes a 'target_type' column (batch|plant)
        self.assertIn("target_type", rows[0])

        # JSON
        r_json = self.client.get("/api/events/export/?format=json")
        self.assertEqual(r_json.status_code, 200)
        self.assertIsInstance(r_json.data, list)
        self.assertGreaterEqual(len(r_json.data), 2)

    def test_label_revoked_on_terminal_status(self):
        """
        Setting a plant to a terminal status revokes and detaches any active label token.
        """
        # Attach a label with an active token to p1 (raw token is never stored—hash/prefix only).
        ct = ContentType.objects.get_for_model(Plant)
        label = Label.objects.create(user=self.user, content_type=ct, object_id=self.p1.id)
        token = LabelToken.objects.create(
            label=label,
            token_hash="deadbeef" * 8,  # fake hash
            prefix="deadbeefdead",
        )
        label.active_token = token
        label.save(update_fields=["active_token"])

        # Bulk set SOLD (terminal)
        resp = self.client.post(
            "/api/plants/bulk/status/",
            {"ids": [self.p1.id], "status": PlantStatus.SOLD},
            format="json",
            HTTP_IDEMPOTENCY_KEY="bulk-2",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        label.refresh_from_db()
        token.refresh_from_db()
        self.assertIsNone(label.active_token)
        self.assertIsNotNone(token.revoked_at)
