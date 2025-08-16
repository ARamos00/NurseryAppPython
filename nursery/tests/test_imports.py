from __future__ import annotations

import io
import csv

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
)


def _csv_bytes(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return io.BytesIO(output.getvalue().encode("utf-8"))


class ImportApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Quercus robur")
        self.material = PlantMaterial.objects.create(
            user=self.user, taxon=self.taxon, material_type=MaterialType.SEED, lot_code="LOT-IMP"
        )
        self.batch = PropagationBatch.objects.create(
            user=self.user, material=self.material, method=PropagationMethod.SEED_SOWING, quantity_started=10
        )

    def test_import_taxa_success_and_idempotent(self):
        rows = [
            {"scientific_name": "Acer palmatum", "cultivar": "", "clone_code": ""},
            {"scientific_name": "Fagus sylvatica", "cultivar": "Atropunicea", "clone_code": ""},
        ]
        f = _csv_bytes(rows)
        resp = self.client.post(
            "/api/imports/taxa/?dry_run=0",
            data={"file": ("taxa.csv", f, "text/csv")},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="imp-1",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["rows_ok"], 2)
        self.assertEqual(resp.data["rows_failed"], 0)

        # Replay idempotent
        f2 = _csv_bytes(rows)
        resp2 = self.client.post(
            "/api/imports/taxa/?dry_run=0",
            data={"file": ("taxa.csv", f2, "text/csv")},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="imp-1",
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data, resp.data)

    def test_import_materials_validations(self):
        # ok row
        ok_rows = [
            {"taxon_id": str(self.taxon.id), "material_type": "SEED", "lot_code": "LOT-A", "notes": ""},
        ]
        f_ok = _csv_bytes(ok_rows)
        r_ok = self.client.post("/api/imports/materials/", data={"file": ("m.csv", f_ok, "text/csv")}, format="multipart")
        self.assertEqual(r_ok.status_code, 200)
        self.assertEqual(r_ok.data["rows_ok"], 1)
        self.assertEqual(r_ok.data["rows_failed"], 0)

        # bad FK + bad choice
        bad_rows = [
            {"taxon_id": "999", "material_type": "NOPE", "lot_code": "LOT-X", "notes": ""},
        ]
        f_bad = _csv_bytes(bad_rows)
        r_bad = self.client.post("/api/imports/materials/", data={"file": ("m2.csv", f_bad, "text/csv")}, format="multipart")
        self.assertEqual(r_bad.status_code, 200)
        self.assertEqual(r_bad.data["rows_ok"], 0)
        self.assertEqual(r_bad.data["rows_failed"], 1)
        self.assertGreaterEqual(len(r_bad.data["errors"]), 1)

    def test_import_plants_dry_run(self):
        rows = [
            {
                "taxon_id": str(self.taxon.id),
                "batch_id": str(self.batch.id),
                "status": "active",  # case-insensitive label allowed
                "quantity": "3",
                "acquired_on": "2025-08-01",
                "notes": "Imported",
            }
        ]
        f = _csv_bytes(rows)
        r = self.client.post("/api/imports/plants/?dry_run=1", data={"file": ("p.csv", f, "text/csv")}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["rows_ok"], 1)
        self.assertEqual(r.data["rows_failed"], 0)

        # Ensure nothing was created
        self.assertEqual(Plant.objects.filter(user=self.user, notes="Imported").count(), 0)
