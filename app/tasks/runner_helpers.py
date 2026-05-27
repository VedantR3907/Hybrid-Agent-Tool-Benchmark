from __future__ import annotations

from statistics import mean
from typing import Iterable

from app.models import AgentRunResult



def _summarize(items: list[AgentRunResult]) -> dict[str, float]:
    if not items:
        return {
            "runs": 0,
            "success_rate": 0.0,
            "avg_tool_calls": 0.0,
            "avg_llm_turns": 0.0,
            "avg_elapsed_ms": 0.0,
            "avg_total_tokens": 0.0,
            "sum_total_tokens": 0,
        }
    return {
        "runs": len(items),
        "success_rate": sum(1 for item in items if item.success) / len(items),
        "avg_tool_calls": mean(item.tool_calls for item in items),
        "avg_llm_turns": mean(item.llm_turns for item in items),
        "avg_elapsed_ms": mean(item.elapsed_ms for item in items),
        "avg_total_tokens": mean(item.total_tokens for item in items),
        "sum_total_tokens": sum(item.total_tokens for item in items),
    }


def aggregate_metrics(results: Iterable[AgentRunResult]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[AgentRunResult]] = {}
    for result in results:
        grouped.setdefault(result.agent_type, []).append(result)
    return {agent_type: _summarize(items) for agent_type, items in grouped.items()}


def aggregate_by_model_agent(results: Iterable[AgentRunResult]) -> dict[str, dict[str, dict[str, float]]]:
    grouped: dict[str, dict[str, list[AgentRunResult]]] = {}
    for result in results:
        grouped.setdefault(result.model_name, {}).setdefault(result.agent_type, []).append(result)
    return {
        model: {agent: _summarize(items) for agent, items in agents.items()}
        for model, agents in grouped.items()
    }


def aggregate_by_difficulty(results: Iterable[AgentRunResult]) -> dict[str, dict[str, dict[str, float]]]:
    """Returns {difficulty: {agent_type: metrics}}."""
    grouped: dict[str, dict[str, list[AgentRunResult]]] = {}
    for result in results:
        grouped.setdefault(result.difficulty, {}).setdefault(result.agent_type, []).append(result)
    return {
        difficulty: {agent: _summarize(items) for agent, items in agents.items()}
        for difficulty, agents in grouped.items()
    }
