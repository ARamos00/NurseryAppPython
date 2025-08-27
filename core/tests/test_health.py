"""Tests for the lightweight /health/ endpoint.

Contract
--------
- 200 when DB connectivity check passes and response includes:
  {"app": "nursery-tracker", "db": "ok", "time": "..."}.
- 503 when the DB check raises; payload includes {"db": "down", "error": "..."}.

These tests assert the endpoint remains minimal and dependable for probes.
"""

from unittest.mock import patch

from django.test import TestCase


class HealthEndpointTests(TestCase):
    """Validate happy path and error path for /health/."""

    def test_health_ok(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("db"), "ok")
        self.assertIn("time", data)
        self.assertEqual(data.get("app"), "nursery-tracker")

    def test_health_db_down(self):
        # Simulate DB connectivity failure to assert 503 behavior and error key.
        with patch("django.db.connection.ensure_connection", side_effect=Exception("boom")):
            resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertEqual(data.get("db"), "down")
        self.assertIn("error", data)
