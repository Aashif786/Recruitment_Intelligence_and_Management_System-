"""
IP-based rate limiting for sensitive endpoints.
Uses slowapi (built on top of limits library).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Global rate limiter instance — keyed by client IP
limiter = Limiter(key_func=get_remote_address)
