from __future__ import annotations

import csv
import io
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".log",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".pdf",
    ".zip",
    ".sqlite",
    ".db",
    ".sqlite3",
}

CSV_PREVIEW_ROWS = 20
CSV_LARGE_ROW_THRESHOLD = 50
CSV_LARGE_SIZE_THRESHOLD = 8192


class WorkspaceError(Exception):
    """Base workspace error."""


class PathAccessError(WorkspaceError):
    """Raised when a path escapes the workspace root."""


class BinaryFileError(WorkspaceError):
    """Raised when a text-only command tries to open a binary file."""


class MissingFileError(WorkspaceError):
    """Raised when a path does not exist."""


@dataclass
class FileInfo:
    path: str
    kind: str
    size_bytes: int
    mime_type: str
    preview: str | None = None


@dataclass
class CsvSummary:
    path: str
    row_count: int
    headers: list[str]
    preview_rows: list[dict[str, str]]


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.artifacts_root = self.root / ".artifacts"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PathAccessError(f"path escapes workspace: {path}") from exc
        return candidate

    def display_path(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def ensure_exists(self, path: str) -> Path:
        resolved = self.resolve_path(path)
        if not resolved.exists():
            raise MissingFileError(f"file not found: {path}")
        return resolved

    def is_binary_path(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix in BINARY_EXTENSIONS:
            return True
        if suffix in TEXT_EXTENSIONS:
            return False
        chunk = path.read_bytes()[:2048]
        if b"\x00" in chunk:
            return True
        try:
            chunk.decode("utf-8")
            return False
        except UnicodeDecodeError:
            return True

    def list_files(self, path: str = ".") -> list[str]:
        target = self.ensure_exists(path)
        if not target.is_dir():
            raise WorkspaceError(f"not a directory: {path}")
        entries: list[str] = []
        for entry in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            rel = self.display_path(entry)
            entries.append(f"{rel}/" if entry.is_dir() else rel)
        return entries

    def is_csv_path(self, path: str | Path) -> bool:
        candidate = path if isinstance(path, Path) else Path(path)
        return candidate.suffix.lower() == ".csv"

    def read_text_file(self, path: str) -> str:
        target = self.ensure_exists(path)
        if target.is_dir():
            raise WorkspaceError(f"is a directory: {path}")
        if self.is_binary_path(target):
            raise BinaryFileError(f"binary file: {path}")
        return target.read_text(encoding="utf-8")

    def write_text_file(self, path: str, content: str) -> int:
        target = self.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return len(content)

    def search_in_file(self, path: str, pattern: str, case_sensitive: bool = True) -> list[str]:
        content = self.read_text_file(path)
        lines = content.splitlines()
        if case_sensitive:
            return [line for line in lines if pattern in line]
        lowered = pattern.lower()
        return [line for line in lines if lowered in line.lower()]

    def count_matching_lines(self, path: str, pattern: str, case_sensitive: bool = True) -> int:
        return len(self.search_in_file(path, pattern, case_sensitive=case_sensitive))

    def head_file(self, path: str, n: int) -> str:
        return "\n".join(self.read_text_file(path).splitlines()[:n])

    def tail_file(self, path: str, n: int) -> str:
        return "\n".join(self.read_text_file(path).splitlines()[-n:])

    def find_files(self, path: str, pattern: str) -> list[str]:
        base = self.ensure_exists(path)
        if not base.is_dir():
            raise WorkspaceError(f"not a directory: {path}")
        matches = [
            self.display_path(item)
            for item in sorted(base.rglob("*"))
            if item.is_file() and item.match(pattern)
        ]
        return matches

    def search_workspace(self, pattern: str, path: str = ".", case_sensitive: bool = False) -> list[str]:
        base = self.ensure_exists(path)
        if not base.is_dir():
            raise WorkspaceError(f"not a directory: {path}")
        matches: list[str] = []
        needle = pattern if case_sensitive else pattern.lower()
        for item in sorted(base.rglob("*")):
            if not item.is_file() or self.is_binary_path(item):
                continue
            rel = self.display_path(item)
            for line in item.read_text(encoding="utf-8").splitlines():
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    matches.append(rel)
                    break
        return matches

    def inspect_file(self, path: str) -> FileInfo:
        target = self.ensure_exists(path)
        mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        kind = "binary"
        preview: str | None = None
        if target.is_dir():
            kind = "directory"
        elif not self.is_binary_path(target):
            kind = "text"
            preview = "\n".join(target.read_text(encoding="utf-8").splitlines()[:5])
        elif target.suffix.lower() == ".png":
            kind = "png image"
        return FileInfo(
            path=self.display_path(target),
            kind=kind,
            size_bytes=target.stat().st_size,
            mime_type=mime_type,
            preview=preview,
        )

    def query_csv(
        self,
        path: str,
        filter_column: str,
        filter_value: str,
        sort_column: str,
        descending: bool = True,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        rows = self.read_csv_rows(path)
        filtered = [row for row in rows if row.get(filter_column) == filter_value]

        def sort_key(row: dict[str, Any]) -> Any:
            value = row.get(sort_column, "")
            try:
                return float(value)
            except ValueError:
                return value

        filtered.sort(key=sort_key, reverse=descending)
        return filtered[:limit]

    def read_csv_rows(self, path: str) -> list[dict[str, str]]:
        target = self.ensure_exists(path)
        if not self.is_csv_path(target):
            raise WorkspaceError(f"not a csv file: {path}")
        with target.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def get_csv_summary(self, path: str, preview_rows: int = CSV_PREVIEW_ROWS) -> CsvSummary:
        rows = self.read_csv_rows(path)
        headers = list(rows[0].keys()) if rows else []
        return CsvSummary(
            path=path,
            row_count=len(rows),
            headers=headers,
            preview_rows=rows[:preview_rows],
        )

    def is_large_csv(self, path: str) -> bool:
        target = self.ensure_exists(path)
        if not self.is_csv_path(target):
            return False
        summary = self.get_csv_summary(path, preview_rows=1)
        return summary.row_count > CSV_LARGE_ROW_THRESHOLD or target.stat().st_size > CSV_LARGE_SIZE_THRESHOLD

    def get_csv_columns(self, path: str) -> list[str]:
        return self.get_csv_summary(path, preview_rows=1).headers

    def filter_csv_rows(self, path: str, filters: dict[str, str]) -> list[dict[str, str]]:
        rows = self.read_csv_rows(path)
        return [
            row for row in rows
            if all((row.get(column, "") or "") == expected for column, expected in filters.items())
        ]

    def rows_to_csv_text(self, headers: list[str], rows: list[dict[str, str]]) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})
        return output.getvalue().rstrip()
    def format_csv_preview(
        self,
        path: str,
        rows: list[dict[str, str]] | None = None,
        title: str | None = None,
        filters: dict[str, str] | None = None,
        total_rows: int | None = None,
    ) -> tuple[str, str | None]:
        summary = self.get_csv_summary(path)
        headers = summary.headers
        selected_rows = rows if rows is not None else self.read_csv_rows(path)
        preview_rows = selected_rows[:CSV_PREVIEW_ROWS]
        preview_csv = self.rows_to_csv_text(headers, preview_rows) if headers else ""
        artifact_path: str | None = None
        if len(selected_rows) > CSV_PREVIEW_ROWS:
            artifact_content = self.rows_to_csv_text(headers, selected_rows)
            artifact_path = self.write_artifact(f"csv-{Path(path).stem}", artifact_content, suffix=".csv")

        header_line = ", ".join(headers)
        lines = [f"[info] {title or 'Large CSV detected'}: {path}"]
        lines.append(
            f"Rows: {total_rows if total_rows is not None else (len(selected_rows) if rows is not None else summary.row_count)}"
        )
        lines.append(f"Columns: {len(headers)}")
        lines.append("Headers:")
        lines.append(header_line)
        if filters:
            lines.append("Filters:")
            lines.append(", ".join(f"{key}={value}" for key, value in filters.items()))
        lines.append("")
        lines.append(f"Preview (first {min(CSV_PREVIEW_ROWS, len(preview_rows))} rows):")
        lines.append(preview_csv or "<no rows>")
        if artifact_path:
            lines.append("")
            lines.append("--- CSV output truncated ---")
            lines.append(f"Full output: {artifact_path}")
            lines.append("Use targeted inspection commands instead, for example:")
            lines.append(f"csv-head {path}")
            lines.append(f"csv-cols {path}")
            lines.append(f"csv-filter {path} Year=2024")
            lines.append(f"csv-filter {path} Variable_code=H23")
            lines.append(f"grep \"Agriculture, Forestry and Fishing\" {path}")
        return "\n".join(lines), artifact_path

    def write_artifact(self, prefix: str, content: str, suffix: str = ".txt") -> str:
        existing = sorted(self.artifacts_root.glob(f"{prefix}-*{suffix}"))
        artifact_path = self.artifacts_root / f"{prefix}-{len(existing) + 1}{suffix}"
        artifact_path.write_text(content, encoding="utf-8")
        return self.display_path(artifact_path)

    @staticmethod
    def file_info_to_text(info: FileInfo) -> str:
        payload = {
            "path": info.path,
            "kind": info.kind,
            "size_bytes": info.size_bytes,
            "mime_type": info.mime_type,
        }
        if info.preview:
            payload["preview"] = info.preview
        return json.dumps(payload, indent=2)



