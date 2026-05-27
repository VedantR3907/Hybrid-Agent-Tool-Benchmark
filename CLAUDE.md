# Hybrid Agent Tool Benchmark

## Purpose

Benchmarks two agent styles on identical local workspace tasks using the same model and settings:

- **Function agent** — structured tool calls: `list_files`, `read_file`, `write_file`, `run_command`, `read_pdf`, `search_pdf`, `query_sql`
- **CLI agent** — single tool: `run_command` (PowerShell, workspace-scoped) — must compose everything natively (PDF extraction via WinRT or pdftotext, SQL via `python -c "import sqlite3..."`, etc.)

Goal: quantify the tradeoff between rich function-calling primitives vs raw CLI fluency — success rate, token cost, tool call count, latency — across a 48-task suite and multiple models.

## Stack

- Python 3.11+
- `httpx` — Ollama API client
- `pydantic` — config and model validation
- `rich` — terminal tables and live transcript streaming
- `matplotlib` — post-run chart generation
- `pypdf` — PDF text extraction for the function-agent PDF tools

## Environment setup

```powershell
# 1. Copy and fill env
cp .env.example .env   # set OLLAMA_API_KEY, OLLAMA_MODEL, etc.

# 2. Install deps
pip install -r requirements.txt

# 3. Refresh workspace fixtures (first time or after changes)
python -m app.workspace.setup_workspace --force

# 4. (Optional) Build the large StackExchange SQLite DB used by the hard SQL tasks.
#    Requires the superuser.com XML data dump from https://archive.org/details/stackexchange
python scripts/build_superuser_db.py <path-to-extracted-xml-dir> workspace_data/sqlite/superuser.sqlite
```

Key env vars (in `.env`):

| Variable | Purpose |
|---|---|
| `OLLAMA_API_KEY` | Required for Ollama Cloud |
| `OLLAMA_API_KEY_SECOND` | Optional fallback key (auto-used on 401/403) |
| `OLLAMA_BASE_URL` | Default: `https://ollama.com/api` |
| `OLLAMA_MODEL` | Default model, e.g. `gpt-oss:120b` |
| `OLLAMA_MODELS` | Comma-separated list for multi-model runs |
| `BENCHMARK_MAX_TURNS` | Max agentic turns per task (default: 30) |
| `BENCHMARK_LLM_CALL_PAUSE_SECONDS` | Pause between LLM calls (default: 5) |
| `BENCHMARK_COMMAND_TIMEOUT_SECONDS` | Per-command timeout (default: 20) |
| `BENCHMARK_OUTPUT_CHAR_LIMIT` | Truncate tool output above this many chars (default: 4000) |

## Run commands

```powershell
# Run both agents on all tasks (with workspace refresh)
python -m app.tasks.runner --rebuild-workspace

# Run one agent only
python -m app.tasks.runner --agent function
python -m app.tasks.runner --agent cli

# Run a specific task range (1-based inclusive)
python -m app.tasks.runner --task-range 2-4

# Run specific task IDs
python -m app.tasks.runner --tasks pdf_apple_financials sql_chinook_top_genre

# Run across multiple models
python -m app.tasks.runner --models gpt-oss:120b,glm-5:cloud,qwen2.5-coder

# Suppress live transcript streaming
python -m app.tasks.runner --no-transcript

# Generate charts and FINDINGS.md after a multi-model run
python -m app.tasks.report
```

## Project layout

```
app/
  agents/         # BaseAgent, FunctionAgent, CliAgent
  tasks/          # runner.py (entry), hybrid_tasks.py (task suite), evaluator.py, report.py
  tools/          # HybridFunctionToolSuite, HybridCliToolSuite, PdfToolSuite, SqlToolSuite
  runtime/        # command_runner.py, file_reader.py (file-type-aware read logic)
  workspace/      # WorkspaceManager, setup_workspace.py
  config.py       # BenchmarkConfig (pydantic, loaded from .env)
  ollama_client.py
  models.py       # AgentRunResult, BenchmarkTask
  logger.py       # RunLogger, write_summary

scripts/
  build_superuser_db.py   # Stream-converts a StackExchange XML dump into a single SQLite DB

workspace_data/   # Benchmark workspace (files agents operate on)
  pdfs/           # PDF fixtures for PDF tasks
  sqlite/         # chinook.sqlite, sakila.sqlite (committed); superuser.sqlite (gitignored, build via script)
runs/             # Per-run JSON logs, markdown transcripts, latest-summary.json
runs/charts/      # PNG charts (written by app.tasks.report)
FINDINGS.md       # Auto-generated findings scaffold (written by app.tasks.report)
```

