"""
Authentication, tenancy isolation, CSRF, and serializer validation tests.

What these tests verify
-----------------------
- **Auth required**: SessionAuthentication + IsAuthenticated returns 403 for
  unauthenticated API access.
- **Ownership on create**: Server ignores a client-supplied `user` field and
  assigns ownership from `request.user`.
- **Per-user isolation**: Objects created by one user are invisible to others.
- **CSRF enforcement**: With `enforce_csrf_checks=True`, unsafe methods require a
  valid CSRF cookie + header pair (403 without; 201 with).
- **Event serializer validation**:
  * XOR invariant: exactly one of `batch` XOR `plant` must be set.
  * Ownership: target object must belong to the authenticated user.

Notes
-----
- Tests use the real APIClient to exercise auth/session middleware and DRF view
  plumbing; assertions focus on *security boundaries* and *invariants* rather
  than model shapes.
"""

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
)


class ApiAuthAndOwnershipTests(APITestCase):
    """Authentication, tenant isolation, CSRF, and XOR validation behaviors."""

    def setUp(self):
        """Create two users and a plain APIClient (no CSRF enforcement by default)."""
        self.user_a = User.objects.create_user(username="alice", password="pass12345")
        self.user_b = User.objects.create_user(username="bob", password="pass12345")
        self.client = APIClient()

    def test_auth_required_list_taxa_unauthenticated_403(self):
        """Unauthenticated list access is forbidden (403)."""
        # SessionAuthentication + IsAuthenticated -> 403 when unauthenticated
        resp = self.client.get("/api/taxa/")
        self.assertEqual(resp.status_code, 403)

    def test_create_taxon_sets_owner(self):
        """
        Creating a taxon sets `user` to the authenticated user, regardless of any
        client-supplied value in the payload (server-side ownership).
        """
        self.client.login(username="alice", password="pass12345")
        payload = {
            "scientific_name": "Acer palmatum",
            "cultivar": "",
            "clone_code": "",
            "user": 999,  # read-only; ignored
        }
        resp = self.client.post("/api/taxa/", payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        taxon_id = resp.data["id"]

        # Owner is alice
        detail = self.client.get(f"/api/taxa/{taxon_id}/")
        self.assertEqual(detail.status_code, 200)
        t = Taxon.objects.get(pk=taxon_id)
        self.assertEqual(t.user_id, self.user_a.id)

    def test_per_user_isolation(self):
        """Data created by Alice is not visible to Bob (404 on retrieve, empty list)."""
        # Alice creates a taxon
        self.client.login(username="alice", password="pass12345")
        resp = self.client.post(
            "/api/taxa/",
            {"scientific_name": "Pinus thunbergii", "cultivar": "", "clone_code": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        taxon_id = resp.data["id"]
        self.client.logout()

        # Bob cannot see or retrieve Alice's object
        self.client.login(username="bob", password="pass12345")
        list_resp = self.client.get("/api/taxa/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.data["count"], 0)

        detail = self.client.get(f"/api/taxa/{taxon_id}/")
        self.assertEqual(detail.status_code, 404)

    def test_csrf_required_when_enforced(self):
        """
        With `enforce_csrf_checks=True`, SessionAuthentication requires CSRF for
        unsafe methods (POST/PUT/PATCH/DELETE).
        """
        # WHY: enable Django's CSRF checks in the client to simulate real browser behavior.
        client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(username="alice", password="pass12345"))

        # POST without CSRF -> 403
        resp = client.post(
            "/api/taxa/",
            {"scientific_name": "Quercus robur", "cultivar": "", "clone_code": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

        # Obtain a valid CSRF token via a GET that sets the CSRF cookie
        _ = client.get("/admin/login/")
        csrftoken = client.cookies.get(settings.CSRF_COOKIE_NAME).value
        self.assertTrue(len(csrftoken) >= 32)

        # POST with matching cookie + header -> 201
        resp_ok = client.post(
            "/api/taxa/",
            {"scientific_name": "Quercus robur", "cultivar": "", "clone_code": ""},
            format="json",
            HTTP_X_CSRFTOKEN=csrftoken,
        )
        self.assertEqual(resp_ok.status_code, 201, resp_ok.data)

    def test_event_serializer_validation_xor_and_ownership(self):
        """
        Event serializer enforces XOR target (batch XOR plant) and ownership.

        Cases:
            - both batch and plant -> 400
            - cross-owner target -> 400
            - valid event with batch only -> 201
        """
        # Alice logs in and owns the created resources
        self.client.login(username="alice", password="pass12345")

        t = Taxon.objects.create(user=self.user_a, scientific_name="Acer palmatum", cultivar="", clone_code="")
        m = PlantMaterial.objects.create(user=self.user_a, taxon=t, material_type=MaterialType.SEED, lot_code="A1")
        b = PropagationBatch.objects.create(
            user=self.user_a,
            material=m,
            method=PropagationMethod.SEED_SOWING,
            status=BatchStatus.STARTED,
            started_on=timezone.now().date(),
            quantity_started=12,
        )
        p = Plant.objects.create(
            user=self.user_a,
            taxon=t,
            batch=b,
            status=PlantStatus.ACTIVE,
            quantity=4,
            acquired_on=timezone.now().date(),
        )

        # Bob's batch (cross-owner)
        t_bob = Taxon.objects.create(user=self.user_b, scientific_name="Betula pendula", cultivar="", clone_code="")
        m_bob = PlantMaterial.objects.create(user=self.user_b, taxon=t_bob, material_type=MaterialType.CUTTING)
        b_bob = PropagationBatch.objects.create(
            user=self.user_b,
            material=m_bob,
            method=PropagationMethod.CUTTING_ROOTING,
            status=BatchStatus.STARTED,
            started_on=timezone.now().date(),
            quantity_started=3,
        )

        # both batch and plant -> 400
        r1 = self.client.post(
            "/api/events/",
            {
                "batch": b.id,
                "plant": p.id,
                "event_type": "NOTE",
                "happened_at": timezone.now().isoformat(),
                "notes": "invalid",
            },
            format="json",
        )
        self.assertEqual(r1.status_code, 400)

        # cross-owner batch -> 400
        r2 = self.client.post(
            "/api/events/",
            {
                "batch": b_bob.id,
                "event_type": "NOTE",
                "happened_at": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(r2.status_code, 400)

        # valid event with batch only -> 201
        r3 = self.client.post(
            "/api/events/",
            {
                "batch": b.id,
                "event_type": "SOW",
                "happened_at": timezone.now().isoformat(),
                "quantity_delta": 5,
                "notes": "Started",
            },
            format="json",
        )
        self.assertEqual(r3.status_code, 201, r3.data)
