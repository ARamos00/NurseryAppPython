"""
Tests for the inventory and production report endpoints.

What these tests verify
-----------------------
- **Inventory report** (`/api/reports/inventory/`):
  * JSON payload contains a `rows` array and a `totals` object.
  * Totals are correct for the seeded data (plants count and summed quantity).
  * CSV variant responds with `text/csv` and includes expected headers.

- **Production report** (`/api/reports/production/`):
  * JSON payload contains `summary_by_type` with per-event-type counts/quantities.
  * Optional `group_by=day` timeseries is present and shaped as expected.
  * CSV variant responds with `text/csv`.

Notes
-----
- Tests log in as a real user to exercise owner-scoped querysets.
- Minimal, deterministic fixtures are built in `setUp()` so assertions remain
  stable and easy to reason about.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta

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
    Plant,
    PlantStatus,
    Event,
    EventType,
)


class ReportsApiTests(TestCase):
    """End-to-end assertions for inventory and production report APIs."""

    def setUp(self):
        """
        Seed a minimal dataset:

        - Two taxa (t1, t2).
        - One material (SEED) and a batch for t1.
        - Three plants:
            p1: t1/batch, quantity=3, ACTIVE
            p2: t1/batch, quantity=2, SOLD
            p3: t2/no-batch, quantity=5, ACTIVE
          => totals: plants=3, quantity=10
        - Production events (relative to `now`):
            SOW(+10) on batch b1 (5 days ago)
            NOTE on plant p1 (3 days ago)
            SELL(-3) on plant p1 (1 day ago)
        """
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        # Data
        self.t1 = Taxon.objects.create(user=self.user, scientific_name="Quercus robur")
        self.t2 = Taxon.objects.create(user=self.user, scientific_name="Acer palmatum")

        m1 = PlantMaterial.objects.create(user=self.user, taxon=self.t1, material_type=MaterialType.SEED, lot_code="L1")
        b1 = PropagationBatch.objects.create(
            user=self.user, material=m1, method=PropagationMethod.SEED_SOWING, quantity_started=10
        )

        # Plants inventory
        self.p1 = Plant.objects.create(user=self.user, taxon=self.t1, batch=b1, quantity=3, status=PlantStatus.ACTIVE)
        self.p2 = Plant.objects.create(user=self.user, taxon=self.t1, batch=b1, quantity=2, status=PlantStatus.SOLD)
        self.p3 = Plant.objects.create(user=self.user, taxon=self.t2, batch=None, quantity=5, status=PlantStatus.ACTIVE)

        # Events for production report
        now = timezone.now()
        Event.objects.create(user=self.user, batch=b1, event_type=EventType.SOW, quantity_delta=10, happened_at=now - timedelta(days=5))
        Event.objects.create(user=self.user, plant=self.p1, event_type=EventType.NOTE, happened_at=now - timedelta(days=3))
        Event.objects.create(user=self.user, plant=self.p1, event_type=EventType.SELL, quantity_delta=-3, happened_at=now - timedelta(days=1))

    def test_inventory_json_and_csv(self):
        """Inventory report returns JSON with totals and a CSV variant with headers."""
        r = self.client.get("/api/reports/inventory/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("rows", r.data)
        self.assertIn("totals", r.data)
        rows = r.data["rows"]
        self.assertGreaterEqual(len(rows), 2)
        totals = r.data["totals"]
        self.assertEqual(totals["plants"], 3)
        self.assertEqual(totals["quantity"], 10)

        # CSV
        rc = self.client.get("/api/reports/inventory/?format=csv")
        self.assertEqual(rc.status_code, 200, rc.content)
        self.assertTrue(rc["Content-Type"].startswith("text/csv"))
        content = rc.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        cs_rows = list(reader)
        self.assertGreaterEqual(len(cs_rows), 2)
        # WHY: 'status' helps spreadsheet consumers slice inventory by state.
        self.assertIn("status", reader.fieldnames)

    def test_production_summary_and_timeseries(self):
        """Production report exposes a per-type summary, daily timeseries, and CSV."""
        r = self.client.get("/api/reports/production/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("summary_by_type", r.data)
        by_type = {row["event_type"]: row for row in r.data["summary_by_type"]}
        # at least SOW and SELL present
        self.assertIn(EventType.SOW, by_type)
        self.assertIn(EventType.SELL, by_type)
        self.assertEqual(by_type[EventType.SOW]["quantity"], 10)
        self.assertEqual(by_type[EventType.SELL]["events"], 1)

        # timeseries (day)
        rt = self.client.get("/api/reports/production/?group_by=day")
        self.assertEqual(rt.status_code, 200, rt.content)
        self.assertIn("timeseries", rt.data)
        self.assertGreaterEqual(len(rt.data["timeseries"]), 2)
        sample = rt.data["timeseries"][0]
        self.assertIn("date", sample)
        self.assertIn("event_type", sample)

        # CSV
        rc = self.client.get("/api/reports/production/?format=csv")
        self.assertEqual(rc.status_code, 200)
        self.assertTrue(rc["Content-Type"].startswith("text/csv"))
