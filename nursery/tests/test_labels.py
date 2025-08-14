from __future__ import annotations

import hashlib

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from nursery.models import (
    Taxon,
    PlantMaterial,
    MaterialType,
    PropagationBatch,
    PropagationMethod,
)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LabelFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Acer palmatum", cultivar="")
        self.material = PlantMaterial.objects.create(
            user=self.user, taxon=self.taxon, material_type=MaterialType.SEED, lot_code="LOT1"
        )
        self.batch = PropagationBatch.objects.create(
            user=self.user, material=self.material, method=PropagationMethod.SEED_SOWING, quantity_started=10
        )

    def test_create_rotate_revoke_label_and_public_page(self):
        # Create label for batch
        resp = self.client.post(
            "/api/labels/",
            {"target": {"type": "batch", "id": self.batch.id}},
            format="json",
            HTTP_IDEMPOTENCY_KEY="it-1",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        token = resp.data["token"]
        public_url = resp.data["public_url"]
        self.assertTrue(public_url.endswith(f"/p/{token}/"))

        # Public page works
        pub = self.client.get(public_url)
        self.assertEqual(pub.status_code, 200, pub.content)

        # Old token becomes invalid after rotate
        rid = resp.data["id"]
        r2 = self.client.post(f"/api/labels/{rid}/rotate/", {}, format="json", HTTP_IDEMPOTENCY_KEY="it-2")
        self.assertEqual(r2.status_code, 200, r2.content)
        new_token = r2.data["token"]

        old = self.client.get(public_url)
        self.assertEqual(old.status_code, 404)
        new = self.client.get(f"/p/{new_token}/")
        self.assertEqual(new.status_code, 200)

        # Revoke
        r3 = self.client.post(f"/api/labels/{rid}/revoke/", {}, format="json")
        self.assertEqual(r3.status_code, 200)
        revoked = self.client.get(f"/p/{new_token}/")
        self.assertEqual(revoked.status_code, 404)
