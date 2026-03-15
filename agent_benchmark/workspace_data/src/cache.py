from __future__ import annotations

import os


REDIS_HOST = os.getenv("REDIS_HOST", "cache.internal")


def get_cache_host() -> str:
    return REDIS_HOST
