from __future__ import annotations

from typing import Any

import httpx

from app.config import BenchmarkConfig
from app.models import ChatResponse


class OllamaClient:
    def __init__(self, config: BenchmarkConfig) -> None:
        self.config = config
        self.client = httpx.Client(timeout=config.ollama_timeout_seconds)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> tuple[ChatResponse, dict[str, Any], dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.config.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.ollama_temperature,
                "num_predict": self.config.ollama_max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        headers = {"Content-Type": "application/json"}
        if self.config.ollama_api_key:
            headers["Authorization"] = f"Bearer {self.config.ollama_api_key}"

        response = self.client.post(f"{self.config.normalized_base_url}/chat", json=payload, headers=headers)
        response.raise_for_status()
        raw = response.json()
        return ChatResponse.model_validate(raw), payload, raw
