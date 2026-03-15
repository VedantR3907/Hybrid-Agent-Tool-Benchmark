from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.runtime.file_reader import RangedFileReader
from app.workspace import WorkspaceManager


_SIMPLE_FILE_READ_RE = re.compile(
    r'^\s*(?:cat|type|Get-Content)\s+(?:-LiteralPath\s+|-Path\s+)?[\"\']?(?P<path>[^\"\'|;]+?)[\"\']?\s*$',
    re.IGNORECASE,
)


@dataclass
class CommandRunPayload:
    payload: dict[str, Any]
    artifact_path: str | None = None


class WorkspaceCommandRunner:
    def __init__(self, workspace: WorkspaceManager, char_limit: int, line_limit: int, timeout_seconds: float) -> None:
        self.workspace = workspace
        self.char_limit = char_limit
        self.line_limit = line_limit
        self.timeout_seconds = timeout_seconds
        self.reader = RangedFileReader(workspace, char_limit=char_limit, line_limit=line_limit)

    def run(self, command: str) -> CommandRunPayload:
        intercepted = self._intercept_simple_file_read(command)
        if intercepted is not None:
            return intercepted

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                cwd=str(self.workspace.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            stdout_payload, artifact_path, truncated = self._truncate_stdout(completed.stdout)
            payload = {
                "command": command,
                "stdout": stdout_payload,
                "stderr": completed.stderr,
                "exit_code": completed.returncode,
                "duration_ms": duration_ms,
                "truncated": truncated,
            }
            if artifact_path:
                payload["overflow_path"] = artifact_path
                payload["message"] = (
                    f"Output truncated. Full output saved to {artifact_path}. "
                    "Refine the command or inspect the saved file with narrower commands."
                )
            return CommandRunPayload(payload, artifact_path=artifact_path)
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            stdout_payload, artifact_path, truncated = self._truncate_stdout((exc.stdout or "") if isinstance(exc.stdout, str) else "")
            return CommandRunPayload(
                {
                    "command": command,
                    "stdout": stdout_payload,
                    "stderr": "command timed out",
                    "exit_code": 124,
                    "duration_ms": duration_ms,
                    "truncated": truncated,
                    "message": f"Command exceeded timeout of {self.timeout_seconds} seconds.",
                    **({"overflow_path": artifact_path} if artifact_path else {}),
                },
                artifact_path=artifact_path,
            )

    def _intercept_simple_file_read(self, command: str) -> CommandRunPayload | None:
        match = _SIMPLE_FILE_READ_RE.match(command)
        if not match:
            return None
        raw_path = match.group("path").strip()
        if not raw_path:
            return None
        candidate = Path(raw_path)
        if candidate.is_absolute():
            try:
                candidate = candidate.resolve().relative_to(self.workspace.root).as_posix()
            except Exception:
                return None
        path = candidate.as_posix()
        try:
            result = self.reader.read(path)
        except Exception:
            return None
        payload = {
            "command": command,
            "stdout": result.payload,
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 0,
            "truncated": bool(result.payload.get("truncated", False)),
        }
        if result.artifact_path:
            payload["overflow_path"] = result.artifact_path
        return CommandRunPayload(payload, artifact_path=result.artifact_path)

    def _truncate_stdout(self, stdout: str) -> tuple[str, str | None, bool]:
        lines = stdout.splitlines()
        if len(stdout) <= self.char_limit and len(lines) <= self.line_limit:
            return stdout, None, False
        preview = "\n".join(lines[: self.line_limit])
        if len(preview) > self.char_limit:
            preview = preview[: self.char_limit]
        artifact_path = self.workspace.write_artifact("cmd-output", stdout)
        return preview, artifact_path, True