## Output

Each run writes:
- `runs/<timestamp>-<task>-<agent>.json` — structured result log
- `runs/<timestamp>-<task>-<agent>.md` — full conversation transcript
- `runs/latest-summary.json` — aggregate summary across all runs in session

Terminal output: per-run table, task comparison table, aggregate metrics table, per-difficulty success table. Multi-model runs also print a per-model × agent table.

## Task suite (48 tasks)

Organized by category and difficulty:

- **Engineering — easy/medium/hard**: single-file lookup, CSV/log filtering, cross-file reasoning, large-file scans
- **Non-engineering**: finance, HR, scheduling, email triage, recipe, travel
- **PDF Q&A (5 tasks, hard)**: extract answers from real PDF documents (Apple financials, research paper, LLM interview guide, multi-PDF cross-doc, recruitment analysis). Function agent uses `read_pdf`/`search_pdf`; CLI agent must discover its own technique (WinRT PDF+OCR, pdftotext, pdfplumber via python, etc.).
- **SQLite (5 tasks)**:
  - `sql_chinook_top_genre` (easy) — Chinook DB, single JOIN + GROUP BY
  - `sql_sakila_top_film` (medium) — Sakila DB, 3-table JOIN through inventory
  - `sql_sakila_top_customer` (medium) — Sakila DB, aggregate sum + ROUND
  - `sql_superuser_cooccurring_tag` (hard) — 2.7 GB superuser DB, parse pipe-delimited Tags column
  - `sql_superuser_body_search` (hard) — 2.7 GB superuser DB, COUNT(*) with LIKE scan of 1.2M Body fields

See `app/tasks/hybrid_tasks.py` for full definitions and expected answers.

## Evaluation

`app/tasks/evaluator.py` validates agent answers. Helpers:

- `contains_all(text, expected)` — strict, all keywords must match
- `contains_partial(text, expected, threshold=0.8)` — partial credit, passes if ≥ threshold of keywords match (used for multi-question PDF tasks so one wrong sub-answer doesn't tank the whole task)
- `contains_in_order` — sequence matters
- `contains_any` — at least one match

`validation_notes` on the result reports which keywords matched/missed.

## Adding tasks

1. Add a `BenchmarkTask` entry to `app/tasks/hybrid_tasks.py`
2. Add a validator function near the other validators in the same file
3. Add corresponding workspace fixture files to `workspace_data/` if needed
4. Update `app/workspace/setup_workspace.py` if the fixture needs deterministic generation

## Adding models

Set `OLLAMA_MODELS=model1,model2` in `.env` or pass `--models model1,model2` at runtime. The runner iterates models × agents × tasks automatically. Auth failures on one model are isolated — the runner skips remaining tasks for that model and continues with the next.

## Key design decisions

- **CLI agent has only `run_command`** — forces the model to compose PowerShell natively, no scaffolded reads
- **`read_file` is file-type-aware** — large files return previews with suggested ranges instead of dumping everything
- **`run_command` intercepts bare `Get-Content`/`cat`/`type`** — routed through the preview logic to prevent context floods
- **`query_sql` is read-only** — opens SQLite DBs in `mode=ro`, rejects anything not starting with SELECT/WITH/PRAGMA/EXPLAIN, hard row limit of 100
- **Tool outputs are escaped before Rich rendering** — prevents binary PDF/SQL content with `[...]` patterns from crashing the live transcript
- **Task-level error isolation** — exception in one task/agent doesn't kill the whole run; only auth errors halt the current model
- **Temperature=0** — deterministic runs; set in `.env`
