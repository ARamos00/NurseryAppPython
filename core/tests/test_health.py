from unittest.mock import patch

from django.test import TestCase


class HealthEndpointTests(TestCase):
    def test_health_ok(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("db"), "ok")
        self.assertIn("time", data)
        self.assertEqual(data.get("app"), "nursery-tracker")

    def test_health_db_down(self):
        with patch("django.db.connection.ensure_connection", side_effect=Exception("boom")):
            resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertEqual(data.get("db"), "down")
        self.assertIn("error", data)
