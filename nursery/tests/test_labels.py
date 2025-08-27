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

        # -- New: public QR image (immutable caching)
        qr = self.client.get(f"/p/{token}/qr.svg")
        self.assertEqual(qr.status_code, 200, qr.content)
        self.assertEqual(qr["Content-Type"], "image/svg+xml; charset=utf-8")
        self.assertIn("immutable", qr["Cache-Control"])

        # -- New: owner QR (no-store) requires proof-of-possession raw token
        rid = resp.data["id"]
        owner_qr = self.client.get(f"/api/labels/{rid}/qr/?token={token}")
        self.assertEqual(owner_qr.status_code, 200, owner_qr.content)
        self.assertEqual(owner_qr["Content-Type"], "image/svg+xml; charset=utf-8")
        self.assertEqual(owner_qr["Cache-Control"], "no-store")

        # Old token becomes invalid for owner QR after rotate; public QR still returns 200
        r2 = self.client.post(f"/api/labels/{rid}/rotate/", {}, format="json", HTTP_IDEMPOTENCY_KEY="it-2")
        self.assertEqual(r2.status_code, 200, r2.content)
        new_token = r2.data["token"]

        # Owner QR should reject old token
        old_owner = self.client.get(f"/api/labels/{rid}/qr/?token={token}")
        self.assertEqual(old_owner.status_code, 403)

        # Public QR remains 200 (it only encodes a URL)
        new_pub_qr = self.client.get(f"/p/{new_token}/qr.svg")
        self.assertEqual(new_pub_qr.status_code, 200)
