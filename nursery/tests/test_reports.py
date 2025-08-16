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
    def setUp(self):
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
        self.assertIn("status", reader.fieldnames)

    def test_production_summary_and_timeseries(self):
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
