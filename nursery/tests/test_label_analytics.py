from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.contenttypes.models import ContentType

from nursery.models import Taxon, Plant, Label, LabelToken, LabelVisit

class LabelAnalyticsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="pw")
        self.client = APIClient()
        self.client.login(username="u", password="pw")

        self.taxon = Taxon.objects.create(user=self.user, scientific_name="Quercus robur")
        self.plant = Plant.objects.create(user=self.user, taxon=self.taxon, quantity=1)

        # create a label + active token
        ct = ContentType.objects.get_for_model(Plant)
        self.label = Label.objects.create(user=self.user, content_type=ct, object_id=self.plant.id)
        self.token = LabelToken.objects.create(label=self.label, token_hash="ab"*32, prefix="abcdef123456")
        self.label.active_token = self.token
        self.label.save(update_fields=["active_token"])

    def test_public_view_records_visit_and_stats_endpoint(self):
        # simulate a public scan (no auth required)
        pub = self.client.get(f"/p/{self.token.prefix}/", HTTP_USER_AGENT="UA", HTTP_REFERER="https://example.com/x")
        self.assertEqual(pub.status_code, 200)

        # a LabelVisit should exist, tied to owner
        self.assertEqual(LabelVisit.objects.filter(label=self.label, user=self.user).count(), 1)

        # owner stats endpoint
        r = self.client.get(f"/api/labels/{self.label.id}/stats/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["label_id"], self.label.id)
        self.assertEqual(r.data["total_visits"], 1)
        self.assertGreaterEqual(r.data["last_7d"], 1)
        self.assertGreaterEqual(r.data["last_30d"], 1)
