from __future__ import annotations

import re
from typing import Iterable


DEFAULT_CONFIG_TEXT = '{"mode":"default","timeout":30,"retries":3}'



def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())



def contains_all(text: str, expected: Iterable[str]) -> tuple[bool, str]:
    normalized = normalize(text)
    missing = [item for item in expected if normalize(item) not in normalized]
    if missing:
        return False, f"missing expected substrings: {', '.join(missing)}"
    return True, "matched expected substrings"



def contains_any(text: str, expected: Iterable[str]) -> bool:
    normalized = normalize(text)
    return any(normalize(item) in normalized for item in expected)



def contains_in_order(text: str, expected: Iterable[str]) -> tuple[bool, str]:
    normalized = normalize(text)
    cursor = 0
    for item in expected:
        needle = normalize(item)
        position = normalized.find(needle, cursor)
        if position == -1:
            return False, f"expected in-order substring not found: {item}"
        cursor = position + len(needle)
    return True, "matched expected substrings in order"
