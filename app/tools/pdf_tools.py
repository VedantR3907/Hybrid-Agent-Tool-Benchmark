from __future__ import annotations

import json
import re
from typing import Any

from app.models import ToolExecutionResult
from app.workspace import WorkspaceManager


def _parse_page_range(pages_str: str, total_pages: int) -> list[int]:
    pages_str = pages_str.strip()
    match = re.fullmatch(r"(\d+)-(\d+)", pages_str)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
    else:
        try:
            page = int(pages_str)
            start, end = page, page
        except ValueError:
            raise ValueError(f"Invalid pages format: {pages_str!r}. Use '3' or '1-5'.")
    start = max(1, start)
    end = min(total_pages, end)
    return list(range(start - 1, end))  # 0-indexed


def _ok(payload: Any) -> ToolExecutionResult:
    return ToolExecutionResult(content=json.dumps(payload, indent=2), metadata={})


def _err(message: str) -> ToolExecutionResult:
    return ToolExecutionResult(content=json.dumps({"error": message}), metadata={})


class PdfToolSuite:
    def __init__(self, workspace: WorkspaceManager, char_limit: int = 4000) -> None:
        self.workspace = workspace
        self.char_limit = char_limit

    def read_pdf(self, args: dict[str, Any]) -> ToolExecutionResult:
        try:
            import pypdf
        except ImportError:
            return _err("pypdf is not installed. Run: pip install pypdf")

        path = args.get("path", "")
        pages_str = str(args.get("pages", "1-5"))
        try:
            full_path = self.workspace.resolve_path(path)
        except Exception as exc:
            return _err(str(exc))

        try:
            reader = pypdf.PdfReader(str(full_path))
            total = len(reader.pages)
            indices = _parse_page_range(pages_str, total)

            extracted: list[dict[str, Any]] = []
            total_chars = 0
            for idx in indices:
                text = (reader.pages[idx].extract_text() or "").strip()
                remaining = self.char_limit - total_chars
                if remaining <= 0:
                    extracted.append({"page": idx + 1, "text": "[char limit reached — request a smaller range]"})
                    break
                if len(text) > remaining:
                    text = text[:remaining] + " ...[truncated]"
                extracted.append({"page": idx + 1, "text": text})
                total_chars += len(text)

            return _ok({
                "path": path,
                "total_pages": total,
                "returned_pages": [p["page"] for p in extracted],
                "pages": extracted,
            })
        except Exception as exc:
            return _err(str(exc))

    def search_pdf(self, args: dict[str, Any]) -> ToolExecutionResult:
        try:
            import pypdf
        except ImportError:
            return _err("pypdf is not installed. Run: pip install pypdf")

        path = args.get("path", "")
        keyword = str(args.get("keyword", ""))
        context_chars = int(args.get("context_chars", 200))

        try:
            full_path = self.workspace.resolve_path(path)
        except Exception as exc:
            return _err(str(exc))

        try:
            reader = pypdf.PdfReader(str(full_path))
            total = len(reader.pages)
            matches: list[dict[str, Any]] = []
            keyword_lower = keyword.lower()

            for idx in range(total):
                text = reader.pages[idx].extract_text() or ""
                text_lower = text.lower()
                pos = 0
                snippets: list[str] = []
                while True:
                    found = text_lower.find(keyword_lower, pos)
                    if found == -1:
                        break
                    start = max(0, found - context_chars // 2)
                    end = min(len(text), found + len(keyword) + context_chars // 2)
                    snippet = text[start:end].replace("\n", " ").strip()
                    snippets.append(snippet)
                    pos = found + len(keyword)
                    if len(snippets) >= 3:
                        break
                if snippets:
                    matches.append({"page": idx + 1, "count": len(snippets), "snippets": snippets})

            return _ok({
                "path": path,
                "keyword": keyword,
                "total_pages": total,
                "pages_with_matches": len(matches),
                "matches": matches[:20],
            })
        except Exception as exc:
            return _err(str(exc))
