from __future__ import annotations

import csv
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.workspace import WorkspaceManager


TEXT_CHUNK_LINES = 2500
TEXT_PREVIEW_LINES = 200
STRUCTURED_PREVIEW_LINES = 120
CSV_PREVIEW_ROWS = 20

TEXT_LIKE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".log",
    ".env",
    ".ini",
    ".cfg",
    ".toml",
    ".ps1",
    ".sh",
}

STRUCTURED_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
    ".xml",
}

CSV_EXTENSIONS = {".csv", ".tsv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf"}


@dataclass
class ReadFilePayload:
    payload: dict[str, Any]
    artifact_path: str | None = None


class RangedFileReader:
    def __init__(self, workspace: WorkspaceManager, char_limit: int, line_limit: int) -> None:
        self.workspace = workspace
        self.char_limit = char_limit
        self.line_limit = line_limit

    def read(self, path: str, start_line: int | None = None, end_line: int | None = None) -> ReadFilePayload:
        target = self.workspace.ensure_exists(path)
        file_class = self._classify(target)
        mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"

        if file_class in {"image", "pdf", "binary"}:
            info = self.workspace.inspect_file(path)
            return ReadFilePayload(
                {
                    "path": path,
                    "file_class": file_class,
                    "file_type": mime_type,
                    "size_bytes": info.size_bytes,
                    "truncated": False,
                    "content": None,
                    "message": f"{path} is {file_class}-like. Do not read raw bytes; use metadata or targeted commands instead.",
                }
            )

        if file_class == "csv":
            return self._read_csv(path, mime_type, start_line, end_line)

        return self._read_text_like(path, file_class, mime_type, start_line, end_line)

    def _classify(self, target: Path) -> str:
        suffix = target.suffix.lower()
        if suffix in CSV_EXTENSIONS:
            return "csv"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        if suffix in PDF_EXTENSIONS:
            return "pdf"
        if suffix in STRUCTURED_EXTENSIONS:
            return "structured"
        if suffix in TEXT_LIKE_EXTENSIONS:
            return "text"
        if self.workspace.is_binary_path(target):
            return "binary"
        return "text"

    def _read_text_like(
        self,
        path: str,
        file_class: str,
        mime_type: str,
        start_line: int | None,
        end_line: int | None,
    ) -> ReadFilePayload:
        text = self.workspace.read_text_file(path)
        lines = text.splitlines()
        total_lines = len(lines)
        preview_limit = STRUCTURED_PREVIEW_LINES if file_class == "structured" else TEXT_PREVIEW_LINES

        if start_line is not None or end_line is not None:
            start = max(start_line or 1, 1)
            end = min(end_line or total_lines, total_lines)
            selected = lines[start - 1 : end]
            content = "\n".join(selected)
            payload = {
                "path": path,
                "file_class": file_class,
                "file_type": mime_type,
                "total_lines": total_lines,
                "returned_range": f"{start}-{end}",
                "content": content,
                "truncated": False,
                "next_suggested_ranges": self._next_ranges(end, total_lines),
            }
            return self._truncate_payload(path, payload)

        if len(lines) <= preview_limit and len(text) <= self.char_limit:
            return ReadFilePayload(
                {
                    "path": path,
                    "file_class": file_class,
                    "file_type": mime_type,
                    "total_lines": total_lines,
                    "returned_range": f"1-{total_lines}",
                    "content": text,
                    "truncated": False,
                    "next_suggested_ranges": [],
                }
            )

        preview_end = min(preview_limit, total_lines)
        preview = "\n".join(lines[:preview_end])
        payload = {
            "path": path,
            "file_class": file_class,
            "file_type": mime_type,
            "total_lines": total_lines,
            "returned_range": f"1-{preview_end}",
            "content": preview,
            "truncated": True,
            "next_suggested_ranges": self._chunk_ranges(total_lines, start_at=preview_end + 1),
            "message": "Large text-like file preview only. Use narrower line ranges or targeted commands for deeper inspection.",
        }
        return self._truncate_payload(path, payload)

    def _read_csv(
        self,
        path: str,
        mime_type: str,
        start_line: int | None,
        end_line: int | None,
    ) -> ReadFilePayload:
        rows = self.workspace.read_csv_rows(path)
        headers = self.workspace.get_csv_columns(path)
        total_rows = len(rows)

        if start_line is not None or end_line is not None:
            raw_lines = self.workspace.read_text_file(path).splitlines()
            total_lines = len(raw_lines)
            start = max(start_line or 1, 1)
            end = min(end_line or total_lines, total_lines)
            content = "\n".join(raw_lines[start - 1 : end])
            payload = {
                "path": path,
                "file_class": "csv",
                "file_type": mime_type,
                "row_count": total_rows,
                "column_count": len(headers),
                "headers": headers,
                "total_lines": total_lines,
                "returned_range": f"{start}-{end}",
                "content": content,
                "truncated": False,
                "next_suggested_ranges": self._next_ranges(end, total_lines),
                "message": "CSV line-range read. Prefer targeted filtering and aggregation commands for this file type.",
            }
            return self._truncate_payload(path, payload)

        preview_text = self.workspace.rows_to_csv_text(headers, rows[:CSV_PREVIEW_ROWS]) if headers else ""
        return ReadFilePayload(
            {
                "path": path,
                "file_class": "csv",
                "file_type": mime_type,
                "row_count": total_rows,
                "column_count": len(headers),
                "headers": headers,
                "returned_range": None,
                "content": preview_text,
                "truncated": total_rows > CSV_PREVIEW_ROWS,
                "next_suggested_ranges": [],
                "message": "Large CSV preview only. Prefer targeted filtering, sorting, counting, and comparison commands instead of loading the full dataset.",
                "suggested_commands": [
                    f"Import-Csv '{path}' | Select-Object -First 5",
                    f"Import-Csv '{path}' | Where-Object {{$_.Year -eq '2024'}} | Select-Object -First 5",
                    f"Import-Csv '{path}' | Where-Object {{$_.Variable_code -eq 'H23'}} | Select-Object -First 5",
                ],
            }
        )

    def _chunk_ranges(self, total_lines: int, start_at: int = 1) -> list[str]:
        ranges: list[str] = []
        current = start_at
        while current <= total_lines and len(ranges) < 3:
            end = min(current + TEXT_CHUNK_LINES - 1, total_lines)
            ranges.append(f"{current}-{end}")
            current = end + 1
        return ranges

    def _next_ranges(self, end_line: int, total_lines: int) -> list[str]:
        if end_line >= total_lines:
            return []
        return self._chunk_ranges(total_lines, start_at=end_line + 1)

    def _truncate_payload(self, path: str, payload: dict[str, Any]) -> ReadFilePayload:
        content = payload.get("content")
        if not isinstance(content, str):
            return ReadFilePayload(payload)
        lines = content.splitlines()
        if len(content) <= self.char_limit and len(lines) <= self.line_limit:
            return ReadFilePayload(payload)
        preview_lines = lines[: self.line_limit]
        preview = "\n".join(preview_lines)
        if len(preview) > self.char_limit:
            preview = preview[: self.char_limit]
        artifact_path = self.workspace.write_artifact(f"read-{Path(path).stem}", content)
        payload = dict(payload)
        payload["content"] = preview
        payload["truncated"] = True
        payload["overflow_path"] = artifact_path
        payload["message"] = (
            f"Output truncated. Full content saved to {artifact_path}. "
            "Use a narrower line range or a more targeted command for deeper inspection."
        )
        return ReadFilePayload(payload, artifact_path=artifact_path)

