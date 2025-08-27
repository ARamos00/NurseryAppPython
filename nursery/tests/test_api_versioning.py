from __future__ import annotations

"""
Smoke tests for the `/api/v1/` mirror.

What these tests verify
-----------------------
- Basic liveness of the **v1** mount points that mirror the primary `/api/`
  endpoints without duplicating logic.
- Pagination shape for list endpoints under v1 (PageNumberPagination contract).
- v1 label creation returns a one-time `token` and a `public_url` containing `/p/`.
- v1 events export (JSON) responds with HTTP 200.

Notes
-----
- These are intentionally lightweight to catch routing or schema wiring mistakes
  without re-testing business logic already covered by non-v1 tests.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from nursery.models import Taxon, Plant


class ApiVersioningSmokeTests(TestCase):
    """Liveness checks for `/api/v1/` routes and minimal response shapes."""

    def setUp(self):
        """Authenticate a test user so owner-scoped querysets return results."""
        User = get_user_model()
        self.user = User.objects.create_user(username="v1", password="pw")
        self.client = APIClient()
        self.client.login(username="v1", password="pw")

    def test_v1_taxa_list_smoke(self):
        """
        v1 taxa list returns PageNumberPagination shape with at least 2 items.
        """
        # Seed a couple taxa
        Taxon.objects.create(user=self.user, scientific_name="Acer palmatum")
        Taxon.objects.create(user=self.user, scientific_name="Quercus robur")

        r = self.client.get("/api/v1/taxa/")
        self.assertEqual(r.status_code, 200, r.content)
        # PageNumberPagination shape
        self.assertIn("results", r.data)
        self.assertGreaterEqual(r.data["count"], 2)

    def test_v1_labels_create_smoke(self):
        """
        v1 label creation returns a one-time `token` and a `public_url` with `/p/`.
        """
        # Minimal plant target so we can create a label
        t = Taxon.objects.create(user=self.user, scientific_name="Pinus sylvestris")
        p = Plant.objects.create(user=self.user, taxon=t, quantity=1)

        r = self.client.post(
            "/api/v1/labels/",
            {"target": {"type": "plant", "id": p.id}},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("token", r.data)
        self.assertIn("public_url", r.data)
        self.assertIn("/p/", r.data["public_url"])

    def test_v1_events_export_json_smoke(self):
        """
        v1 events export endpoint responds with 200 for JSON format.
        """
        r = self.client.get("/api/v1/events/export/?format=json")
        self.assertEqual(r.status_code, 200, r.content)
