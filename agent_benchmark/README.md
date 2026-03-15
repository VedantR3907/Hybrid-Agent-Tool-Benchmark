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

The benchmark currently runs four focused tasks:

1. `focus_long_log_check`
2. `focus_deep_markdown_lookup`
3. `focus_csv_highest_value`
4. `focus_csv_comparison`

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

Disable transcript streaming:

```bash
python -m app.tasks.runner --no-transcript
```

## Output

The benchmark writes:

- per-run JSON logs in `runs/`
- per-run markdown transcripts in `runs/`
- latest summary at `runs/latest-summary.json`
- terminal tables for per-run, per-task comparison, and aggregate metrics
