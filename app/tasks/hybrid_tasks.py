from __future__ import annotations

import csv
from pathlib import Path

from app.models import BenchmarkTask
from app.tasks.evaluator import contains_all, normalize


SUITE_NAME = "hybrid"
CSV_FILENAME = "industry_financial.csv"



def _csv_path() -> Path:
    return Path(__file__).resolve().parents[2] / "workspace_data" / CSV_FILENAME



def _load_rows() -> list[dict[str, str]]:
    with _csv_path().open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))



def _to_number(value: str) -> float:
    return float(value)



def validate_long_log(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if ("yes" in normalized or "found" in normalized) and ("database connection failed" in normalized or "2" in normalized or "two" in normalized):
        return True, "confirmed database connection failures exist"
    return False, "expected confirmation that database connection failed errors exist"



def validate_deep_markdown(answer: str) -> tuple[bool, str]:
    return contains_all(answer, ["DG_STREAM_MODE", "live-captions"])



def validate_csv_highest_value(answer: str) -> tuple[bool, str]:
    rows = [
        row for row in _load_rows()
        if row["Year"] == "2024"
        and row["Industry_aggregation_NZSIOC"] == "Level 1"
        and row["Variable_code"] == "H01"
        and row["Industry_name_NZSIOC"] != "All industries"
        and row["Value"]
    ]
    winner = max(rows, key=lambda row: _to_number(row["Value"]))
    return contains_all(answer, [winner["Industry_name_NZSIOC"], winner["Value"]])



def validate_csv_comparison(answer: str) -> tuple[bool, str]:
    rows = [
        row for row in _load_rows()
        if row["Year"] == "2024"
        and row["Variable_code"] == "H36"
        and row["Industry_name_NZSIOC"] in {"All industries", "Agriculture, Forestry and Fishing"}
    ]
    by_name = {row["Industry_name_NZSIOC"]: row for row in rows}
    all_value = by_name["All industries"]["Value"]
    agriculture_value = by_name["Agriculture, Forestry and Fishing"]["Value"]
    larger = "Agriculture, Forestry and Fishing" if _to_number(agriculture_value) > _to_number(all_value) else "All industries"
    difference = str(int(abs(_to_number(agriculture_value) - _to_number(all_value))))
    return contains_all(answer, [all_value, agriculture_value, larger, difference])



def get_tasks() -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_id="focus_long_log_check",
            prompt="Investigate huge.log and determine whether there are any database connection failed errors. Report whether they exist and the count if you can confirm it.",
            validator=validate_long_log,
            notes="huge.log contains 2 database connection failed errors.",
            suite=SUITE_NAME,
        ),
        BenchmarkTask(
            task_id="focus_deep_markdown_lookup",
            prompt="Inspect deepgram_fixture_long.md. What environment variable enables live captions in the streaming example, and what value should it be set to?",
            validator=validate_deep_markdown,
            notes="Expected answer: DG_STREAM_MODE = live-captions.",
            suite=SUITE_NAME,
        ),
        BenchmarkTask(
            task_id="focus_csv_highest_value",
            prompt="Using industry_financial.csv, answer this: Among rows where Year = 2024, Industry_aggregation_NZSIOC = Level 1, Variable_code = H01, which industry has the highest Value, excluding the All industries row? Return the industry name and the value.",
            validator=validate_csv_highest_value,
            notes="Computed dynamically from the CSV at runtime.",
            suite=SUITE_NAME,
        ),
        BenchmarkTask(
            task_id="focus_csv_comparison",
            prompt="Using industry_financial.csv, compare these two rows: Row A has Year = 2024, Industry_name_NZSIOC = All industries, Variable_code = H36. Row B has Year = 2024, Industry_name_NZSIOC = Agriculture, Forestry and Fishing, Variable_code = H36. Return both values, which one is larger, and the difference.",
            validator=validate_csv_comparison,
            notes="Computed dynamically from the CSV at runtime.",
            suite=SUITE_NAME,
        ),
    ]
