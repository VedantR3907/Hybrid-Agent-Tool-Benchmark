from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class BenchmarkConfig(BaseModel):
    ollama_api_key: str | None = Field(default=None)
    ollama_api_key_second: str | None = Field(default=None)
    ollama_base_url: str = Field(default="https://ollama.com/api")
    ollama_model: str = Field(default="glm-5:cloud")
    ollama_models: list[str] = Field(default_factory=list)
    ollama_temperature: float = Field(default=0.0)
    ollama_max_tokens: int = Field(default=2048)
    ollama_timeout_seconds: float = Field(default=60.0)
    benchmark_max_turns: int = Field(default=8)
    llm_call_pause_seconds: float = Field(default=5.0)
    output_char_limit: int = Field(default=4000)
    output_line_limit: int = Field(default=120)
    command_timeout_seconds: float = Field(default=20.0)
    workspace_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "workspace_data")
    runs_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "runs")

    @classmethod
    def load(cls) -> "BenchmarkConfig":
        project_root = Path(__file__).resolve().parents[1]
        load_dotenv(project_root / ".env")
        models_raw = os.getenv("OLLAMA_MODELS", "")
        models = [m.strip() for m in models_raw.split(",") if m.strip()]
        return cls(
            ollama_api_key=os.getenv("OLLAMA_API_KEY"),
            ollama_api_key_second=os.getenv("OLLAMA_API_KEY_SECOND"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "https://ollama.com/api"),
            ollama_model=os.getenv("OLLAMA_MODEL", "glm-5:cloud"),
            ollama_models=models,
            ollama_temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0")),
            ollama_max_tokens=int(os.getenv("OLLAMA_MAX_TOKENS", "2048")),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60")),
            benchmark_max_turns=int(os.getenv("BENCHMARK_MAX_TURNS", "8")),
            llm_call_pause_seconds=float(os.getenv("BENCHMARK_LLM_CALL_PAUSE_SECONDS", "5")),
            output_char_limit=int(os.getenv("BENCHMARK_OUTPUT_CHAR_LIMIT", "4000")),
            output_line_limit=int(os.getenv("BENCHMARK_OUTPUT_LINE_LIMIT", "120")),
            command_timeout_seconds=float(os.getenv("BENCHMARK_COMMAND_TIMEOUT_SECONDS", "20")),
            workspace_root=project_root / "workspace_data",
            runs_root=project_root / "runs",
        )

    @property
    def requires_api_key(self) -> bool:
        return "ollama.com" in self.ollama_base_url

    @property
    def normalized_base_url(self) -> str:
        return self.ollama_base_url.rstrip("/")
