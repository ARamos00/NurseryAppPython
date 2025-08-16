from __future__ import annotations

import json
from typing import Dict, Iterable, List

from django.utils import timezone

from nursery.models import WebhookEndpoint, WebhookDelivery, WebhookEventType, WebhookDeliveryStatus


def _subscribed(endp: WebhookEndpoint, event_type: str) -> bool:
    if not endp.is_active:
        return False
    types = endp.event_types or []
    if not types:
        return True
    if "*" in types:
        return True
    return event_type in types


def enqueue_for_user(user, event_type: str, payload: Dict) -> int:
    """
    Create deliveries for all of the user's active endpoints subscribed to `event_type`.
    Returns number of enqueued deliveries.
    """
    count = 0
    for ep in WebhookEndpoint.objects.filter(user=user, is_active=True):
        if _subscribed(ep, event_type):
            WebhookDelivery.objects.create(
                user=user,
                endpoint=ep,
                event_type=event_type,
                payload=payload,
                status=WebhookDeliveryStatus.QUEUED,
            )
            count += 1
    return count
