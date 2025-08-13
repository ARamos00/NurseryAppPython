from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class UserBurstThrottle(UserRateThrottle):
    """
    Low-rate throttle for tests to quickly trigger 429s.
    """
    rate = "3/min"


class AnonBurstThrottle(AnonRateThrottle):
    """
    Low-rate throttle for tests to quickly trigger 429s.
    """
    rate = "2/min"
