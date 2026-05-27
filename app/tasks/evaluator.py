from __future__ import annotations

import re
from typing import Iterable, Sequence


DEFAULT_CONFIG_TEXT = '{"mode":"default","timeout":30,"retries":3}'



def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())



def contains_all(text: str, expected: Iterable[str]) -> tuple[bool, str]:
    normalized = normalize(text)
    missing = [item for item in expected if normalize(item) not in normalized]
    if missing:
        return False, f"missing expected substrings: {', '.join(missing)}"
    return True, "matched expected substrings"



def contains_partial(text: str, expected: Iterable[str], threshold: float = 0.8) -> tuple[bool, str]:
    items = list(expected)
    normalized = normalize(text)
    missing = [item for item in items if normalize(item) not in normalized]
    matched = len(items) - len(missing)
    ratio = matched / len(items) if items else 1.0
    note = f"{matched}/{len(items)} correct"
    if missing:
        note += f"; missing: {', '.join(missing)}"
    return ratio >= threshold, note


def contains_any(text: str, expected: Iterable[str]) -> bool:
    normalized = normalize(text)
    return any(normalize(item) in normalized for item in expected)



def llm_judge(
    answer: str,
    qa_pairs: Sequence[tuple[str, str]],
    *,
    threshold: int | None = None,
    judge_model: str | None = None,
) -> tuple[bool, str]:
    """Use an LLM call to grade a multi-part answer against gold answers.

    For each (question, gold_answer) pair, the judge decides whether the agent's
    answer captures the key facts. The task passes when the number of correct
    questions meets `threshold` (defaults to a strict majority, i.e. ceil(N/2)+1).
    """
    from app.config import BenchmarkConfig
    from app.ollama_client import OllamaClient

    total = len(qa_pairs)
    if threshold is None:
        threshold = (total // 2) + 1

    rubric_lines: list[str] = []
    for idx, (question, gold) in enumerate(qa_pairs, 1):
        rubric_lines.append(f"Question {idx}: {question}")
        rubric_lines.append(f"Gold answer {idx}: {gold}")
        rubric_lines.append("")
    rubric = "\n".join(rubric_lines).strip()

    judge_prompt = (
        "You are a strict but fair evaluator. For each numbered question below, decide whether "
        "the agent's answer captures the KEY FACTS of the gold answer. Paraphrasing is fine; "
        "the agent does not need identical wording, but the substantive facts (names, events, "
        "specific details) must be present. If a question has multiple sub-parts, all sub-parts "
        "must be substantively correct for PASS.\n\n"
        f"{rubric}\n\n"
        "Agent's full answer:\n"
        '"""\n'
        f"{answer}\n"
        '"""\n\n'
        "Respond with EXACTLY one line per question in this format (no extra commentary):\n"
        "Q1: PASS\n"
        "Q2: FAIL - <one short reason>\n"
        "...\n\n"
        f"After the per-question lines, end with a single line:\nTOTAL: <count> / {total}"
    )

    try:
        config = BenchmarkConfig.load()
        client = OllamaClient(config)
        response, _, _ = client.chat(
            [{"role": "user", "content": judge_prompt}],
            model=judge_model or config.ollama_model,
        )
        verdict = (response.message.content or "").strip()
    except Exception as exc:
        return False, f"judge call failed: {type(exc).__name__}: {exc}"

    pass_count = len(re.findall(r"(?mi)^Q\d+\s*[:\-]\s*PASS\b", verdict))
    fail_count = len(re.findall(r"(?mi)^Q\d+\s*[:\-]\s*FAIL\b", verdict))
    success = pass_count >= threshold
    note = f"judge: {pass_count}/{total} pass (need {threshold})"
    if fail_count:
        note += f", {fail_count} fail"
    return success, note


def contains_in_order(text: str, expected: Iterable[str]) -> tuple[bool, str]:
    normalized = normalize(text)
    cursor = 0
    for item in expected:
        needle = normalize(item)
        position = normalized.find(needle, cursor)
        if position == -1:
            return False, f"expected in-order substring not found: {item}"
        cursor = position + len(needle)
    return True, "matched expected substrings in order"
