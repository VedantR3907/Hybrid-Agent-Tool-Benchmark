from __future__ import annotations

import os


REDIS_URL = os.getenv("REDIS_URL", "redis://worker-cache.internal:6379/0")


def get_worker_redis_url() -> str:
    return REDIS_URL
