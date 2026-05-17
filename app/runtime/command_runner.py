from __future__ import annotations

import re
import subprocess
import sys
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

_PWSH_WRAPPER_RE = re.compile(
    r'^\s*(?:powershell|pwsh)(?:\.exe)?\s+'
    r'(?:-(?:NoProfile|NoLogo|NonInteractive|ExecutionPolicy\s+\S+)\s+)*'
    r'-(?:Command|c)\b',
    re.IGNORECASE,
)


def _is_pwsh_wrapper(command: str) -> bool:
    return bool(_PWSH_WRAPPER_RE.match(command))


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
        if _is_pwsh_wrapper(command):
            return CommandRunPayload(
                {
                    "command": command,
                    "stdout": "",
                    "stderr": (
                        "Invalid command: do not wrap your command in 'powershell -Command \"...\"' or 'pwsh -c ...'. "
                        "Your command is already executed inside PowerShell. Write the PowerShell command directly, e.g. "
                        "Import-Csv 'foo.csv' | Where-Object {...} | Select-Object -First 1"
                    ),
                    "exit_code": 2,
                    "duration_ms": 0,
                    "truncated": False,
                }
            )
        intercepted = self._intercept_simple_file_read(command)
        if intercepted is not None:
            return intercepted

        started = time.perf_counter()
        popen_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=str(self.workspace.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **popen_kwargs,
        )
        timed_out = False
        try:
            stdout_text, stderr_text = process.communicate(timeout=self.timeout_seconds)
            return_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                process.kill()
            try:
                stdout_text, stderr_text = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout_text, stderr_text = "", ""
            return_code = 124

        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout_payload, artifact_path, truncated = self._truncate_stdout(stdout_text or "")
        payload: dict[str, Any] = {
            "command": command,
            "stdout": stdout_payload,
            "stderr": "command timed out" if timed_out else (stderr_text or ""),
            "exit_code": return_code,
            "duration_ms": duration_ms,
            "truncated": truncated,
        }
        if timed_out:
            payload["message"] = f"Command exceeded timeout of {self.timeout_seconds} seconds."
        if artifact_path:
            payload["overflow_path"] = artifact_path
            if not timed_out:
                payload["message"] = (
                    f"Output truncated. Full output saved to {artifact_path}. "
                    "Refine the command or inspect the saved file with narrower commands."
                )
        return CommandRunPayload(payload, artifact_path=artifact_path)

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

