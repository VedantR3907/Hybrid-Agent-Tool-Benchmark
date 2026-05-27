from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console



def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


class RunLogger:
    def __init__(
        self,
        runs_root: Path,
        task_id: str,
        agent_type: str,
        model_name: str,
        console: Console | None = None,
        stream_transcript: bool = False,
    ) -> None:
        self.runs_root = runs_root
        self.task_id = task_id
        self.agent_type = agent_type
        self.model_name = model_name
        self.events: list[dict[str, Any]] = []
        self.transcript_lines: list[str] = []
        self.started_at = datetime.now(timezone.utc)
        self.console = console
        self.stream_transcript = stream_transcript
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def _record_transcript(self, heading: str, content: str, fence: str | None = None) -> None:
        if not content.strip():
            return
        block = [f"## {heading}", ""]
        if fence:
            block.append(f"```{fence}")
            block.append(content.rstrip())
            block.append("```")
        else:
            block.append(content.rstrip())
        block.append("")
        self.transcript_lines.extend(block)
        if self.console and self.stream_transcript:
            self.console.print(f"[bold]{heading}[/bold]")
            self.console.print(content.rstrip(), markup=False)
            self.console.print()

    def log_event(self, event_type: str, **data: Any) -> None:
        self.events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                **data,
            }
        )

    def start_task(self, prompt: str, notes: str) -> None:
        self.log_event("task_start", task_id=self.task_id, prompt=prompt, notes=notes)
        if self.console and self.stream_transcript:
            self.console.rule(f"{self.agent_type} | {self.task_id}")
        self._record_transcript("User", prompt)

    def log_assistant_message(self, turn: int, content: str) -> None:
        self.log_event("assistant_message", turn=turn, content=content)
        self._record_transcript(f"Assistant Turn {turn}", content)

    def log_tool_call(self, turn: int, tool_name: str, arguments: dict[str, Any]) -> None:
        self.log_event("tool_call", turn=turn, tool_name=tool_name, arguments=arguments)
        self._record_transcript(f"Tool Call Turn {turn}: {tool_name}", json.dumps(arguments, indent=2), fence="json")

    def log_tool_result(self, turn: int, tool_name: str, content: str, metadata: dict[str, Any]) -> None:
        self.log_event(
            "tool_result",
            turn=turn,
            tool_name=tool_name,
            content=content,
            metadata=metadata,
        )
        self._record_transcript(f"Tool Output Turn {turn}: {tool_name}", content, fence="text")

    def log_token_usage(self, turn: int, prompt_tokens: int, completion_tokens: int) -> None:
        total_tokens = prompt_tokens + completion_tokens
        payload = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        self.log_event("token_usage", turn=turn, **payload)
        self._record_transcript(f"Token Usage Turn {turn}", json.dumps(payload, indent=2), fence="json")

    def finalize(self, payload: dict[str, Any]) -> tuple[Path, Path]:
        finished_at = datetime.now(timezone.utc)
        safe_model = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in self.model_name)
        stem = f"{self.started_at.strftime('%Y%m%d-%H%M%S')}-{self.task_id}-{self.agent_type}-{safe_model}"
        json_path = self.runs_root / f"{stem}.json"
        transcript_path = self.runs_root / f"{stem}.transcript.md"
        document = {
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "model_name": self.model_name,
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "json_path": str(json_path),
            "transcript_path": str(transcript_path),
            "events": self.events,
            **payload,
        }
        json_path.write_text(json.dumps(document, indent=2, default=_json_default), encoding="utf-8")
        transcript_path.write_text("\n".join(self.transcript_lines).rstrip() + "\n", encoding="utf-8")
        return json_path, transcript_path



def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")

