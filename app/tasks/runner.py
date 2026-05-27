from __future__ import annotations

import argparse
import re
import sys
from dataclasses import asdict
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.agents.cli_agent import CliAgent
from app.agents.function_agent import FunctionAgent
from app.config import BenchmarkConfig
from app.logger import RunLogger, write_summary
from app.models import AgentRunResult, BenchmarkTask
from app.ollama_client import OllamaClient
from app.tasks.hybrid_tasks import SUITE_NAME, get_tasks
from app.tasks.runner_helpers import aggregate_by_difficulty, aggregate_by_model_agent, aggregate_metrics
from app.tools.hybrid_tools import HybridCliToolSuite, HybridFunctionToolSuite
from app.workspace import WorkspaceManager
from app.workspace.setup_workspace import create_workspace


console = Console()



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the hybrid benchmark.")
    parser.add_argument("--agent", choices=["function", "cli", "both"], default="both")
    parser.add_argument("--models", help="Comma-separated Ollama model names; overrides OLLAMA_MODELS/OLLAMA_MODEL.")
    parser.add_argument("--tasks", nargs="*", help="Optional task ids to run.")
    parser.add_argument("--task-range", help="Optional 1-based inclusive task range like 2-4.")
    parser.add_argument("--rebuild-workspace", action="store_true", help="Recreate deterministic workspace files before running.")
    parser.add_argument("--no-transcript", action="store_true", help="Disable live transcript printing while tasks run.")
    return parser.parse_args()



def parse_task_range(range_text: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)-(\d+)", range_text.strip())
    if not match:
        raise ValueError("task range must look like 2-4")
    start = int(match.group(1))
    end = int(match.group(2))
    if start < 1 or end < start:
        raise ValueError("task range must be positive and ascending")
    return start, end



def select_tasks(all_tasks: list[BenchmarkTask], selected_ids: list[str] | None, task_range: str | None) -> list[BenchmarkTask]:
    selected = list(all_tasks)
    if task_range:
        start, end = parse_task_range(task_range)
        if end > len(selected):
            raise ValueError(f"task range {task_range} exceeds available task count {len(selected)}")
        selected = selected[start - 1 : end]
    if selected_ids:
        wanted = set(selected_ids)
        selected = [task for task in selected if task.task_id in wanted]
        missing = wanted - {task.task_id for task in selected}
        if missing:
            raise ValueError(f"unknown task ids in selected scope: {', '.join(sorted(missing))}")
    return selected



def build_agents(client: OllamaClient, config: BenchmarkConfig, workspace: WorkspaceManager, agent_choice: str) -> list[Any]:
    function_agent = FunctionAgent(client, config, HybridFunctionToolSuite(workspace, config).build_tools())
    cli_agent = CliAgent(client, config, HybridCliToolSuite(workspace, config).build_tools())
    if agent_choice == "function":
        return [function_agent]
    if agent_choice == "cli":
        return [cli_agent]
    return [function_agent, cli_agent]



def print_run_table(results: list[AgentRunResult]) -> None:
    table = Table(title="Per-run Results")
    table.add_column("Task")
    table.add_column("Agent")
    table.add_column("Success")
    table.add_column("Tool Calls")
    table.add_column("LLM Turns")
    table.add_column("Tokens")
    table.add_column("Elapsed (ms)")
    table.add_column("Notes")
    for result in results:
        table.add_row(
            result.task_id,
            result.agent_type,
            "yes" if result.success else "no",
            str(result.tool_calls),
            str(result.llm_turns),
            str(result.total_tokens),
            str(result.elapsed_ms),
            result.validation_notes,
        )
    console.print(table)



def print_comparison_table(results: list[AgentRunResult]) -> None:
    by_task: dict[tuple[str, str], dict[str, AgentRunResult]] = {}
    for result in results:
        by_task.setdefault((result.model_name, result.task_id), {})[result.agent_type] = result

    table = Table(title="Task Comparison")
    table.add_column("Model")
    table.add_column("Task")
    table.add_column("Function Agent")
    table.add_column("CLI Agent")
    table.add_column("Notes")
    for (model_name, task_id), entries in by_task.items():
        function_result = entries.get("function")
        cli_result = entries.get("cli")
        function_label = "-"
        cli_label = "-"
        notes = []
        if function_result:
            function_label = (
                f"{'pass' if function_result.success else 'fail'} "
                f"({function_result.tool_calls} tools, {function_result.llm_turns} turns, {function_result.total_tokens} tok)"
            )
            notes.append(f"function: {function_result.validation_notes}")
        if cli_result:
            cli_label = (
                f"{'pass' if cli_result.success else 'fail'} "
                f"({cli_result.tool_calls} tools, {cli_result.llm_turns} turns, {cli_result.total_tokens} tok)"
            )
            notes.append(f"cli: {cli_result.validation_notes}")
        table.add_row(model_name, task_id, function_label, cli_label, " | ".join(notes))
    console.print(table)



def print_aggregate_table(results: list[AgentRunResult]) -> dict[str, dict[str, float]]:
    aggregates = aggregate_metrics(results)
    table = Table(title="Aggregate Metrics")
    table.add_column("Agent")
    table.add_column("Runs")
    table.add_column("Success Rate")
    table.add_column("Avg Tool Calls")
    table.add_column("Avg LLM Turns")
    table.add_column("Avg Tokens")
    table.add_column("Total Tokens")
    table.add_column("Avg Elapsed (ms)")
    for agent_type, metrics in aggregates.items():
        table.add_row(
            agent_type,
            str(int(metrics["runs"])),
            f"{metrics['success_rate']:.2%}",
            f"{metrics['avg_tool_calls']:.2f}",
            f"{metrics['avg_llm_turns']:.2f}",
            f"{metrics['avg_total_tokens']:.2f}",
            str(int(metrics["sum_total_tokens"])),
            f"{metrics['avg_elapsed_ms']:.2f}",
        )
    console.print(table)
    return aggregates



