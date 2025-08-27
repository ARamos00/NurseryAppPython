from __future__ import annotations

import json
import hmac
import hashlib
import time
from typing import List
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from nursery.models import WebhookDelivery, WebhookDeliveryStatus


def _sign(secret: str, body_bytes: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def _parse_backoff_schedule(cfg) -> List[int]:
    """
    Accept either a comma-separated string or a list/tuple of ints.
    """
    if isinstance(cfg, str):
        parts = [p.strip() for p in cfg.split(",") if p.strip()]
        out: List[int] = []
        for p in parts:
            try:
                out.append(int(p))
            except ValueError:
                continue
        return out or [60, 300, 1800, 7200, 86400]
    if isinstance(cfg, (list, tuple)):
        try:
            return [int(x) for x in cfg] or [60, 300, 1800, 7200, 86400]
        except Exception:
            return [60, 300, 1800, 7200, 86400]
    return [60, 300, 1800, 7200, 86400]


class Command(BaseCommand):
    help = "Delivers queued webhooks (POST JSON with HMAC-SHA256 signature)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Maximum deliveries to process this run")

    def handle(self, *args, **opts):
        if not getattr(settings, "WEBHOOKS_DELIVERY_ENABLED", True):
            self.stdout.write(self.style.WARNING("Delivery disabled (WEBHOOKS_DELIVERY_ENABLED=False). Exiting."))
            return

        limit = int(opts["limit"])
        now = timezone.now()

        qs = (
            WebhookDelivery.objects
            .select_related("endpoint")
            .filter(status=WebhookDeliveryStatus.QUEUED)
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
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
            "User-Agent": getattr(settings, "WEBHOOKS_USER_AGENT", "NurseryTracker/0.1"),
            getattr(settings, "WEBHOOKS_SIGNATURE_HEADER", "X-Webhook-Signature"): signature,
        }

        req = urlrequest.Request(ep.url, data=body, headers=headers, method="POST")

        started = time.perf_counter()
        try:
            timeout_sec = int(getattr(settings, "WEBHOOKS_DELIVERY_TIMEOUT_SEC", 15))
            with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
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
        """
        Decide whether to retry later or park in DLQ (FAILED).
        """
        d.status = WebhookDeliveryStatus.FAILED  # updated to QUEUED if we will retry
        d.last_error = reason

        schedule = _parse_backoff_schedule(getattr(settings, "WEBHOOKS_BACKOFF_SCHEDULE", "60,300,1800,7200,86400"))
        max_attempts = int(getattr(settings, "WEBHOOKS_MAX_ATTEMPTS", len(schedule)))

        # If we've already reached/exceeded max attempts, park in DLQ
        if d.attempt_count >= max_attempts:
            d.next_attempt_at = None
            return

        # attempt_count is 1-based; pick corresponding delay if available, else last
        idx = min(d.attempt_count, len(schedule)) - 1
        delay = schedule[idx]
        d.next_attempt_at = timezone.now() + timezone.timedelta(seconds=delay)
        d.status = WebhookDeliveryStatus.QUEUED
