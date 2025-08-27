from __future__ import annotations

"""
Webhook enqueue utilities.

This module selects a user's active webhook endpoints that are subscribed to a given
event type and creates `WebhookDelivery` rows in a QUEUED state. Delivery is performed
elsewhere (e.g., a management command/worker), keeping request latency low.

Concepts
--------
- WebhookEndpoint: User-owned configuration including `is_active` and `event_types`.
- Subscriptions:
    * Empty `event_types` means "subscribe to all".
    * A literal "*" in `event_types` also means "subscribe to all".
    * Otherwise, only exact `event_type` matches receive deliveries.
- WebhookDelivery: Per-endpoint rows with `payload` (JSON), `status`, and timestamps.
- Status: `WebhookDeliveryStatus.QUEUED` on enqueue; worker updates on send/ retry.

Security
--------
- Endpoints are filtered by `user`, ensuring tenant isolation.
- Signing/HTTPS enforcement should occur in the worker when dispatching the request,
  per your settings flags (e.g., require HTTPS, HMAC signatures).
"""

import json
from typing import Dict, Iterable, List

from django.utils import timezone

from nursery.models import WebhookEndpoint, WebhookDelivery, WebhookEventType, WebhookDeliveryStatus


def _subscribed(endp: WebhookEndpoint, event_type: str) -> bool:
    """Return True if `endp` is active and subscribed to `event_type`.

    Rules:
        - Inactive endpoints never receive events.
        - Missing/empty `event_types` -> subscribe to all.
        - `"*"` in `event_types` -> subscribe to all.
        - Otherwise, exact membership test.

    Args:
        endp: `WebhookEndpoint` instance to evaluate.
        event_type: Event name to check.

    Returns:
        Boolean indicating whether the endpoint should receive the event.
    """
    if not endp.is_active:
        return False
    types = endp.event_types or []
    if not types:
        return True
    if "*" in types:
        return True
    return event_type in types


def enqueue_for_user(user, event_type: str, payload: Dict) -> int:
    """Enqueue deliveries for all of `user`'s active endpoints subscribed to an event.

    This call is *write-only* and does not perform any network I/O. A separate worker
    process is expected to dequeue and POST deliveries with signing/HTTPS checks.

    Args:
        user: The owner whose endpoints will receive the event.
        event_type: The event key (e.g., "plant.created").
        payload: JSON-serializable event body to persist to each delivery.

    Returns:
        The number of deliveries enqueued.

    Side Effects:
        Creates `WebhookDelivery` rows in `QUEUED` status for matching endpoints.

    PERF:
        # PERF: For large endpoint counts, consider bulk_create to reduce INSERT round-trips.
    """
    count = 0
    for ep in WebhookEndpoint.objects.filter(user=user, is_active=True):
        if _subscribed(ep, event_type):
            # NOTE: We persist the payload as-is; the worker is responsible for
            # timestamps, signing, retries, and status transitions.
            WebhookDelivery.objects.create(
                user=user,
                endpoint=ep,
                event_type=event_type,
                payload=payload,
                status=WebhookDeliveryStatus.QUEUED,
            )
            count += 1
    return count
