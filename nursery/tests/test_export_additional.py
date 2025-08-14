from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
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


class EventsExportAdditionalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", password="pw")
        self.client = APIClient()
        self.client.login(username="u1", password="pw")

        taxon = Taxon.objects.create(user=self.user, scientific_name="Quercus exportus")
        mat = PlantMaterial.objects.create(user=self.user, taxon=taxon, material_type=MaterialType.SEED, lot_code="LOT-X")
        batch = PropagationBatch.objects.create(
            user=self.user, material=mat, method=PropagationMethod.SEED_SOWING, quantity_started=10
        )
        plant = Plant.objects.create(user=self.user, taxon=taxon, batch=batch, quantity=2)
        Event.objects.create(user=self.user, batch=batch, event_type=EventType.SOW, quantity_delta=10)
        Event.objects.create(user=self.user, plant=plant, event_type=EventType.NOTE, notes="ok")

    def test_csv_via_accept_header(self):
        url = reverse("event-export")
        r = self.client.get(url, HTTP_ACCEPT="text/csv")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r["Content-Type"].startswith("text/csv"))

    def test_invalid_format_falls_back_to_csv(self):
        url = reverse("event-export")
        r = self.client.get(url + "?format=xyz")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r["Content-Type"].startswith("text/csv"))