DIFFICULTY_ORDER = ["easy", "medium", "hard"]


def print_difficulty_table(results: list[AgentRunResult]) -> None:
    by_difficulty = aggregate_by_difficulty(results)
    table = Table(title="Success Rate by Difficulty")
    table.add_column("Difficulty")
    table.add_column("Agent")
    table.add_column("Runs")
    table.add_column("Success Rate")
    table.add_column("Avg Tool Calls")
    table.add_column("Avg Tokens")
    for difficulty in DIFFICULTY_ORDER:
        if difficulty not in by_difficulty:
            continue
        for agent_type, metrics in by_difficulty[difficulty].items():
            table.add_row(
                difficulty,
                agent_type,
                str(int(metrics["runs"])),
                f"{metrics['success_rate']:.2%}",
                f"{metrics['avg_tool_calls']:.2f}",
                f"{metrics['avg_total_tokens']:.2f}",
            )
    console.print(table)


def print_model_table(by_model: dict[str, dict[str, dict[str, float]]]) -> None:
    table = Table(title="Per-Model x Agent Aggregates")
    table.add_column("Model")
    table.add_column("Agent")
    table.add_column("Runs")
    table.add_column("Success Rate")
    table.add_column("Avg Tool Calls")
    table.add_column("Avg LLM Turns")
    table.add_column("Avg Tokens")
    table.add_column("Avg Elapsed (ms)")
    for model_name, by_agent in by_model.items():
        for agent_type, metrics in by_agent.items():
            table.add_row(
                model_name,
                agent_type,
                str(int(metrics["runs"])),
                f"{metrics['success_rate']:.2%}",
                f"{metrics['avg_tool_calls']:.2f}",
                f"{metrics['avg_llm_turns']:.2f}",
                f"{metrics['avg_total_tokens']:.2f}",
                f"{metrics['avg_elapsed_ms']:.2f}",
            )
    console.print(table)



def main() -> None:
    args = parse_args()
    config = BenchmarkConfig.load()
    if config.requires_api_key and not config.ollama_api_key:
        raise SystemExit("OLLAMA_API_KEY is required when using Ollama Cloud. Copy .env.example to .env and set the key.")

    create_workspace(config.workspace_root, force=args.rebuild_workspace)
    workspace = WorkspaceManager(config.workspace_root)
    tasks = select_tasks(get_tasks(), args.tasks, args.task_range)
    client = OllamaClient(config)

    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    elif config.ollama_models:
        models = list(config.ollama_models)
    else:
        models = [config.ollama_model]

    results: list[AgentRunResult] = []
    skipped_models: list[tuple[str, str]] = []
    for model_name in models:
        config.ollama_model = model_name
        console.rule(f"model: {model_name}")
        model_had_any_result = False
        for task in tasks:
            agents = build_agents(client, config, workspace, args.agent)
            for agent in agents:
                logger = RunLogger(
                    config.runs_root,
                    task.task_id,
                    agent.agent_type,
                    config.ollama_model,
                    console=console,
                    stream_transcript=not args.no_transcript,
                )
                logger.start_task(task.prompt, task.notes)
                try:
                    result = agent.run_task(task, logger)
                    json_log_path, transcript_path = logger.finalize(
                        {
                            "task_prompt": task.prompt,
                            "task_notes": task.notes,
                            "task_suite": SUITE_NAME,
                            "result": asdict(result),
                        }
                    )
                    result.log_path = str(json_log_path)
                    result.transcript_path = str(transcript_path)
                    model_had_any_result = True
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    console.print(f"[yellow]task {task.task_id}/{agent.agent_type} failed: {escape(reason)}[/yellow]")
                    result = AgentRunResult(
                        task_id=task.task_id,
                        agent_type=agent.agent_type,
                        model_name=model_name,
                        difficulty=task.difficulty,
                        success=False,
                        validation_notes=reason,
                        final_answer="",
                        llm_turns=0,
                        tool_calls=0,
                        elapsed_ms=0,
                        error_reason=reason,
                    )
                    # If it's an auth error, no point continuing with this model
                    if "401" in reason or "403" in reason or "AuthError" in reason:
                        console.print(f"[yellow]auth failure on model {escape(model_name)}, skipping remaining tasks.[/yellow]")
                        skipped_models.append((model_name, reason))
                        results.append(result)
                        break
                results.append(result)
            else:
                continue
            break  # auth failure inner break propagates out of task loop

    if results:
        print_run_table(results)
        print_comparison_table(results)
        aggregates = print_aggregate_table(results)
        print_difficulty_table(results)
    else:
        aggregates = {}
        console.print("[red]No results to report (all models failed).[/red]")
    by_model = aggregate_by_model_agent(results)
    if len(models) > 1 and results:
        print_model_table(by_model)

    summary_payload = {
        "models": models,
        "skipped_models": [{"model": m, "reason": r} for m, r in skipped_models],
        "base_url": config.ollama_base_url,
        "suite": SUITE_NAME,
        "task_range": args.task_range,
        "results": [asdict(result) for result in results],
        "aggregates": aggregates,
        "aggregates_by_model": by_model,
    }
    if skipped_models:
        console.print("\n[yellow]Skipped models:[/yellow]")
        for model_name, reason in skipped_models:
            console.print(f"  - {escape(model_name)}: {escape(reason)}")
    summary_path = config.runs_root / "latest-summary.json"
    write_summary(summary_path, summary_payload)
    console.print(f"\nSummary written to {summary_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        console.print(f"[red]Benchmark failed:[/red] {escape(str(exc))}")
        sys.exit(1)
