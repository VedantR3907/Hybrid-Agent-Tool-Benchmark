from __future__ import annotations

from statistics import mean
from typing import Iterable

from app.models import AgentRunResult



def aggregate_metrics(results: Iterable[AgentRunResult]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[AgentRunResult]] = {}
    for result in results:
        grouped.setdefault(result.agent_type, []).append(result)

    summary: dict[str, dict[str, float]] = {}
    for agent_type, items in grouped.items():
        summary[agent_type] = {
            "runs": len(items),
            "success_rate": sum(1 for item in items if item.success) / len(items) if items else 0.0,
            "avg_tool_calls": mean(item.tool_calls for item in items) if items else 0.0,
            "avg_llm_turns": mean(item.llm_turns for item in items) if items else 0.0,
            "avg_elapsed_ms": mean(item.elapsed_ms for item in items) if items else 0.0,
            "avg_total_tokens": mean(item.total_tokens for item in items) if items else 0.0,
            "sum_total_tokens": sum(item.total_tokens for item in items),
        }
    return summary
