from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

from app.config import BenchmarkConfig
from app.logger import RunLogger
from app.models import AgentRunResult, BenchmarkTask, ToolExecutionResult, ToolSpec
from app.ollama_client import OllamaClient


class BaseAgent(ABC):
    def __init__(self, client: OllamaClient, config: BenchmarkConfig, tools: list[ToolSpec]) -> None:
        self.client = client
        self.config = config
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}

    @property
    @abstractmethod
    def agent_type(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def system_prompt(self) -> str:
        raise NotImplementedError

    def _coerce_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str):
            parsed = json.loads(raw_arguments)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError(f"tool arguments must be an object, received: {raw_arguments!r}")

    def run_task(self, task: BenchmarkTask, logger: RunLogger) -> AgentRunResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": task.prompt},
        ]
        llm_turns = 0
        tool_calls = 0
        prompt_tokens = 0
        completion_tokens = 0
        final_answer = ""
        error_reason: str | None = None
        started = time.perf_counter()

        for turn in range(1, self.config.benchmark_max_turns + 1):
            if turn > 1 and self.config.llm_call_pause_seconds > 0:
                logger.log_event("llm_pause", turn=turn, seconds=self.config.llm_call_pause_seconds)
                time.sleep(self.config.llm_call_pause_seconds)

            response, request_payload, raw_response = self.client.chat(
                messages=messages,
                tools=[tool.to_ollama_schema() for tool in self.tools],
                model=self.config.ollama_model,
            )
            llm_turns += 1
            logger.log_event("llm_request", turn=turn, request=request_payload)
            logger.log_event("llm_response", turn=turn, response=raw_response)

            turn_prompt_tokens = response.prompt_eval_count or 0
            turn_completion_tokens = response.eval_count or 0
            prompt_tokens += turn_prompt_tokens
            completion_tokens += turn_completion_tokens

            assistant_message = response.message.model_dump(exclude_none=True)
            messages.append(assistant_message)
            if response.message.content:
                logger.log_assistant_message(turn, response.message.content)
            logger.log_token_usage(turn, turn_prompt_tokens, turn_completion_tokens)

            if response.message.tool_calls:
                for tool_call in response.message.tool_calls:
                    tool_calls += 1
                    tool_name = tool_call.function.name
                    try:
                        arguments = self._coerce_arguments(tool_call.function.arguments)
                    except Exception as exc:
                        error_reason = f"invalid tool arguments for {tool_name}: {exc}"
                        logger.log_event(
                            "tool_result",
                            turn=turn,
                            tool_name=tool_name,
                            arguments=tool_call.function.arguments,
                            error=error_reason,
                        )
                        break

                    logger.log_tool_call(turn, tool_name, arguments)
                    tool = self.tool_map.get(tool_name)
                    if tool is None:
                        tool_result = ToolExecutionResult(content=f"Unknown tool: {tool_name}", metadata={"error": True})
                    else:
                        try:
                            tool_result = tool.handler(arguments)
                        except Exception as exc:  # pragma: no cover
                            tool_result = ToolExecutionResult(
                                content=f"Tool {tool_name} failed: {exc}", metadata={"error": True}
                            )
                    logger.log_tool_result(turn, tool_name, tool_result.content, tool_result.metadata)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": tool_result.content,
                        }
                    )
                if error_reason:
                    break
                continue

            final_answer = (response.message.content or "").strip()
            if final_answer:
                break

        else:
            error_reason = f"max turns exceeded ({self.config.benchmark_max_turns})"

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        success = False
        validation_notes = "agent did not produce a final answer"
        if final_answer:
            success, validation_notes = task.validator(final_answer)
        elif error_reason:
            validation_notes = error_reason

        return AgentRunResult(
            task_id=task.task_id,
            agent_type=self.agent_type,
            model_name=self.config.ollama_model,
            difficulty=task.difficulty,
            success=success,
            validation_notes=validation_notes,
            final_answer=final_answer,
            llm_turns=llm_turns,
            tool_calls=tool_calls,
            elapsed_ms=elapsed_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            error_reason=error_reason,
        )
