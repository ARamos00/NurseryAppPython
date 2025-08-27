from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from nursery.models import WebhookEndpoint, WebhookDelivery, WebhookEventType, WebhookDeliveryStatus


class WebhooksDeliveryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="hookuser", password="pw")

    @override_settings(WEBHOOKS_DELIVERY_ENABLED=True)
    def test_delivery_success_marks_sent(self):
        ep = WebhookEndpoint.objects.create(
            user=self.user,
            name="ok",
            url="http://example.com/hook",
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

        class _Resp:
            def __enter__(self): return self
            def __exit__(self, exc_type, exc, tb): return False
            def read(self): return b"ok"
            def getcode(self): return 200
            def getheaders(self): return [("Content-Type", "application/json")]

        with mock.patch("nursery.management.commands.deliver_webhooks.urlrequest.urlopen", return_value=_Resp()):
            call_command("deliver_webhooks", limit=10)

        d.refresh_from_db()
        self.assertEqual(d.status, WebhookDeliveryStatus.SENT)
        self.assertEqual(d.attempt_count, 1)
        self.assertEqual(d.response_status, 200)
        self.assertIsNone(d.next_attempt_at)

    @override_settings(
        WEBHOOKS_DELIVERY_ENABLED=True,
        WEBHOOKS_BACKOFF_SCHEDULE="1,1",
        WEBHOOKS_MAX_ATTEMPTS=2,
        WEBHOOKS_DELIVERY_TIMEOUT_SEC=1,
    )
    def test_delivery_backoff_then_dlq(self):
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

        # Always fail
        from urllib.error import URLError
        with mock.patch("nursery.management.commands.deliver_webhooks.urlrequest.urlopen", side_effect=URLError("boom")):
            call_command("deliver_webhooks", limit=10)

        d.refresh_from_db()
        self.assertEqual(d.status, WebhookDeliveryStatus.QUEUED)  # scheduled for retry
        self.assertEqual(d.attempt_count, 1)
        self.assertIsNotNone(d.next_attempt_at)

        # Force next attempt due
        d.next_attempt_at = timezone.now() - timezone.timedelta(seconds=5)
        d.save(update_fields=["next_attempt_at"])

        with mock.patch("nursery.management.commands.deliver_webhooks.urlrequest.urlopen", side_effect=URLError("boom")):
            call_command("deliver_webhooks", limit=10)

        d.refresh_from_db()
        self.assertEqual(d.status, WebhookDeliveryStatus.FAILED)  # DLQ
        self.assertEqual(d.attempt_count, 2)
        self.assertIsNone(d.next_attempt_at)
