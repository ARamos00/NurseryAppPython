"""
CSV import API tests: taxa, materials, and plants.

What these tests verify
-----------------------
- **Taxa import**: successful rows are counted and the endpoint is idempotent
  when the same `Idempotency-Key` is replayed.
- **Materials import**: validates FK ownership (`taxon_id` must belong to the
  caller) and choice fields (`material_type`).
- **Plants import (dry run)**: validates data but rolls back writes when
  `?dry_run=1` is used.

Notes
-----
- Tests authenticate as a real user so owner-scoped `.for_user(user)` lookups
  are exercised.
- A small domain chain (Taxon → Material(SEED) → Batch(SEED_SOWING)) is created
  in `setUp()` to support FK references used by the imports.
"""

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
    """
    Build a CSV file-like object (BytesIO) from a list of dict rows.

    - Uses the keys of the first row as the header (stable field order).
    - Encodes as UTF-8 and returns a BytesIO suitable for `multipart/form-data`.

    Args:
        rows (list[dict]): Sequence of CSV rows.

    Returns:
        io.BytesIO: File-like object positioned at start for upload.
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return io.BytesIO(output.getvalue().encode("utf-8"))


class ImportApiTests(TestCase):
    """End-to-end tests for the three CSV import endpoints."""

    def setUp(self):
        """
        Create a user and minimal domain graph for FK references:

        - Taxon (self.taxon)
        - PlantMaterial (SEED) for that taxon
        - PropagationBatch (SEED_SOWING) for that material
        """
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
        """
        Taxa import accepts valid rows and is idempotent with the same key.

        Verifies:
            - rows_ok=2, rows_failed=0 on first POST
            - exact same response is replayed when the same Idempotency-Key is used
        """
        rows = [
            {"scientific_name": "Acer palmatum", "cultivar": "", "clone_code": ""},
            {"scientific_name": "Fagus sylvatica", "cultivar": "Atropunicea", "clone_code": ""},
        ]
        f = _csv_bytes(rows)
        resp = self.client.post(
            "/api/imports/taxa/?dry_run=0",
            data={"file": ("taxa.csv", f, "text/csv")},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="imp-1",  # safe retry semantics
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["rows_ok"], 2)
        self.assertEqual(resp.data["rows_failed"], 0)

        # Replay idempotent: same key -> server should return the cached first response
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
        """
        Materials import validates both foreign keys and choices.

        Case 1 (OK): valid `taxon_id` and `material_type=SEED` -> 1 success.
        Case 2 (Invalid): non-existent taxon and invalid material_type -> 1 failure.
        """
        # ok row
        ok_rows = [
            {"taxon_id": str(self.taxon.id), "material_type": "SEED", "lot_code": "LOT-A", "notes": ""},
        ]
        f_ok = _csv_bytes(ok_rows)
        r_ok = self.client.post("/api/imports/materials/", data={"file": ("m.csv", f_ok, "text/csv")}, format="multipart")
        self.assertEqual(r_ok.status_code, 200)
        self.assertEqual(r_ok.data["rows_ok"], 1)
        we = r_ok.data["rows_failed"]
        self.assertEqual(we, 0, f"expected 0 failed rows but got {we}")

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
        """
        Plants import honors `dry_run=1`: counts successes but writes nothing.

        Also verifies case-insensitive label normalization for `status`.
        """
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

        # Ensure nothing was created due to dry-run
        self.assertEqual(Plant.objects.filter(user=self.user, notes="Imported").count(), 0)
