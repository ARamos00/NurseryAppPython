from __future__ import annotations

import csv
import io

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from nursery.models import (
    Taxon,
    PlantMaterial,
    MaterialType,
    PropagationBatch,
    PropagationMethod,
    Plant,
    Event,
    EventType,
)


class LimitsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

    @override_settings(MAX_REQUEST_BYTES=100)
    def test_request_size_limit_413(self):
        # Create a payload bigger than 100 bytes
        payload = {"scientific_name": "A" * 120}
        r = self.client.post("/api/taxa/", payload, format="json")
        self.assertEqual(r.status_code, 413, r.content)
        self.assertIn("request_too_large", r.data.get("code"))

    @override_settings(MAX_IMPORT_BYTES=100)
    def test_import_size_limit_413(self):
        # Compose a small CSV slightly above 100 bytes
        csv_text = "scientific_name\n" + ("X" * 120) + "\n"
        f = io.BytesIO(csv_text.encode("utf-8"))
        r = self.client.post("/api/imports/taxa/?dry_run=1", data={"file": ("t.csv", f, "text/csv")}, format="multipart")
        self.assertEqual(r.status_code, 413, r.content)

    @override_settings(EXPORT_MAX_ROWS=1)
    def test_export_row_cap_applied_json_and_csv(self):
        # Seed minimal domain to produce events
        taxon = Taxon.objects.create(user=self.user, scientific_name="Capulus testus")
        mat = PlantMaterial.objects.create(user=self.user, taxon=taxon, material_type=MaterialType.SEED, lot_code="LOT")
        batch = PropagationBatch.objects.create(user=self.user, material=mat, method=PropagationMethod.SEED_SOWING, quantity_started=3)
        plant = Plant.objects.create(user=self.user, taxon=taxon, batch=batch, quantity=1)

        Event.objects.create(user=self.user, batch=batch, event_type=EventType.SOW, quantity_delta=3)
        Event.objects.create(user=self.user, plant=plant, event_type=EventType.NOTE, notes="n1")
        Event.objects.create(user=self.user, plant=plant, event_type=EventType.NOTE, notes="n2")

        # JSON export limited to 1
        r_json = self.client.get("/api/events/export/?format=json")
        self.assertEqual(r_json.status_code, 200, r_json.content)
        self.assertEqual(len(r_json.data), 1)
        self.assertEqual(r_json["X-Export-Total"], "3")
        self.assertEqual(r_json["X-Export-Limit"], "1")
        self.assertEqual(r_json["X-Export-Truncated"], "true")

        # CSV export limited to 1
        r_csv = self.client.get("/api/events/export/?format=csv")
        self.assertEqual(r_csv.status_code, 200, r_csv.content)
        content = r_csv.content.decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(r_csv["X-Export-Total"], "3")
        self.assertEqual(r_csv["X-Export-Limit"], "1")
        self.assertEqual(r_csv["X-Export-Truncated"], "true")

    @override_settings(IMPORT_MAX_ROWS=1)
    def test_import_row_cap_truncates(self):
        # Two rows; cap is 1 -> only first should be processed
        csv_text = "scientific_name\nRowOne\nRowTwo\n"
        f = io.BytesIO(csv_text.encode("utf-8"))
        r = self.client.post("/api/imports/taxa/?dry_run=0", data={"file": ("t.csv", f, "text/csv")}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["rows_ok"] + r.data["rows_failed"], 1)
