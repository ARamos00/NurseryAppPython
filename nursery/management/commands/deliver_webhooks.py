from __future__ import annotations

import json
import hmac
import hashlib
import time
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from nursery.models import WebhookDelivery, WebhookDeliveryStatus


BACKOFF_SECONDS = [60, 300, 1800, 7200, 86400]  # 1m, 5m, 30m, 2h, 24h
SIG_HEADER = getattr(settings, "WEBHOOKS_SIGNATURE_HEADER", "X-Webhook-Signature")
USER_AGENT = getattr(settings, "WEBHOOKS_USER_AGENT", "NurseryTracker/0.1")


def _sign(secret: str, body_bytes: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    # include algorithm prefix for clarity
    return f"sha256={mac}"


class Command(BaseCommand):
    help = "Delivers queued webhooks (POST JSON with HMAC-SHA256 signature)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Maximum deliveries to process this run")

    def handle(self, *args, **opts):
        limit = int(opts["limit"])
        now = timezone.now()

        qs = (
            WebhookDelivery.objects
            .select_related("endpoint")
            .filter(status=WebhookDeliveryStatus.QUEUED)
            .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now))
            .order_by("created_at")[:limit]
        )

        processed = 0
        for d in qs:
            processed += 1
            self._process_one(d)

        self.stdout.write(self.style.SUCCESS(f"Processed {processed} delivery(ies)."))

    def _process_one(self, d: WebhookDelivery):
        ep = d.endpoint
        body = json.dumps(d.payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signature = _sign(ep.secret, body)

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
            SIG_HEADER: signature,
        }

        req = urlrequest.Request(ep.url, data=body, headers=headers, method="POST")

        started = time.perf_counter()
        try:
            with urlrequest.urlopen(req, timeout=15) as resp:
                resp_body = resp.read()
                status_code = resp.getcode()
                resp_headers = dict(resp.getheaders())

            duration_ms = int((time.perf_counter() - started) * 1000)

            d.response_status = status_code
            d.response_headers = resp_headers
            d.response_body = (resp_body or b"").decode("utf-8", errors="replace")[:8192]
            d.request_duration_ms = duration_ms
            d.last_attempt_at = timezone.now()
            d.attempt_count += 1

            if 200 <= status_code < 300:
                d.status = WebhookDeliveryStatus.SENT
                d.next_attempt_at = None
                d.last_error = ""
            else:
                self._schedule_retry(d, f"HTTP {status_code}")
        except (HTTPError, URLError, TimeoutError) as e:
            d.response_status = None
            d.response_headers = {}
            d.response_body = ""
            d.request_duration_ms = int((time.perf_counter() - started) * 1000)
            d.last_attempt_at = timezone.now()
            d.attempt_count += 1
            self._schedule_retry(d, str(e))
        finally:
            d.save(update_fields=[
                "response_status", "response_headers", "response_body",
                "request_duration_ms", "last_attempt_at", "attempt_count",
                "status", "next_attempt_at", "last_error", "updated_at",
            ])

    def _schedule_retry(self, d: WebhookDelivery, reason: str):
        d.status = WebhookDeliveryStatus.FAILED  # may be changed to QUEUED below
        d.last_error = reason
        # compute next backoff
        if d.attempt_count <= len(BACKOFF_SECONDS):
            delay = BACKOFF_SECONDS[d.attempt_count - 1]
            d.next_attempt_at = timezone.now() + timezone.timedelta(seconds=delay)
            d.status = WebhookDeliveryStatus.QUEUED
