"""
Throttle classes for rate limiting during tests and development.

These throttles intentionally use low rates to make it easy to exercise 429
responses in automated tests (see `nursery/tests/test_throttling.py`) and
manual QA. Production throttle classes/scopes should be configured via DRF
settings and not altered here.

Classes:
    - `UserBurstThrottle`: e.g., 3 requests per minute per authenticated user.
    - `AnonBurstThrottle`: e.g., 2 requests per minute per anonymous client.
"""

from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class UserBurstThrottle(UserRateThrottle):
    """
    Low-rate throttle for tests to quickly trigger 429s.

    Rate:
        "3/min" per authenticated user identity.
    """
    rate = "3/min"


class AnonBurstThrottle(AnonRateThrottle):
    """
    Low-rate throttle for tests to quickly trigger 429s.

    Rate:
        "2/min" per anonymous client/IP (per DRF's throttle scope).
    """
    rate = "2/min"
