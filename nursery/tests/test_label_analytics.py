from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta

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

        # owner stats endpoint (legacy fields preserved)
        r = self.client.get(f"/api/labels/{self.label.id}/stats/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["label_id"], self.label.id)
        self.assertEqual(r.data["total_visits"], 1)
        self.assertGreaterEqual(r.data["last_7d"], 1)
        self.assertGreaterEqual(r.data["last_30d"], 1)

    def test_stats_with_days_returns_series(self):
        """
        New behavior: when ?days=N is provided, include window metadata and a complete per-day series.
        """
        # Seed multiple visits across a small window by adjusting requested_at
        now = timezone.now()
        # Today
        v1 = LabelVisit.objects.create(user=self.user, label=self.label, token=self.token)
        # 2 days ago
        v2 = LabelVisit.objects.create(user=self.user, label=self.label, token=self.token)
        LabelVisit.objects.filter(pk=v2.pk).update(requested_at=now - timedelta(days=2))
        # 4 days ago (outside a 3-day window but inside a 5-day window)
        v3 = LabelVisit.objects.create(user=self.user, label=self.label, token=self.token)
        LabelVisit.objects.filter(pk=v3.pk).update(requested_at=now - timedelta(days=4))

        # Request a 5-day window (inclusive)
        r = self.client.get(f"/api/labels/{self.label.id}/stats/?days=5")
        self.assertEqual(r.status_code, 200, r.content)

        # Window metadata present
        self.assertEqual(r.data["window_days"], 5)
        self.assertIn("start_date", r.data)
        self.assertIn("end_date", r.data)

        # Series covers each day in the window (inclusive)
        series = r.data["series"]
        self.assertEqual(len(series), 5)
        # Ensure keys present and integer counts
        for item in series:
            self.assertIn("date", item)
            self.assertIn("visits", item)
            self.assertIsInstance(item["visits"], int)

        # Sanity: at least one of the days has a non-zero count
        total_series_visits = sum(item["visits"] for item in series)
        # Should be >= number of visits we created (3), allowing for rounding if now's day overlaps
        self.assertGreaterEqual(total_series_visits, 3)
