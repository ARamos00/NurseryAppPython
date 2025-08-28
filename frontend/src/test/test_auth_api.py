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
        self.client = APIClient(enforce_csrf_checks=True)

    def _prime_csrf(self):
        r = self.client.get("/api/auth/csrf/")
        self.assertEqual(r.status_code, 204)
        self.assertIn("csrftoken", self.client.cookies)
        token = r.headers.get("X-CSRFToken")
        self.assertTrue(token)
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
        rf = deepcopy(settings.REST_FRAMEWORK)
        rates = dict(rf.get("DEFAULT_THROTTLE_RATES", {}))
        rates["auth-login"] = "2/min"
        rf["DEFAULT_THROTTLE_RATES"] = rates

        with override_settings(REST_FRAMEWORK=rf):
            client = APIClient(enforce_csrf_checks=True)
            r = client.get("/api/auth/csrf/")
            token = r.headers.get("X-CSRFToken")
            client.credentials(HTTP_X_CSRFTOKEN=token)

            for _ in range(2):
                self.assertEqual(
                    client.post("/api/auth/login/", {"username": "alice", "password": "bad"}).status_code,
                    400,
                )
            r3 = client.post("/api/auth/login/", {"username": "alice", "password": "bad"})
            self.assertEqual(r3.status_code, 429)


class RegistrationApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient(enforce_csrf_checks=True)

    def _prime_csrf(self):
        r = self.client.get("/api/auth/csrf/")
        token = r.headers.get("X-CSRFToken")
        self.client.credentials(HTTP_X_CSRFTOKEN=token)

    @override_settings(ENABLE_REGISTRATION=False)
    def test_register_disabled_returns_403(self):
        self._prime_csrf()
        r = self.client.post("/api/auth/register/", {
            "username": "bob",
            "email": "b@example.com",
            "password1": "Str0ngPass!23",
            "password2": "Str0ngPass!23",
        })
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("code"), "registration_disabled")

    @override_settings(ENABLE_REGISTRATION=True)
    def test_register_requires_email_and_unique(self):
        self._prime_csrf()
        # Missing email
        r = self.client.post("/api/auth/register/", {
            "username": "charlie",
            "password1": "Str0ngPass!23",
            "password2": "Str0ngPass!23",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.json())

        # Duplicate email
        User.objects.create_user(username="existing", email="dup@example.com", password="pass123456")
        r2 = self.client.post("/api/auth/register/", {
            "username": "charlie2",
            "email": "dup@example.com",
            "password1": "Str0ngPass!23",
            "password2": "Str0ngPass!23",
        }, format="json")
        self.assertEqual(r2.status_code, 400)
        self.assertIn("email", r2.json())

    @override_settings(ENABLE_REGISTRATION=True)
    def test_register_password_mismatch_and_strength(self):
        self._prime_csrf()
        # mismatch
        r = self.client.post("/api/auth/register/", {
            "username": "dave",
            "email": "d@example.com",
            "password1": "Str0ngPass!23",
            "password2": "Str0ngPass!24",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password2", r.json())

        # weak (likely too short / common)
        r2 = self.client.post("/api/auth/register/", {
            "username": "dave2",
            "email": "d2@example.com",
            "password1": "password",
            "password2": "password",
        }, format="json")
        self.assertEqual(r2.status_code, 400)
        self.assertTrue(any("password" in k for k in r2.json().keys()))

    @override_settings(ENABLE_REGISTRATION=True)
    def test_register_success_auto_logs_in(self):
        self._prime_csrf()
        r = self.client.post("/api/auth/register/", {
            "username": "eve",
            "email": "e@example.com",
            "password1": "An0therStr0ng!Pass",
            "password2": "An0therStr0ng!Pass",
        }, format="json")
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["username"], "eve")

        # Should be logged in now
        r_me = self.client.get("/api/auth/me/")
        self.assertEqual(r_me.status_code, 200)
        self.assertEqual(r_me.json()["username"], "eve")

    def test_register_throttled_429(self):
        rf = deepcopy(settings.REST_FRAMEWORK)
        rates = dict(rf.get("DEFAULT_THROTTLE_RATES", {}))
        rates["auth-register"] = "1/min"
        rf["DEFAULT_THROTTLE_RATES"] = rates

        with override_settings(REST_FRAMEWORK=rf, ENABLE_REGISTRATION=True):
            client = APIClient(enforce_csrf_checks=True)
            r = client.get("/api/auth/csrf/")
            token = r.headers.get("X-CSRFToken")
            client.credentials(HTTP_X_CSRFTOKEN=token)

            # First attempt (invalid to be safe)
            self.assertIn(
                client.post("/api/auth/register/", {
                    "username": "eve2",
                    "email": "e2@example.com",
                    "password1": "short",
                    "password2": "short",
                }, format="json").status_code,
                (200, 201, 400),
            )
            # Second immediately should be throttled by scope
            r2 = client.post("/api/auth/register/", {
                "username": "eve3",
                "email": "e3@example.com",
                "password1": "short",
                "password2": "short",
            }, format="json")
            self.assertEqual(r2.status_code, 429)
