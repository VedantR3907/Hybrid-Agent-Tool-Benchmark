from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.models import ToolExecutionResult
from app.workspace import WorkspaceManager


_READ_ONLY_PREFIXES = ("select", "with", "pragma", "explain")


def _ok(payload: Any) -> ToolExecutionResult:
    return ToolExecutionResult(content=json.dumps(payload, indent=2, default=str), metadata={})


def _err(message: str) -> ToolExecutionResult:
    return ToolExecutionResult(content=json.dumps({"error": message}), metadata={})


class SqlToolSuite:
    def __init__(self, workspace: WorkspaceManager, row_limit: int = 100, char_limit: int = 4000) -> None:
        self.workspace = workspace
        self.row_limit = row_limit
        self.char_limit = char_limit

    def query_sql(self, args: dict[str, Any]) -> ToolExecutionResult:
        path = args.get("path", "")
        sql = str(args.get("sql", "")).strip()
        if not sql:
            return _err("sql is required")
        first_token = sql.lstrip("(").lstrip().split()[0].lower() if sql else ""
        if first_token not in _READ_ONLY_PREFIXES:
            return _err(f"only read-only queries allowed (SELECT/WITH/PRAGMA/EXPLAIN), got: {first_token}")

        try:
            full_path = self.workspace.resolve_path(path)
        except Exception as exc:
            return _err(str(exc))
        if not full_path.exists():
            return _err(f"database not found: {path}")

        try:
            uri = f"file:{full_path.as_posix()}?mode=ro"
            con = sqlite3.connect(uri, uri=True)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(self.row_limit + 1)
            truncated = len(rows) > self.row_limit
            rows = rows[: self.row_limit]
            result_rows = [dict(r) for r in rows]
            con.close()
        except Exception as exc:
            return _err(f"{type(exc).__name__}: {exc}")

        payload: dict[str, Any] = {
            "path": path,
            "columns": columns,
            "row_count": len(result_rows),
            "truncated": truncated,
            "rows": result_rows,
        }
        if truncated:
            payload["message"] = (
                f"Row limit reached ({self.row_limit}). Refine the query with WHERE/LIMIT/aggregates."
            )

        content = json.dumps(payload, indent=2, default=str)
        if len(content) > self.char_limit:
            payload["rows"] = result_rows[: max(1, len(result_rows) // 4)]
            payload["truncated"] = True
            payload["message"] = "Output truncated by char limit. Use aggregates or narrower SELECT columns."
            content = json.dumps(payload, indent=2, default=str)
        return ToolExecutionResult(content=content, metadata={"path": path})
