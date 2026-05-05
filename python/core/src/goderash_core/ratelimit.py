"""Shared rate-limiter instance.

Kept in its own module to avoid circular imports:
  main.py sets up the FastAPI app and mounts the limiter,
  while auth_public.py decorates routes with @limiter.limit().
Both import from here rather than from each other.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
