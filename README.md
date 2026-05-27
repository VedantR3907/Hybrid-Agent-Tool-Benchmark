# Hybrid Agent Tool Benchmark

Benchmarks two agent styles on the same local workspace tasks using the same model and settings:

- **Function agent** — structured tools: `list_files`, `read_file`, `write_file`, `run_command`, `read_pdf`, `search_pdf`, `query_sql`
- **CLI agent** — single tool: `run_command` (PowerShell, workspace-scoped). Must compose everything natively — PDF extraction via WinRT or pdftotext, SQL via `python -c "import sqlite3..."`, etc.

Goal: quantify the tradeoff between rich function-calling primitives vs raw CLI fluency — success rate, token cost, tool call count, latency — across a 49-task suite and multiple models.

## Tools

### Function agent

| Tool | Behavior |
|---|---|
| `list_files(path)` | Workspace-relative directory listing |
| `read_file(path, start_line?, end_line?)` | File-type-aware; previews large files with suggested next ranges |
| `write_file(path, content)` | Text writes inside the workspace |
| `run_command(command)` | PowerShell command in the workspace root |
| `read_pdf(path, pages)` | Extract text from a page range (`'1-5'` or `'3'`) |
| `search_pdf(path, keyword, context_chars?)` | Locate keyword across all pages, returns hits + snippets |
| `query_sql(path, sql)` | Read-only SQLite query (SELECT/WITH/PRAGMA/EXPLAIN). 100-row limit, opened `mode=ro` |

### CLI agent

| Tool | Behavior |
|---|---|
| `run_command(command)` | Any PowerShell command. No restrictions beyond the same output/timeout truncation as the function agent. |

The CLI agent must discover PDF/SQL techniques on its own. The system prompt mentions Python's `sqlite3` module as a fallback when `sqlite3.exe` is not installed, but does not hint at WinRT or pdftotext for PDFs.

## Runtime behavior

### `read_file`

- Small text/code/log/markdown files return full content
- Large text-like files return a preview, total line count, returned range, and suggested next ranges
- Explicit ranges return the requested line slice; oversized slices are previewed and the full slice is saved under `.artifacts/`
- CSV files return headers, row count, and a preview instead of a full dump
- JSON / YAML / XML are preview-first
- Image / PDF / SQLite / other binary files return metadata only

### `run_command`

- `cwd` is the benchmark workspace
- Captures `stdout`, `stderr`, `exit_code`, `duration_ms`
- Enforces `BENCHMARK_COMMAND_TIMEOUT_SECONDS`
- Truncates large output and saves the full content under `.artifacts/`
- Intercepts bare `Get-Content`, `cat`, `type` and routes them through the file-aware preview logic to avoid context floods
- Rejects nested PowerShell wrappers like `powershell -Command "..."` with a clear error

### `query_sql`

- Opens the database in `file:...?mode=ro` so writes are physically impossible
- Rejects anything not starting with `SELECT / WITH / PRAGMA / EXPLAIN`
- Hard caps result at 100 rows + truncates JSON payload above `BENCHMARK_OUTPUT_CHAR_LIMIT`

Scoped for local benchmark use. Not a hardened OS sandbox.

## Task suite (49 tasks)

| Category | Count | Difficulty mix |
|---|---|---|
| Engineering — file lookup, log parsing, CSV reasoning | 16 | easy / medium / hard |
| Non-engineering — finance, HR, scheduling, recipe, travel, email triage | 22 | mostly easy/medium |
| **PDF Q&A** | 6 | hard |
| **SQLite** | 5 | 1 easy, 2 medium, 2 hard |

### PDF tasks

| Task ID | Source | Notes |
|---|---|---|
| `pdf_apple_financials` | `apple_statement.pdf` | Apple Q2 2025 financials |
| `pdf_research_paper_qa` | `research_paper.pdf` | FAQ-Gen NLP paper Q&A |
| `pdf_llm_interview_qa` | `llm_interview.pdf` | LLM concepts |
| `pdf_multi_ai_docs` | both research PDFs | Cross-document reasoning |
| `pdf_recruitment_qa` | `recruitment_analysis.pdf` | Emotion-detection doc |
| `pdf_harry_potter_plot` | `harry_potter_5.pdf` (891 pages) | 5 very-hard plot questions, **LLM-as-judge** evaluation |

### SQLite tasks

| Task ID | DB | Difficulty driver |
|---|---|---|
| `sql_chinook_top_genre` | chinook.sqlite (1 MB) | Single JOIN + GROUP BY |
| `sql_sakila_top_film` | sakila.sqlite (5 MB) | 3-table JOIN through inventory |
| `sql_sakila_top_customer` | sakila.sqlite | Aggregate + ROUND |
| `sql_superuser_cooccurring_tag` | superuser.sqlite (2.7 GB) | Parse pipe-delimited Tags column; precomputed counts table can't help |
| `sql_superuser_body_search` | superuser.sqlite | Full LIKE scan of 1.2M Body fields — must use `COUNT(*)`, not `SELECT *` |

`chinook.sqlite` and `sakila.sqlite` ship in the repo. `superuser.sqlite` is gitignored (2.7 GB) — build it locally from a Stack Exchange XML dump (see Setup).

## Evaluation

