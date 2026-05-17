# Hybrid Agent Benchmark

This project benchmarks two hybrid-style agents on the same local workspace tasks and the same model settings.

- Function agent: `list_files`, `read_file`, `write_file`, `run_command`
- CLI agent: `run_command` only

The benchmark is intentionally centered on a small number of strong primitives rather than many task-shaped tools.

## Core tools

### Function agent

- `list_files(path='.')`
- `read_file(path, start_line=None, end_line=None)`
- `write_file(path, content)`
- `run_command(command)`

### CLI agent

- `run_command(command)`

## Runtime behavior

### `read_file`

`read_file` is file-type aware.

- small text/code/log/markdown files return full content
- large text-like files return a preview, total line count, returned range, and suggested next ranges
- explicit ranges return the requested line slice
- large slices are previewed and the full slice is saved to `.artifacts/`
- CSV files return headers, row count, and preview instead of a full dump
- JSON/YAML/XML are preview-first
- image/PDF/binary files return metadata only

### `run_command`

`run_command` executes a PowerShell command in the workspace directory.

- `cwd` is the benchmark workspace
- captures `stdout`, `stderr`, `exit_code`, and `duration_ms`
- enforces `BENCHMARK_COMMAND_TIMEOUT_SECONDS`
- truncates large output before sending it back to the model
- saves full output under `.artifacts/` when truncated
- intercepts simple file reads like `Get-Content file`, `cat file`, and `type file` and routes them through the file-aware preview logic

This is scoped for local benchmark use. It is not a hardened OS sandbox.

## Benchmark tasks

32 tasks across three difficulty levels, spanning both engineering and non-engineering agent work.

**Easy** (single file, one fact)
- `easy_config_lookup` — read two values from `config.json`
- `easy_count_app_errors` — count ERROR lines in `app.log`
- `easy_find_billing_api_files` — find which files contain the string `billing-api`
- `easy_list_csv_files` — list all `.csv` files in the workspace root

**Medium** (filter, aggregate, dedupe, sort)
- `focus_long_log_check` — count `database connection failed` errors in `huge.log`
- `medium_top_failure_reason` — most frequent failure reason in `failed_jobs.log`
- `medium_top_500_endpoint` — endpoint with the most HTTP 500s in `server.log`
- `medium_unique_customers` — distinct customer names in `customers.csv`
- `medium_top_revenue_country` — highest total revenue country in `sales.csv`

**Hard** (cross-file or deep-scan reasoning)
- `focus_deep_markdown_lookup` — find an env var deep inside a long markdown file
- `focus_csv_highest_value` — filter+max over a 5MB+ CSV
- `focus_csv_comparison` — compare two rows in a large CSV
- `hard_prod_staging_feature_diff` — find the one feature flag that differs between `configs/prod.env` and `configs/staging.env`
- `hard_incident_root_cause` — correlate `incident_notes.md` with `deployments.log`
- `hard_env_var_mismatch` — find an env var read by `src/cache.py` but missing from `configs/prod.env`
- `hard_correlated_alerts` — correlate `alerts.log` with `timeline.log`

**Non-engineering domains** (added to test broader agent work)

*Personal finance* — `finance_total_spend`, `finance_top_category` (over `expenses.csv`)

*Customer support* — `support_open_ticket_count`, `support_top_customer` (over `tickets.csv`)

*HR / org chart* — `hr_direct_reports_mark`, `hr_no_manager` (over `employees.csv`)

*Scheduling* — `meetings_count_on_march_02`, `meetings_double_booked` (over `meetings.csv`)

*Document summarization* — `minutes_facilitator`, `minutes_action_owners` (over `meeting_minutes.md`)

*Inventory / recipe* — `pantry_lowest_stock`, `recipe_missing_ingredient` (over `pantry.csv` + `recipe.md`)

*Travel planning* — `travel_nyc_boston_distance`, `travel_route_total` (over `distances.csv`)

*Email triage* — `inbox_urgent_count`, `inbox_outage_sender` (over `inbox.md`)

The workspace fixtures include:

- `huge.log`
- `deepgram_fixture_long.md`
- `industry_financial.csv`

## Setup

Copy `.env.example` to `.env` and set your model config.

```bash
cp .env.example .env
```

Important environment variables:

- `OLLAMA_API_KEY`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `BENCHMARK_MAX_TURNS`
- `BENCHMARK_LLM_CALL_PAUSE_SECONDS`
- `BENCHMARK_COMMAND_TIMEOUT_SECONDS`

Recommended start:

```env
OLLAMA_BASE_URL=https://ollama.com/api
OLLAMA_MODEL=glm-5:cloud
BENCHMARK_LLM_CALL_PAUSE_SECONDS=5
BENCHMARK_COMMAND_TIMEOUT_SECONDS=20
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Refresh workspace fixtures:

```bash
python -m app.workspace.setup_workspace --force
```

## Run the benchmark

Run both agents:

```bash
python -m app.tasks.runner --rebuild-workspace
```

Run one agent only:

```bash
python -m app.tasks.runner --agent function
python -m app.tasks.runner --agent cli
```

Run a subset by range:

```bash
python -m app.tasks.runner --task-range 2-4
```

Run selected task ids:

```bash
python -m app.tasks.runner --tasks focus_long_log_check focus_csv_highest_value
```

Run across multiple Ollama models (cross-model comparison):

```bash
python -m app.tasks.runner --models llama3.1,qwen2.5-coder,mistral
```

You can also set `OLLAMA_MODELS=llama3.1,qwen2.5-coder` in `.env` to make it the default. When more than one model is selected, an extra per-model × agent aggregate table is printed and `runs/latest-summary.json` includes an `aggregates_by_model` section.

Disable transcript streaming:

```bash
python -m app.tasks.runner --no-transcript
```

## Report

After a multi-model run completes, generate charts and a findings scaffold:

```bash
python -m app.tasks.report
```

Writes PNG charts to `runs/charts/` and a `FINDINGS.md` at the repo root with auto-derived headline observations (e.g. which agent won on tokens/success per model). Open `FINDINGS.md` in any markdown viewer to see charts inline.

## Output

The benchmark writes:

- per-run JSON logs in `runs/`
- per-run markdown transcripts in `runs/`
- latest summary at `runs/latest-summary.json`
- terminal tables for per-run, per-task comparison, and aggregate metrics
