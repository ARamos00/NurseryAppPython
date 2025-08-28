from __future__ import annotations

from copy import deepcopy

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

User = get_user_model()


class AuthApiTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alice", password="pass12345", email="a@example.com")
        # Enforce CSRF checks in tests to mirror real behavior
        self.client = APIClient(enforce_csrf_checks=True)

    def _prime_csrf(self):
        r = self.client.get("/api/auth/csrf/")
        self.assertEqual(r.status_code, 204)
        self.assertIn("csrftoken", self.client.cookies)
        token = r.headers.get("X-CSRFToken")
        self.assertTrue(token)
        # attach header for subsequent unsafe requests
        self.client.credentials(HTTP_X_CSRFTOKEN=token)

    def test_csrf_sets_cookie_and_header(self):
        self._prime_csrf()

    def test_login_invalid_returns_400(self):
        self._prime_csrf()
        r = self.client.post("/api/auth/login/", {"username": "alice", "password": "wrong"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json().get("code"), "invalid_credentials")

    def test_login_success_me_logout_flow(self):
        self._prime_csrf()
        r = self.client.post("/api/auth/login/", {"username": "alice", "password": "pass12345"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["username"], "alice")

        r_me = self.client.get("/api/auth/me/")
        self.assertEqual(r_me.status_code, 200)
        self.assertEqual(r_me.json()["username"], "alice")

        r_logout = self.client.post("/api/auth/logout/")
        self.assertEqual(r_logout.status_code, 204)

        r_me_after = self.client.get("/api/auth/me/")
        self.assertEqual(r_me_after.status_code, 401)

    def test_me_unauthenticated_401(self):
        r = self.client.get("/api/auth/me/")
        self.assertEqual(r.status_code, 401)

    def test_login_throttled_429(self):
        # Lower the auth-login rate for this test to trigger quickly.
        rf = deepcopy(settings.REST_FRAMEWORK)
        rates = dict(rf.get("DEFAULT_THROTTLE_RATES", {}))
        rates["auth-login"] = "2/min"
        rf["DEFAULT_THROTTLE_RATES"] = rates

        with override_settings(REST_FRAMEWORK=rf):
            client = APIClient(enforce_csrf_checks=True)
            # prime csrf
            r = client.get("/api/auth/csrf/")
            token = r.headers.get("X-CSRFToken")
            client.credentials(HTTP_X_CSRFTOKEN=token)

            # two invalid attempts allowed
            for _ in range(2):
                self.assertEqual(
                    client.post("/api/auth/login/", {"username": "alice", "password": "bad"}).status_code,
                    400,
                )
            # third should be throttled
            r3 = client.post("/api/auth/login/", {"username": "alice", "password": "bad"})
            self.assertEqual(r3.status_code, 429)
