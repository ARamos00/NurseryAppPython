from __future__ import annotations

"""
Limits and caps tests (request size, import size, export row limits, import row cap).

What these tests verify
-----------------------
- **Request size limit**: Oversized JSON POST returns HTTP 413 with a stable error code.
- **Import size limit**: Oversized CSV upload returns HTTP 413.
- **Export row cap**: Events export applies a row limit for both JSON and CSV and
  annotates responses with `X-Export-Total`, `X-Export-Limit`, and `X-Export-Truncated`.
- **Import row cap**: CSV imports stop processing after the configured number of data rows.

Notes
-----
- Each test uses `@override_settings` to clamp limits/sizes tightly so assertions are fast.
- Tests log in as a real user to exercise owner-scoped querysets.
"""

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
    """Integration tests for request/import size guards and export/import row caps."""

    def setUp(self):
        """Create a user and authenticate APIClient to hit owner-scoped endpoints."""
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

    @override_settings(MAX_REQUEST_BYTES=100)
    def test_request_size_limit_413(self):
        """
        Payloads larger than `MAX_REQUEST_BYTES` return HTTP 413 with an error code.

        WHY:
            Middleware enforces an early cut-off for oversized requests to avoid
            unnecessary JSON parsing and DB work.
        """
        # Create a payload bigger than 100 bytes
        payload = {"scientific_name": "A" * 120}
        r = self.client.post("/api/taxa/", payload, format="json")
        self.assertEqual(r.status_code, 413, r.content)
        self.assertIn("request_too_large", r.data.get("code"))

    @override_settings(MAX_IMPORT_BYTES=100)
    def test_import_size_limit_413(self):
        """
        CSV uploads larger than `MAX_IMPORT_BYTES` are rejected with HTTP 413.
        """
        # Compose a small CSV slightly above 100 bytes
        csv_text = "scientific_name\n" + ("X" * 120) + "\n"
        f = io.BytesIO(csv_text.encode("utf-8"))
        r = self.client.post(
            "/api/imports/taxa/?dry_run=1",
            data={"file": ("t.csv", f, "text/csv")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 413, r.content)

    @override_settings(EXPORT_MAX_ROWS=1)
    def test_export_row_cap_applied_json_and_csv(self):
        """
        Events export applies row caps and returns explanatory headers (JSON & CSV).
        """
        # Seed minimal domain to produce events
        taxon = Taxon.objects.create(user=self.user, scientific_name="Capulus testus")
        mat = PlantMaterial.objects.create(
            user=self.user, taxon=taxon, material_type=MaterialType.SEED, lot_code="LOT"
        )
        batch = PropagationBatch.objects.create(
            user=self.user, material=mat, method=PropagationMethod.SEED_SOWING, quantity_started=3
        )
        plant = Plant.objects.create(user=self.user, taxon=taxon, batch=batch, quantity=1)

        Event.objects.create(user=self.user, batch=batch, event_type=EventType.SOW, quantity_delta=3)
        Event.objects.create(user=self.user, plant=plant, event_type=EventType.NOTE, notes="n1")
        Event.objects.create(user=self.user, plant=plant, event_type=EventType.NOTE, notes="n2")

        # JSON export limited to 1
        r_json = self.client.get("/api/events/export/?format=json")
        self.assertEqual(r_json.status_code, 200, r_json.content)
        self.assertEqual(len(r_json.data), 1)
        # NOTE: headers communicate total vs. returned and whether truncation occurred.
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
        """
        Import row cap stops after the first data row; totals reflect processed rows.
        """
        # Two rows; cap is 1 -> only first should be processed
        csv_text = "scientific_name\nRowOne\nRowTwo\n"
        f = io.BytesIO(csv_text.encode("utf-8"))
        r = self.client.post(
            "/api/imports/taxa/?dry_run=0",
            data={"file": ("t.csv", f, "text/csv")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["rows_ok"] + r.data["rows_failed"], 1)
