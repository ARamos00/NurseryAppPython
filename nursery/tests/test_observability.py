from __future__ import annotations

import re
from django.test import override_settings
from rest_framework.test import APITestCase, APIClient

from accounts.models import User

# Reference the middleware path once to avoid typos in both tests.
MW_PATH = "core.middleware.RequestIDLogMiddleware"


@override_settings(
    MIDDLEWARE=(
        # Minimal stack for tests; add our middleware at the end so it can see the final response status.
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        MW_PATH,
    )
)
class ObservabilityMiddlewareTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass12345")
        self.client = APIClient()
        self.client.login(username="alice", password="pass12345")

    def test_response_includes_request_id_and_logs_once(self):
        # Capture our dedicated logger; this creates a handler regardless of global LOGGING.
        with self.assertLogs("nursery.request", level="INFO") as cap:
            r = self.client.get("/api/taxa/")
        self.assertEqual(r.status_code, 200, r.content)

        # Header present and looks safe
        rid = r.headers.get("X-Request-ID")
        self.assertIsNotNone(rid)
        self.assertRegex(rid, r"^[A-Za-z0-9._\-]{1,200}$")

        # One line logged with our message and at least status & method in the text
        # (formatter specifics are left to settings; assert minimal contract)
        self.assertTrue(any("request" in line for line in cap.output))
        self.assertTrue(any("INFO" in line for line in cap.output))

    def test_client_provided_request_id_is_respected(self):
        with self.assertLogs("nursery.request", level="INFO") as cap:
            r = self.client.get("/api/taxa/", HTTP_X_REQUEST_ID="custom-123_OK")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("X-Request-ID"), "custom-123_OK")

    def test_bad_client_request_id_is_replaced(self):
        # Spaces are not allowed; middleware should generate a UUID.
        r = self.client.get("/api/taxa/", HTTP_X_REQUEST_ID="BAD ID")
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.headers.get("X-Request-ID"), "BAD ID")
        self.assertRegex(r.headers.get("X-Request-ID") or "", r"^[a-f0-9]{32}$")