Each task ships a validator. Helpers in `app/tasks/evaluator.py`:

| Helper | When to use |
|---|---|
| `contains_all(text, expected)` | Strict — every keyword must match |
| `contains_partial(text, expected, threshold=0.8)` | Partial credit — passes when ≥ threshold of keywords match. Used for multi-sub-question PDF/SQL tasks so a single wrong sub-answer doesn't tank the score |
| `contains_in_order(text, expected)` | Sequence must be preserved |
| `contains_any(text, expected)` | At least one match |
| `llm_judge(answer, qa_pairs, threshold)` | Open-ended grading. Calls an LLM with (question, gold answer, agent answer) per sub-question. Used for the Harry Potter task |

`validation_notes` on each result reports which keywords matched / which sub-questions passed.

## Setup

```powershell
# 1. Configure
cp .env.example .env       # set OLLAMA_API_KEY (and optionally OLLAMA_API_KEY_SECOND, OLLAMA_MODELS)

# 2. Install
pip install -r requirements.txt

# 3. Refresh workspace fixtures
python -m app.workspace.setup_workspace --force

# 4. (Optional) Build the 2.7 GB Stack Exchange DB used by the hard SQL tasks.
#    Download a site dump from https://archive.org/details/stackexchange (e.g. superuser.com.7z),
#    extract it, then:
python scripts/build_superuser_db.py <path-to-extracted-xml-dir> workspace_data/sqlite/superuser.sqlite
```

### Environment variables (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_API_KEY` | — | Required for Ollama Cloud |
| `OLLAMA_API_KEY_SECOND` | — | Optional fallback key, auto-used on 401/403 |
| `OLLAMA_BASE_URL` | `https://ollama.com/api` | API endpoint |
| `OLLAMA_MODEL` | `glm-5:cloud` | Default model |
| `OLLAMA_MODELS` | — | Comma-separated list for multi-model runs |
| `OLLAMA_TEMPERATURE` | `0` | Deterministic by default |
| `BENCHMARK_MAX_TURNS` | `30` | Cap on agentic turns per task |
| `BENCHMARK_LLM_CALL_PAUSE_SECONDS` | `5` | Inter-call sleep to respect rate limits |
| `BENCHMARK_COMMAND_TIMEOUT_SECONDS` | `20` | Per-command timeout |
| `BENCHMARK_OUTPUT_CHAR_LIMIT` | `4000` | Truncate tool output above this many chars |
| `BENCHMARK_OUTPUT_LINE_LIMIT` | `120` | Truncate tool output above this many lines |

## Run

```powershell
# Both agents, all tasks, fresh workspace
python -m app.tasks.runner --rebuild-workspace

# One agent only
python -m app.tasks.runner --agent function
python -m app.tasks.runner --agent cli

# Subset by 1-based range
python -m app.tasks.runner --task-range 2-4

# Specific task ids
python -m app.tasks.runner --tasks pdf_apple_financials sql_chinook_top_genre

# Multi-model
python -m app.tasks.runner --models gpt-oss:120b,glm-5:cloud,qwen2.5-coder

# Quiet (no live transcript)
python -m app.tasks.runner --no-transcript
```

Auth failures on a single model are isolated — the runner records skipped status, moves on to the next model, and prints a summary of skipped models at the end.

## Report

After a multi-model run, generate charts and a findings scaffold:

```powershell
python -m app.tasks.report
```

Writes PNG charts to `runs/charts/` and `FINDINGS.md` at the repo root with headline observations (which agent won on tokens / success per model, per-difficulty breakdowns, etc.). Charts are referenced from the markdown so it renders inline in any markdown viewer.

## Output

Each task run writes:

- `runs/<timestamp>-<task>-<agent>-<model>.json` — structured result log
- `runs/<timestamp>-<task>-<agent>-<model>.transcript.md` — full conversation transcript
- `runs/latest-summary.json` — aggregate summary across all runs in the session

Terminal output: per-run table, task comparison table, aggregate metrics, per-difficulty breakdown, and (multi-model) a per-model × agent table.

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
  build_superuser_db.py   # Stream-converts a Stack Exchange XML dump into a single SQLite DB

workspace_data/   # Benchmark workspace (files agents operate on)
  pdfs/           # PDF fixtures
  sqlite/         # chinook.sqlite, sakila.sqlite (committed); superuser.sqlite (gitignored)
runs/             # Per-run JSON logs, markdown transcripts, latest-summary.json
runs/charts/      # PNG charts (written by app.tasks.report)
FINDINGS.md       # Auto-generated findings scaffold
```

## Key design decisions

- **CLI agent has only `run_command`** — forces the model to compose PowerShell natively, no scaffolded reads
- **`read_file` is file-type-aware** — large files return previews with suggested ranges, never dump raw
- **`run_command` intercepts bare `Get-Content`/`cat`/`type`** — routed through the same preview logic to prevent context floods
- **`query_sql` is read-only** — opens SQLite DBs in `mode=ro`, row limit 100, char limit on output
- **Tool output and exception messages are Rich-escaped** — binary blobs with `[...]` patterns can't crash the live transcript
- **Task-level error isolation** — one bad task does not kill the model run; only auth failures abort the current model
- **Temperature = 0** — deterministic runs across re-runs of the same model
