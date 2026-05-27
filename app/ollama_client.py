from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import BenchmarkConfig
from app.models import ChatResponse


RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
AUTH_FAIL_STATUS = {401, 403}
MAX_RETRIES = 6
BASE_BACKOFF_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 120.0


class OllamaClient:
    def __init__(self, config: BenchmarkConfig) -> None:
        self.config = config
        self.client = httpx.Client(timeout=config.ollama_timeout_seconds)
        # Tracks which key is active; falls back to second on auth failure
        self._active_key: str | None = config.ollama_api_key

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._active_key:
            headers["Authorization"] = f"Bearer {self._active_key}"
        return headers

    def _try_fallback_key(self) -> bool:
        """Switch to the second API key if available and not already active. Returns True if switched."""
        second = self.config.ollama_api_key_second
        if second and self._active_key != second:
            print(f"[ollama] auth failure on primary key; switching to secondary key")
            self._active_key = second
            return True
        return False

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> tuple[ChatResponse, dict[str, Any], dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model or self.config.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.ollama_temperature,
                "num_predict": self.config.ollama_max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        url = f"{self.config.normalized_base_url}/chat"
        backoff = BASE_BACKOFF_SECONDS
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.client.post(url, json=payload, headers=self._build_headers())
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt == MAX_RETRIES:
                    raise
                wait = min(backoff, MAX_BACKOFF_SECONDS)
                print(f"[ollama] network error ({type(exc).__name__}); waiting {wait:.0f}s then retrying (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                backoff *= 2
                continue

            if response.status_code in AUTH_FAIL_STATUS:
                if self._try_fallback_key():
                    continue  # retry immediately with the new key, don't count as a backoff attempt
                response.raise_for_status()

            if response.status_code in RETRY_STATUS:
                if attempt == MAX_RETRIES:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else backoff
                except ValueError:
                    wait = backoff
                wait = min(wait, MAX_BACKOFF_SECONDS)
                print(f"[ollama] HTTP {response.status_code} on {self.config.ollama_model}; waiting {wait:.0f}s then retrying (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                backoff *= 2
                continue

            response.raise_for_status()
            raw = response.json()
            return ChatResponse.model_validate(raw), payload, raw

        assert last_exc is not None
        raise last_exc
