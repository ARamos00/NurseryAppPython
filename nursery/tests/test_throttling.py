"""
Throttling tests for burst-y traffic patterns.

What these tests verify
-----------------------
- User (authenticated) burst throttle: applying a small rate to a ViewSet
  causes the 4th POST within the window to return HTTP 429.
- Anonymous burst throttle: temporarily allowing anonymous access with a small
  anon rate causes the 3rd GET within the window to return HTTP 429.

Notes
-----
- We patch `TaxonViewSet.throttle_classes` (and permissions for the anon tests)
  at runtime and restore originals with `addCleanup` to avoid cross-tests bleed.
- The tests focus on DRF's throttle integration; underlying view behavior
  remains unchanged and is not under tests here.
"""

from django.core.cache import cache
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIClient, APITestCase

from accounts.models import User
from core.permissions import IsOwner  # imported by the module under tests; not used directly
from core.throttling import UserBurstThrottle, AnonBurstThrottle
from nursery.api import TaxonViewSet


class ThrottlingTests(APITestCase):
    """Burst throttle behavior for authenticated and anonymous callers."""

    def setUp(self):
        # Ensure a clean throttle state for each tests case.
        cache.clear()
        self.client = APIClient()
        self.alice = User.objects.create_user(username="alice", password="pass12345")

    def test_user_throttle_overflow(self):
        """
        Apply a very small user throttle to the TaxonViewSet and prove
        the 4th POST within a minute returns 429.
        """
        # Patch view throttle classes for this tests only.
        orig_throttle = getattr(TaxonViewSet, "throttle_classes", [])
        TaxonViewSet.throttle_classes = [UserBurstThrottle]
        self.addCleanup(setattr, TaxonViewSet, "throttle_classes", orig_throttle)

        # Keep original permissions (IsAuthenticated + IsOwner) from OwnedModelViewSet.
        self.client.login(username="alice", password="pass12345")

        # 3 creates succeed within the window.
        for i in range(3):
            resp = self.client.post(
                "/api/taxa/",
                {"scientific_name": f"Throttle Species {i}", "cultivar": "", "clone_code": ""},
                format="json",
            )
            self.assertEqual(resp.status_code, 201, resp.data)

        # 4th within the window should hit the throttle.
        resp4 = self.client.post(
            "/api/taxa/",
            {"scientific_name": "Throttle Species 3", "cultivar": "", "clone_code": ""},
            format="json",
        )
        self.assertEqual(resp4.status_code, 429, resp4.content)

    def test_anon_throttle_overflow(self):
        """
        Allow anonymous access temporarily and prove anon throttle (2/min)
        returns 429 on the 3rd request.
        """
        # Patch to allow anonymous & set a tiny anon throttle.
        orig_perms = getattr(TaxonViewSet, "permission_classes", [])
        orig_throttle = getattr(TaxonViewSet, "throttle_classes", [])
        TaxonViewSet.permission_classes = [AllowAny]
        TaxonViewSet.throttle_classes = [AnonBurstThrottle]
        self.addCleanup(setattr, TaxonViewSet, "permission_classes", orig_perms)
        self.addCleanup(setattr, TaxonViewSet, "throttle_classes", orig_throttle)

        # Anonymous GET list (owned queryset returns empty, but that's fine for throttling).
        r1 = self.client.get("/api/taxa/")
        r2 = self.client.get("/api/taxa/")
        r3 = self.client.get("/api/taxa/")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r3.status_code, 429)
