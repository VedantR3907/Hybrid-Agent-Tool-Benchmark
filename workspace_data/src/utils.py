from __future__ import annotations

from typing import Any


def calculate_retry_delay(retries: int) -> int:
    return min(retries * 5, 30)


def process_order(order: dict[str, Any]) -> dict[str, Any]:
    status = "approved" if order.get("amount", 0) < 1000 else "manual_review"
    return {
        "order_id": order["id"],
        "status": status,
        "timeout_policy": "standard-timeout-window",
    }
