from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from accounts.models import User
from nursery.models import (
    Taxon,
    PlantMaterial,
    MaterialType,
    PropagationBatch,
    PropagationMethod,
    BatchStatus,
    Plant,
    PlantStatus,
    Event,
    EventType,
)


class ApiFiltersOrderingPaginationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass12345")
        self.client = APIClient()
        self.client.login(username="alice", password="pass12345")

        # --- Taxa ---
        self.t_acer_pal = Taxon.objects.create(
            user=self.user, scientific_name="Acer palmatum", cultivar="Seiryu", clone_code=""
        )
        self.t_acer_rub = Taxon.objects.create(
            user=self.user, scientific_name="Acer rubrum", cultivar="October Glory", clone_code=""
        )
        self.t_betula = Taxon.objects.create(
            user=self.user, scientific_name="Betula pendula", cultivar="", clone_code="BP-1"
        )

        # --- Materials ---
        self.m_seed_pal = PlantMaterial.objects.create(
            user=self.user, taxon=self.t_acer_pal, material_type=MaterialType.SEED, lot_code="PAL-SEED-001"
        )
        self.m_cutting_rub = PlantMaterial.objects.create(
            user=self.user, taxon=self.t_acer_rub, material_type=MaterialType.CUTTING, lot_code="RUB-CUT-001"
        )
        self.m_seed_bet = PlantMaterial.objects.create(
            user=self.user, taxon=self.t_betula, material_type=MaterialType.SEED, lot_code="BET-SEED-001"
        )

        # --- Batches ---
        today = timezone.now().date()
        earlier = today.replace(day=max(1, today.day - 7))
        self.b1 = PropagationBatch.objects.create(
            user=self.user,
            material=self.m_seed_pal,
            method=PropagationMethod.SEED_SOWING,
            status=BatchStatus.STARTED,
            started_on=earlier,
            quantity_started=20,
            notes="pal seed"
        )
        self.b2 = PropagationBatch.objects.create(
            user=self.user,
            material=self.m_cutting_rub,
            method=PropagationMethod.CUTTING_ROOTING,
            status=BatchStatus.GERMINATING,
            started_on=today,
            quantity_started=10,
            notes="rub cutting"
        )
        self.b3 = PropagationBatch.objects.create(
            user=self.user,
            material=self.m_seed_bet,
            method=PropagationMethod.SEED_SOWING,
            status=BatchStatus.POTTED,
            started_on=today,
            quantity_started=5,
            notes="bet seed"
        )

        # --- Plants ---
        self.p1 = Plant.objects.create(
            user=self.user,
            taxon=self.t_acer_pal,
            batch=self.b1,
            status=PlantStatus.ACTIVE,
            quantity=3,
            acquired_on=earlier,
        )
        self.p2 = Plant.objects.create(
            user=self.user,
            taxon=self.t_acer_rub,
            batch=self.b2,
            status=PlantStatus.DORMANT,
            quantity=2,
            acquired_on=today,
        )
        self.p3 = Plant.objects.create(
            user=self.user,
            taxon=self.t_betula,
            batch=self.b3,
            status=PlantStatus.SOLD,
            quantity=1,
            acquired_on=today,
        )

        # --- Events (start with 5 items) ---
        now = timezone.now()
        self.e1 = Event.objects.create(
            user=self.user, batch=self.b1, event_type=EventType.SOW, happened_at=now - timezone.timedelta(hours=4)
        )
        self.e2 = Event.objects.create(
            user=self.user, batch=self.b1, event_type=EventType.WATER, happened_at=now - timezone.timedelta(hours=3)
        )
        self.e3 = Event.objects.create(
            user=self.user, batch=self.b1, event_type=EventType.GERMINATE, happened_at=now - timezone.timedelta(hours=2)
        )
        self.e4 = Event.objects.create(
            user=self.user, batch=self.b1, event_type=EventType.POT_UP, happened_at=now - timezone.timedelta(hours=1)
        )
        self.e5 = Event.objects.create(
            user=self.user, batch=self.b1, event_type=EventType.NOTE, happened_at=now
        )

    # -------------------------
    # Taxon: filter / search / order
    # -------------------------
    def test_taxa_filter_search_order(self):
        # filter exact by scientific_name
        r = self.client.get("/api/taxa/", {"scientific_name": "Acer palmatum"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["scientific_name"], "Acer palmatum")

        # search by cultivar
        r = self.client.get("/api/taxa/", {"search": "October"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["cultivar"], "October Glory")

        # order ascending by scientific_name (allowed field)
        r = self.client.get("/api/taxa/", {"ordering": "scientific_name"})
        names = [row["scientific_name"] for row in r.data["results"]]
        self.assertEqual(names, sorted(names))

        # order descending by scientific_name
        r = self.client.get("/api/taxa/", {"ordering": "-scientific_name"})
        names_desc = [row["scientific_name"] for row in r.data["results"]]
        self.assertEqual(names_desc, sorted(names_desc, reverse=True))

    # -------------------------
    # PlantMaterial: filter / search / order
    # -------------------------
    def test_materials_filter_search_order(self):
        # filter by taxon
        r = self.client.get("/api/materials/", {"taxon": self.t_acer_pal.id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["material_type"], MaterialType.SEED)

        # filter by material_type
        r = self.client.get("/api/materials/", {"material_type": MaterialType.CUTTING})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["taxon"], self.t_acer_rub.id)

        # search across related fields (taxon)
        r = self.client.get("/api/materials/", {"search": "pendula"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["taxon"], self.t_betula.id)

        # ordering by an allowed, stable field (material_type)
        r_asc = self.client.get("/api/materials/", {"ordering": "material_type"})
        r_desc = self.client.get("/api/materials/", {"ordering": "-material_type"})
        asc = [row["material_type"] for row in r_asc.data["results"]]
        desc = [row["material_type"] for row in r_desc.data["results"]]
        self.assertEqual(asc, sorted(asc))
        self.assertEqual(desc, sorted(desc, reverse=True))

    # -------------------------
    # PropagationBatch: filter / order / pagination (default PAGE_SIZE)
    # -------------------------
    def test_batches_filter_order_pagination(self):
        # filter by status
        r = self.client.get("/api/batches/", {"status": "STARTED"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["id"], self.b1.id)

        # explicit ordering by allowed field
        r_ordered = self.client.get("/api/batches/", {"ordering": "-started_on"})
        self.assertEqual(r_ordered.status_code, 200)
        started_on_list = [row["started_on"] for row in r_ordered.data["results"]]
        self.assertEqual(started_on_list, sorted(started_on_list, reverse=True))

        # Create enough batches to exceed default PAGE_SIZE (25)
        page_size = settings.REST_FRAMEWORK.get("PAGE_SIZE", 25)
        target_total = max(30, page_size + 5)
        current_total = 3
        for i in range(target_total - current_total):
            PropagationBatch.objects.create(
                user=self.user,
                material=self.m_seed_pal,
                method=PropagationMethod.SEED_SOWING,
                status=BatchStatus.STARTED,
                started_on=timezone.now().date() + timezone.timedelta(days=i + 1),
                quantity_started=10 + i,
            )

        page1 = self.client.get("/api/batches/", {"ordering": "started_on"})
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page1.data["count"], target_total)
        self.assertEqual(len(page1.data["results"]), page_size)
        self.assertIsNotNone(page1.data["next"])

        page2 = self.client.get(page1.data["next"])
        self.assertEqual(page2.status_code, 200)
        # remaining items after page 1
        remaining = target_total - page_size
        self.assertEqual(
            len(page2.data["results"]),
            remaining if remaining < page_size else page_size,
        )

    # -------------------------
    # Plant: filter / order
    # -------------------------
    def test_plants_filter_order(self):
        # filter by status
        r = self.client.get("/api/plants/", {"status": PlantStatus.DORMANT})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["id"], self.p2.id)

        # filter by batch
        r = self.client.get("/api/plants/", {"batch": self.b1.id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["id"], self.p1.id)

        # order by -acquired_on (allowed)
        r = self.client.get("/api/plants/", {"ordering": "-acquired_on"})
        acquired = [row["acquired_on"] for row in r.data["results"]]
        self.assertEqual(acquired, sorted(acquired, reverse=True))

    # -------------------------
    # Event: filter / order / pagination (default PAGE_SIZE)
    # -------------------------
    def test_events_filter_order_pagination(self):
        # filter by event_type
        r = self.client.get("/api/events/", {"event_type": EventType.WATER})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["id"], self.e2.id)

        # filter by batch
        r = self.client.get("/api/events/", {"batch": self.b1.id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 5)

        # explicit ordering by allowed field (ascending)
        r_asc = self.client.get("/api/events/", {"ordering": "happened_at"})
        times = [row["happened_at"] for row in r_asc.data["results"]]
        self.assertEqual(times, sorted(times))

        # Create enough events to exceed default PAGE_SIZE (25)
        page_size = settings.REST_FRAMEWORK.get("PAGE_SIZE", 25)
        target_total = max(30, page_size + 5)
        current_total = 5
        base_time = timezone.now()
        for i in range(target_total - current_total):
            Event.objects.create(
                user=self.user,
                batch=self.b1,
                event_type=EventType.NOTE,
                happened_at=base_time + timezone.timedelta(minutes=i + 1),
                notes=f"note {i}",
            )

        page1 = self.client.get("/api/events/", {"ordering": "happened_at"})
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page1.data["count"], target_total)
        self.assertEqual(len(page1.data["results"]), page_size)
        self.assertIsNotNone(page1.data["next"])

        page2 = self.client.get(page1.data["next"])
        self.assertEqual(page2.status_code, 200)
        remaining = target_total - page_size
        self.assertEqual(
            len(page2.data["results"]),
            remaining if remaining < page_size else page_size,
        )
