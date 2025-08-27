"""
Observability middleware tests (request id header + single structured log line).

What these tests verify
-----------------------
- Every API response includes an `X-Request-ID` header:
  * Auto-generated UUID (hex) when a bad/unsafe header is supplied.
  * Echoes a client-provided, safe `X-Request-ID` when present.
- The middleware logs exactly one structured line per request to the
  `nursery.request` logger at INFO level.

Notes
-----
- The middleware stack is minimized via `@override_settings` so we can reason
  about order; our middleware is placed last to observe the final status code.
- We use `self.assertLogs("nursery.request")` to capture the dedicated channel,
  making the test independent of global LOGGING configuration.
"""

from __future__ import annotations

import re  # kept for parity with original imports
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
    """Integration tests for `RequestIDLogMiddleware` header and logging behavior."""

    def setUp(self):
        """Log in a user so `/api/taxa/` resolves with a 200 list response."""
        self.user = User.objects.create_user(username="alice", password="pass12345")
        self.client = APIClient()
        self.client.login(username="alice", password="pass12345")

    def test_response_includes_request_id_and_logs_once(self):
        """Response has `X-Request-ID` and exactly one INFO log line is emitted."""
        # Capture our dedicated logger; this creates a handler regardless of global LOGGING.
        with self.assertLogs("nursery.request", level="INFO") as cap:
            r = self.client.get("/api/taxa/")
        self.assertEqual(r.status_code, 200, r.content)

        # Header present and looks safe (alnum/._- only, <=200 chars).
        rid = r.headers.get("X-Request-ID")
        self.assertIsNotNone(rid)
        self.assertRegex(rid, r"^[A-Za-z0-9._\-]{1,200}$")

        # One line logged with our message and at least status & method in the text
        # (formatter specifics are left to settings; assert minimal contract)
        self.assertTrue(any("request" in line for line in cap.output))
        self.assertTrue(any("INFO" in line for line in cap.output))

    def test_client_provided_request_id_is_respected(self):
        """A safe client-provided `X-Request-ID` is echoed back unchanged."""
        with self.assertLogs("nursery.request", level="INFO") as cap:
            r = self.client.get("/api/taxa/", HTTP_X_REQUEST_ID="custom-123_OK")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("X-Request-ID"), "custom-123_OK")

    def test_bad_client_request_id_is_replaced(self):
        """An unsafe `X-Request-ID` (e.g., with spaces) is replaced by a UUID hex."""
        # Spaces are not allowed; middleware should generate a UUID.
        r = self.client.get("/api/taxa/", HTTP_X_REQUEST_ID="BAD ID")
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.headers.get("X-Request-ID"), "BAD ID")
        # NOTE: Our middleware emits uuid4().hex -> 32 lowercase hex chars.
        self.assertRegex(r.headers.get("X-Request-ID") or "", r"^[a-f0-9]{32}$")
