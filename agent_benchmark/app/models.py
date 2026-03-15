from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field


class ToolFunctionCall(BaseModel):
    index: int | None = None
    name: str
    arguments: dict[str, Any] | str = Field(default_factory=dict)


class ToolCall(BaseModel):
    type: str = "function"
    function: ToolFunctionCall


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_name: str | None = None


class ChatResponse(BaseModel):
    model: str
    message: ChatMessage
    done: bool = True
    total_duration: int | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None


@dataclass
class ToolExecutionResult:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], ToolExecutionResult]

    def to_ollama_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class BenchmarkTask:
    task_id: str
    prompt: str
    validator: Callable[[str], tuple[bool, str]]
    notes: str = ""
    suite: str = "hybrid"


@dataclass
class AgentRunResult:
    task_id: str
    agent_type: str
    model_name: str
    success: bool
    validation_notes: str
    final_answer: str
    llm_turns: int
    tool_calls: int
    elapsed_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error_reason: str | None = None
    log_path: str | None = None
    transcript_path: str | None = None

