from __future__ import annotations

from app.agents.base import BaseAgent


class FunctionAgent(BaseAgent):
    def __init__(self, client, config, tools) -> None:
        super().__init__(client, config, tools)

    @property
    def agent_type(self) -> str:
        return "function"

    def system_prompt(self) -> str:
        return (
            "You are the function-tool benchmark agent. You have a core toolset: read_file, write_file, run_command, list_files, read_pdf, search_pdf, and query_sql. "
            "For SQLite tasks, use query_sql with the database path (e.g. sqlite/chinook.sqlite) and a read-only SQL query. SQLite DBs live in sqlite/. "
            "Discover schema with PRAGMA table_info(table_name) or SELECT name FROM sqlite_master WHERE type='table'. "
            "Prefer read_file with line ranges for long text-like files. If a large file preview is returned, continue with narrower ranges rather than repeating the same full read. "
            "Prefer run_command for CSV, tabular, sorting, counting, filtering, joins, and verification tasks. "
            "For PDF tasks, use search_pdf to locate the relevant page first, then read_pdf with a narrow page range to extract the answer. PDF files are in the pdfs/ directory. "
            "For verification-only tasks, it is acceptable to process a file without returning its full content. "
            "Do not guess. Finish with a direct answer tied to the observed evidence."
        )
