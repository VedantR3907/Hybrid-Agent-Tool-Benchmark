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
            "You are the function-tool benchmark agent. You have a small core toolset: read_file, write_file, run_command, and list_files. "
            "Prefer read_file with line ranges for long text-like files. If a large file preview is returned, continue with narrower ranges rather than repeating the same full read. "
            "Prefer run_command for CSV, tabular, sorting, counting, filtering, joins, and verification tasks. "
            "For verification-only tasks, it is acceptable to process a file without returning its full content. "
            "Do not read raw bytes from binary, image, or PDF files. "
            "Examples of tool use patterns only: read_file(path=<file>, start_line=<n>, end_line=<m>); run_command(command=<PowerShell command over the workspace>); list_files(path=<dir>). "
            "Do not guess. Finish with a direct answer tied to the observed evidence."
        )
