"""
Tests for webhook delivery worker behavior.

What these tests cover
----------------------
- Successful delivery path: a queued `WebhookDelivery` transitions to `SENT`,
  records a 200 response, and clears `next_attempt_at`.
- Failure + backoff path: network failures trigger backoff scheduling (QUEUED
  with `next_attempt_at` set) until the maximum attempts is reached, at which
  point the delivery is parked as `FAILED` (DLQ).

Notes
-----
- We patch `urlopen` used by the management command to simulate success/failure
  without performing real I/O.
- Settings are overridden per tests to exercise the feature flags and timing.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from nursery.models import WebhookEndpoint, WebhookDelivery, WebhookEventType, WebhookDeliveryStatus


class WebhooksDeliveryTests(TestCase):
    """End-to-end tests for the `deliver_webhooks` management command."""

    def setUp(self):
        # Minimal tenant/user for ownership scoping.
        User = get_user_model()
        self.user = User.objects.create_user(username="hookuser", password="pw")

    @override_settings(WEBHOOKS_DELIVERY_ENABLED=True)
    def test_delivery_success_marks_sent(self):
        """
        A 200 response marks the delivery as SENT and clears scheduling fields.
        """
        ep = WebhookEndpoint.objects.create(
            user=self.user,
            name="ok",
            url="http://example.com/hook",  # NOTE: http is fine in tests; HTTPS is enforced in prod by settings.
            event_types=["*"],
            secret="sekret",
            is_active=True,
        )
        d = WebhookDelivery.objects.create(
            user=self.user,
            endpoint=ep,
            event_type=WebhookEventType.EVENT_CREATED,
            payload={"hello": "world"},
            status=WebhookDeliveryStatus.QUEUED,
        )

        # Fake a successful HTTP response object with the minimal API used by the worker.
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, exc_type, exc, tb): return False
            def read(self): return b"ok"
            def getcode(self): return 200
            def getheaders(self): return [("Content-Type", "application/json")]

        # WHY: Patch the exact import path used by the command for deterministic behavior.
        with mock.patch("nursery.management.commands.deliver_webhooks.urlrequest.urlopen", return_value=_Resp()):
            call_command("deliver_webhooks", limit=10)

        d.refresh_from_db()
        self.assertEqual(d.status, WebhookDeliveryStatus.SENT)
        self.assertEqual(d.attempt_count, 1)
        self.assertEqual(d.response_status, 200)
        self.assertIsNone(d.next_attempt_at)

    @override_settings(
        WEBHOOKS_DELIVERY_ENABLED=True,
        WEBHOOKS_BACKOFF_SCHEDULE="1,1",  # two quick retries for quicker tests
        WEBHOOKS_MAX_ATTEMPTS=2,          # DLQ on the second failure
        WEBHOOKS_DELIVERY_TIMEOUT_SEC=1,
    )
    def test_delivery_backoff_then_dlq(self):
        """
        Network errors schedule backoff, then eventually mark the delivery FAILED.
        """
        ep = WebhookEndpoint.objects.create(
            user=self.user,
            name="fail",
            url="http://example.com/hook",
            event_types=["*"],
            secret="sekret",
            is_active=True,
        )
        d = WebhookDelivery.objects.create(
            user=self.user,
            endpoint=ep,
            event_type=WebhookEventType.EVENT_CREATED,
            payload={},
            status=WebhookDeliveryStatus.QUEUED,
        )

        # Always fail the HTTP call to trigger backoff logic.
        from urllib.error import URLError
        with mock.patch("nursery.management.commands.deliver_webhooks.urlrequest.urlopen", side_effect=URLError("boom")):
            call_command("deliver_webhooks", limit=10)

        d.refresh_from_db()
        # First failure -> scheduled retry
        self.assertEqual(d.status, WebhookDeliveryStatus.QUEUED)  # scheduled for retry
        self.assertEqual(d.attempt_count, 1)
        self.assertIsNotNone(d.next_attempt_at)

        # Force next attempt to be due by moving the clock back.
        d.next_attempt_at = timezone.now() - timezone.timedelta(seconds=5)
        d.save(update_fields=["next_attempt_at"])

        # Second failure reaches max attempts -> DLQ
        with mock.patch("nursery.management.commands.deliver_webhooks.urlrequest.urlopen", side_effect=URLError("boom")):
            call_command("deliver_webhooks", limit=10)

        d.refresh_from_db()
        self.assertEqual(d.status, WebhookDeliveryStatus.FAILED)  # DLQ
        self.assertEqual(d.attempt_count, 2)
        self.assertIsNone(d.next_attempt_at)
