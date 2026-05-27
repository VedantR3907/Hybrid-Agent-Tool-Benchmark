from __future__ import annotations

import json
from typing import Any

from app.config import BenchmarkConfig
from app.models import ToolExecutionResult, ToolSpec
from app.runtime.command_runner import WorkspaceCommandRunner
from app.runtime.file_reader import RangedFileReader
from app.tools.pdf_tools import PdfToolSuite
from app.tools.sql_tools import SqlToolSuite
from app.workspace import WorkspaceError, WorkspaceManager


class HybridFunctionToolSuite:
    def __init__(self, workspace: WorkspaceManager, config: BenchmarkConfig) -> None:
        self.workspace = workspace
        self.config = config
        self.reader = RangedFileReader(workspace, char_limit=config.output_char_limit, line_limit=config.output_line_limit)
        self.command_runner = WorkspaceCommandRunner(
            workspace,
            char_limit=config.output_char_limit,
            line_limit=config.output_line_limit,
            timeout_seconds=config.command_timeout_seconds,
        )
        self.pdf = PdfToolSuite(workspace, char_limit=config.output_char_limit)
        self.sql = SqlToolSuite(workspace, row_limit=100, char_limit=config.output_char_limit)

    def build_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="list_files",
                description="List files and directories under a workspace path.",
                parameters={"type": "object", "properties": {"path": {"type": "string", "default": "."}}},
                handler=lambda args: self._list_files(args.get("path", ".")),
            ),
            ToolSpec(
                name="read_file",
                description="Read a workspace file. Supports line ranges for long text files and returns previews instead of dumping large files by default.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
                handler=lambda args: self._read_file(args["path"], args.get("start_line"), args.get("end_line")),
            ),
            ToolSpec(
                name="write_file",
                description="Write text content to a file inside the workspace.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                },
                handler=lambda args: self._write_file(args["path"], args["content"]),
            ),
            ToolSpec(
                name="run_command",
                description="Run a PowerShell command in the workspace. Captures stdout, stderr, exit code, duration, and truncates large output safely.",
                parameters={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
                handler=lambda args: self._run_command(args["command"]),
            ),
            ToolSpec(
                name="read_pdf",
                description="Extract text from specific pages of a PDF file in the workspace. Use pages='1-5' for a range or pages='3' for a single page. PDF files are in pdfs/.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Workspace-relative path, e.g. pdfs/apple_statement.pdf"},
                        "pages": {"type": "string", "description": "Page range like '1-5' or single page like '3'. Defaults to '1-5'."},
                    },
                    "required": ["path"],
                },
                handler=lambda args: self.pdf.read_pdf(args),
            ),
            ToolSpec(
                name="search_pdf",
                description="Search for a keyword across all pages of a PDF file. Returns matching page numbers and surrounding snippets.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Workspace-relative path, e.g. pdfs/research_paper.pdf"},
                        "keyword": {"type": "string", "description": "The exact keyword or phrase to search for."},
                        "context_chars": {"type": "integer", "description": "Characters of context around each match (default 200)."},
                    },
                    "required": ["path", "keyword"],
                },
                handler=lambda args: self.pdf.search_pdf(args),
            ),
            ToolSpec(
                name="query_sql",
                description="Run a read-only SQL query against a SQLite database in the workspace. Returns rows as JSON. Only SELECT/WITH/PRAGMA/EXPLAIN allowed. Row limit 100. SQLite DBs live in sqlite/.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Workspace-relative path, e.g. sqlite/chinook.sqlite"},
                        "sql": {"type": "string", "description": "Read-only SQL query."},
                    },
                    "required": ["path", "sql"],
                },
                handler=lambda args: self.sql.query_sql(args),
            ),
        ]

    def _json_result(self, payload: Any, metadata: dict[str, Any] | None = None) -> ToolExecutionResult:
        return ToolExecutionResult(content=json.dumps(payload, indent=2), metadata=metadata or {})

    def _error_result(self, message: str, **metadata: Any) -> ToolExecutionResult:
        return ToolExecutionResult(content=json.dumps({"error": message}, indent=2), metadata=metadata)

    def _list_files(self, path: str) -> ToolExecutionResult:
        try:
            return self._json_result({"path": path, "entries": self.workspace.list_files(path)})
        except WorkspaceError as exc:
            return self._error_result(str(exc), path=path)

    def _read_file(self, path: str, start_line: int | None, end_line: int | None) -> ToolExecutionResult:
        try:
            result = self.reader.read(path, start_line=start_line, end_line=end_line)
            return self._json_result(result.payload, metadata={"path": path, "artifact_path": result.artifact_path})
        except WorkspaceError as exc:
            return self._error_result(str(exc), path=path)

    def _write_file(self, path: str, content: str) -> ToolExecutionResult:
        try:
            written = self.workspace.write_text_file(path, content)
            return self._json_result({"path": path, "written_chars": written})
        except WorkspaceError as exc:
            return self._error_result(str(exc), path=path)

    def _run_command(self, command: str) -> ToolExecutionResult:
        result = self.command_runner.run(command)
        return self._json_result(result.payload, metadata={"command": command, "artifact_path": result.artifact_path})


class HybridCliToolSuite:
    def __init__(self, workspace: WorkspaceManager, config: BenchmarkConfig) -> None:
        self.command_runner = WorkspaceCommandRunner(
            workspace,
            char_limit=config.output_char_limit,
            line_limit=config.output_line_limit,
            timeout_seconds=config.command_timeout_seconds,
        )

    def build_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="run_command",
                description="Run a PowerShell command in the workspace. Captures stdout, stderr, exit code, duration, and truncates large output safely.",
                parameters={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
                handler=lambda args: self._run_command(args["command"]),
            ),
        ]

    def _run_command(self, command: str) -> ToolExecutionResult:
        result = self.command_runner.run(command)
        return ToolExecutionResult(
            content=json.dumps(result.payload, indent=2),
            metadata={"command": command, "artifact_path": result.artifact_path},
        )

