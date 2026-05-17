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



EXISTENCE_PHRASES = (
    "yes", "found", "there are", "there is", "exist", "present", "confirmed",
    "detected", "identified", "occurrences", "occurrence", "matches", "match",
)
NEGATIVE_PHRASES = (
    "no database connection failed", "none found", "no occurrences",
    "no matches", "did not find", "no such errors", "no errors",
)
COUNT_PHRASES = ("2", "two")


def validate_long_log(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if any(phrase in normalized for phrase in NEGATIVE_PHRASES):
        return False, "answer claims no database connection failed errors exist; expected 2"
    has_existence_claim = any(phrase in normalized for phrase in EXISTENCE_PHRASES)
    has_correct_count = any(phrase in normalized for phrase in COUNT_PHRASES)
    if has_existence_claim and has_correct_count:
        return True, "confirmed database connection failures exist with correct count"
    if not has_correct_count:
        return False, "expected the correct count (2) in the answer"
    return False, "expected an explicit confirmation that the errors exist"



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



# ---------- New task validators (added to extend the benchmark) ----------

def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = normalize(text)
    return any(p in normalized for p in phrases)


def validate_config_lookup(answer: str) -> tuple[bool, str]:
    return contains_all(answer, ["45", "5"])


def validate_count_app_errors(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "6" in normalized or "six" in normalized:
        return True, "correct error count"
    return False, "expected 6 ERROR lines in app.log"


def validate_find_billing_api_files(answer: str) -> tuple[bool, str]:
    return contains_all(answer, ["incident_notes.md", "alerts.log", "deployments.log"])


def validate_list_csv_files(answer: str) -> tuple[bool, str]:
    return contains_all(answer, ["sales.csv", "customers.csv", "jobs.csv", "industry_financial.csv"])


def validate_top_failure_reason(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "timeout" not in normalized:
        return False, "expected 'timeout' as top failure reason"
    if "3" not in normalized and "three" not in normalized:
        return False, "expected count of 3 timeout failures"
    return True, "correct top failure reason and count"


def validate_top_500_endpoint(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "/api/payments/charge" not in normalized and "payments/charge" not in normalized:
        return False, "expected /api/payments/charge as top 500 endpoint"
    if "6" not in normalized and "six" not in normalized:
        return False, "expected count of 6 errors"
    return True, "correct top 500 endpoint and count"


def validate_unique_customers(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "5" in normalized or "five" in normalized:
        return True, "correct unique customer count"
    return False, "expected 5 unique customers in customers.csv"


def validate_top_revenue_country(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "india" not in normalized:
        return False, "expected India as top revenue country"
    if "6065" not in normalized:
        return False, "expected total revenue 6065"
    return True, "correct top revenue country and total"


def validate_prod_staging_feature_diff(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "feature_billing_v2" not in normalized:
        return False, "expected FEATURE_BILLING_V2 as the differing flag"
    if "true" not in normalized:
        return False, "expected the prod value to be true"
    return True, "correct differing feature flag and prod value"


def validate_incident_root_cause(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "billing-api" not in normalized:
        return False, "expected billing-api as the suspected service"
    return True, "correct service identified as incident cause"


def validate_env_var_mismatch(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "redis_host" not in normalized:
        return False, "expected REDIS_HOST as the missing env var"
    return True, "correct missing env var identified"


def validate_correlated_alerts(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "billing-worker" not in normalized:
        return False, "expected billing-worker as the failing service before alerts fired"
    return True, "correct correlation between timeline.log and alerts.log"


# ---------- Non-programming domain validators ----------

def validate_expenses_total(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "636.74" in normalized or "636.7" in normalized:
        return True, "correct total"
    return False, "expected total of 636.74"


def validate_expenses_top_category(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "groceries" not in normalized:
        return False, "expected groceries as top category"
    if "212.8" not in normalized and "212.80" not in normalized:
        return False, "expected groceries total of 212.80"
    return True, "correct top category and total"


def validate_tickets_open_count(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "5" in normalized or "five" in normalized:
        return True, "correct open ticket count"
    return False, "expected 5 open tickets"


def validate_tickets_top_customer(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "alice" not in normalized:
        return False, "expected Alice as top customer"
    if "4" not in normalized and "four" not in normalized:
        return False, "expected Alice with 4 tickets"
    return True, "correct top customer and count"


def validate_hr_direct_reports(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "2" not in normalized and "two" not in normalized:
        return False, "expected 2 direct reports for Mark VP Eng"
    return True, "correct direct report count"


def validate_hr_no_manager(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "sarah" not in normalized:
        return False, "expected Sarah CEO as the employee with no manager"
    return True, "correct employee identified"


def validate_meetings_count_on_date(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "3" in normalized or "three" in normalized:
        return True, "correct meeting count on 2026-03-02"
    return False, "expected 3 meetings on 2026-03-02"


def validate_meetings_double_booked(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "alice" not in normalized:
        return False, "expected alice as the double-booked attendee"
    return True, "correct double-booked attendee"


def validate_minutes_facilitator(answer: str) -> tuple[bool, str]:
    return contains_all(answer, ["Sarah", "Chen"])


def validate_minutes_action_owners(answer: str) -> tuple[bool, str]:
    return contains_all(answer, ["Mark", "Lisa", "Tom"])


def validate_pantry_lowest_stock(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "yeast" not in normalized:
        return False, "expected yeast as the lowest stock item"
    return True, "correct lowest stock item"


def validate_recipe_missing_ingredient(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "cocoa" not in normalized:
        return False, "expected cocoa as the missing ingredient"
    return True, "correct missing ingredient"


def validate_distance_lookup(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "215" not in normalized:
        return False, "expected distance of 215 miles between NYC and Boston"
    return True, "correct distance"


def validate_route_total(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "875" not in normalized:
        return False, "expected total route distance of 875 miles"
    return True, "correct route total"


def validate_inbox_urgent_count(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "3" in normalized or "three" in normalized:
        return True, "correct urgent email count"
    return False, "expected 3 urgent emails"


def validate_inbox_outage_sender(answer: str) -> tuple[bool, str]:
    normalized = normalize(answer)
    if "client@acme.com" not in normalized and "acme.com" not in normalized:
        return False, "expected client@acme.com as the sender about production outage"
    return True, "correct sender identified"


def get_tasks() -> list[BenchmarkTask]:
    return [
        # ---- original 4 ----
        BenchmarkTask(
            task_id="focus_long_log_check",
            prompt=(
                "Investigate huge.log for lines containing the phrase 'database connection failed'. "
                "Answer in two short lines: "
                "Line 1: 'Exists: yes' or 'Exists: no'. "
                "Line 2: 'Count: <integer>'. "
                "Base both lines strictly on observed evidence from the file."
            ),
            validator=validate_long_log,
            notes="huge.log contains 2 database connection failed errors.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        BenchmarkTask(
            task_id="focus_deep_markdown_lookup",
            prompt="Inspect deepgram_fixture_long.md. What environment variable enables live captions in the streaming example, and what value should it be set to?",
            validator=validate_deep_markdown,
            notes="Expected answer: DG_STREAM_MODE = live-captions.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        BenchmarkTask(
            task_id="focus_csv_highest_value",
            prompt="Using industry_financial.csv, answer this: Among rows where Year = 2024, Industry_aggregation_NZSIOC = Level 1, Variable_code = H01, which industry has the highest Value, excluding the All industries row? Return the industry name and the value.",
            validator=validate_csv_highest_value,
            notes="Computed dynamically from the CSV at runtime.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        BenchmarkTask(
            task_id="focus_csv_comparison",
            prompt="Using industry_financial.csv, compare these two rows: Row A has Year = 2024, Industry_name_NZSIOC = All industries, Variable_code = H36. Row B has Year = 2024, Industry_name_NZSIOC = Agriculture, Forestry and Fishing, Variable_code = H36. Return both values, which one is larger, and the difference.",
            validator=validate_csv_comparison,
            notes="Computed dynamically from the CSV at runtime.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        # ---- EASY (single file, single fact) ----
        BenchmarkTask(
            task_id="easy_config_lookup",
            prompt=(
                "Read config.json in the workspace root. "
                "Answer in two lines: "
                "Line 1: 'timeout: <value>'. "
                "Line 2: 'retries: <value>'."
            ),
            validator=validate_config_lookup,
            notes="config.json has timeout=45, retries=5.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="easy_count_app_errors",
            prompt=(
                "Count how many lines in app.log contain the level 'ERROR'. "
                "Answer with exactly one line: 'Count: <integer>'."
            ),
            validator=validate_count_app_errors,
            notes="app.log contains 6 ERROR lines.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="easy_find_billing_api_files",
            prompt=(
                "Search every file in the workspace root and the configs/ and src/ directories for the literal string 'billing-api'. "
                "Return the list of filenames (just the file names, comma-separated) that contain it."
            ),
            validator=validate_find_billing_api_files,
            notes="incident_notes.md, alerts.log, deployments.log contain 'billing-api'.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="easy_list_csv_files",
            prompt=(
                "List every file in the workspace root (top level only) whose name ends with .csv. "
                "Return the filenames as a comma-separated list."
            ),
            validator=validate_list_csv_files,
            notes="sales.csv, customers.csv, jobs.csv, industry_financial.csv",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        # ---- MEDIUM (filter / aggregate / dedupe) ----
        BenchmarkTask(
            task_id="medium_top_failure_reason",
            prompt=(
                "Read failed_jobs.log. Each line has a 'reason=<value>' field. "
                "Identify the most frequent reason and how many times it appears. "
                "Answer in two lines: 'Reason: <value>' and 'Count: <integer>'."
            ),
            validator=validate_top_failure_reason,
            notes="timeout appears 3 times (most frequent).",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        BenchmarkTask(
            task_id="medium_top_500_endpoint",
            prompt=(
                "Read server.log. Find which endpoint path returned HTTP 500 the most times. "
                "Answer in two lines: 'Endpoint: <path>' and 'Count: <integer>'."
            ),
            validator=validate_top_500_endpoint,
            notes="/api/payments/charge had 6 occurrences of 500.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        BenchmarkTask(
            task_id="medium_unique_customers",
            prompt=(
                "Read customers.csv. How many distinct customer names appear in the 'name' column? "
                "Answer with exactly one line: 'Count: <integer>'."
            ),
            validator=validate_unique_customers,
            notes="5 unique names: Alex Stone, Mia Chen, Raj Patel, Sam Ortiz, Lina Park.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        BenchmarkTask(
            task_id="medium_top_revenue_country",
            prompt=(
                "Read sales.csv. Sum the revenue per country across all quarters and identify the country with the highest total. "
                "Answer in two lines: 'Country: <name>' and 'Total: <integer>'."
            ),
            validator=validate_top_revenue_country,
            notes="India has the highest total revenue (6065).",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        # ---- HARD (cross-file reasoning) ----
        BenchmarkTask(
            task_id="hard_prod_staging_feature_diff",
            prompt=(
                "Compare configs/prod.env and configs/staging.env. "
                "There is exactly one feature flag (a key starting with FEATURE_) whose value differs between them. "
                "Answer in two lines: 'Flag: <name>' and 'ProdValue: <value>'."
            ),
            validator=validate_prod_staging_feature_diff,
            notes="FEATURE_BILLING_V2 = true in prod, false in staging.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        BenchmarkTask(
            task_id="hard_incident_root_cause",
            prompt=(
                "Read incident_notes.md and deployments.log together. "
                "The incident notes describe an outage that started shortly after a specific deployment. "
                "Identify which service was deployed immediately before the incident began. "
                "Answer with exactly one line: 'Service: <name>'."
            ),
            validator=validate_incident_root_cause,
            notes="billing-api deployed at 09:52 just before the incident.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        BenchmarkTask(
            task_id="hard_env_var_mismatch",
            prompt=(
                "Read src/cache.py. It reads an environment variable via os.getenv. "
                "Then read configs/prod.env. Identify which environment variable the code reads but is NOT defined in prod.env. "
                "Answer with exactly one line: 'Missing: <ENV_VAR_NAME>'."
            ),
            validator=validate_env_var_mismatch,
            notes="cache.py reads REDIS_HOST; prod.env defines REDIS_URL but not REDIS_HOST.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        BenchmarkTask(
            task_id="hard_correlated_alerts",
            prompt=(
                "Read alerts.log to find the timestamp of the first alert. "
                "Then read timeline.log and identify which service had repeated FAIL status entries in the minutes immediately before that first alert fired. "
                "Answer with exactly one line: 'Service: <name>'."
            ),
            validator=validate_correlated_alerts,
            notes="First alert at 10:03; billing-worker had FAIL entries at 10:01, 10:02, 10:03.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        # ---- Personal finance ----
        BenchmarkTask(
            task_id="finance_total_spend",
            prompt=(
                "Read expenses.csv. Sum the 'amount' column across all rows. "
                "Answer with exactly one line: 'Total: <number>' (use two decimal places)."
            ),
            validator=validate_expenses_total,
            notes="Sum of all expense amounts is 636.74.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="finance_top_category",
            prompt=(
                "Read expenses.csv. Group by the 'category' column and sum the 'amount' per category. "
                "Identify the category with the highest total spend. "
                "Answer in two lines: 'Category: <name>' and 'Total: <number>'."
            ),
            validator=validate_expenses_top_category,
            notes="groceries is highest at 212.80.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        # ---- Customer support ----
        BenchmarkTask(
            task_id="support_open_ticket_count",
            prompt=(
                "Read tickets.csv. Count how many rows have status equal to 'open'. "
                "Answer with exactly one line: 'Count: <integer>'."
            ),
            validator=validate_tickets_open_count,
            notes="5 tickets have status=open.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="support_top_customer",
            prompt=(
                "Read tickets.csv. Identify which customer has filed the most tickets. "
                "Answer in two lines: 'Customer: <name>' and 'Count: <integer>'."
            ),
            validator=validate_tickets_top_customer,
            notes="Alice has 4 tickets.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        # ---- HR / org chart ----
        BenchmarkTask(
            task_id="hr_direct_reports_mark",
            prompt=(
                "Read employees.csv. Count how many employees report directly to 'Mark VP Eng'. "
                "Answer with exactly one line: 'Count: <integer>'."
            ),
            validator=validate_hr_direct_reports,
            notes="Mark VP Eng has 2 direct reports: Tom and Jen.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        BenchmarkTask(
            task_id="hr_no_manager",
            prompt=(
                "Read employees.csv. Identify the employee whose manager_id field is empty (the top of the org chart). "
                "Answer with exactly one line: 'Name: <employee name>'."
            ),
            validator=validate_hr_no_manager,
            notes="Sarah CEO has no manager.",
            suite=SUITE_NAME,
            difficulty="hard",
        ),
        # ---- Meetings / scheduling ----
        BenchmarkTask(
            task_id="meetings_count_on_march_02",
            prompt=(
                "Read meetings.csv. Count how many meetings are scheduled on 2026-03-02. "
                "Answer with exactly one line: 'Count: <integer>'."
            ),
            validator=validate_meetings_count_on_date,
            notes="3 meetings on 2026-03-02.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="meetings_double_booked",
            prompt=(
                "Read meetings.csv. On 2026-03-02, identify the attendee who is double-booked "
                "(present in two meetings whose time ranges overlap). "
                "Answer with exactly one line: 'Attendee: <name>'."
            ),
            validator=validate_meetings_double_booked,
            notes="alice is in Planning (11:00-12:30) and Lunch Sync (12:00-13:00) on 2026-03-02.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        # ---- Document summarization ----
        BenchmarkTask(
            task_id="minutes_facilitator",
            prompt=(
                "Read meeting_minutes.md. Identify the meeting's facilitator. "
                "Answer with exactly one line: 'Facilitator: <full name>'."
            ),
            validator=validate_minutes_facilitator,
            notes="Facilitator is Sarah Chen.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="minutes_action_owners",
            prompt=(
                "Read meeting_minutes.md. List the names of the people assigned action items. "
                "Answer with exactly one line: 'Owners: <name1>, <name2>, ...'."
            ),
            validator=validate_minutes_action_owners,
            notes="Action items assigned to Mark, Lisa, Tom.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        # ---- Pantry / recipe ----
        BenchmarkTask(
            task_id="pantry_lowest_stock",
            prompt=(
                "Read pantry.csv. Identify the item with the lowest quantity. "
                "Answer with exactly one line: 'Item: <name>'."
            ),
            validator=validate_pantry_lowest_stock,
            notes="yeast has quantity 0 (lowest).",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="recipe_missing_ingredient",
            prompt=(
                "Read recipe.md and pantry.csv. Identify the recipe ingredient that does not appear at all in pantry.csv. "
                "Answer with exactly one line: 'Missing: <ingredient name>'."
            ),
            validator=validate_recipe_missing_ingredient,
            notes="cocoa is required by recipe but absent from pantry.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        # ---- Travel / route ----
        BenchmarkTask(
            task_id="travel_nyc_boston_distance",
            prompt=(
                "Read distances.csv. Find the distance in miles between NYC and Boston. "
                "Answer with exactly one line: 'Miles: <integer>'."
            ),
            validator=validate_distance_lookup,
            notes="215 miles.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="travel_route_total",
            prompt=(
                "Read distances.csv. Compute the total miles for the route NYC -> Philadelphia -> Washington -> Atlanta "
                "by summing each consecutive leg. "
                "Answer with exactly one line: 'Total: <integer> miles'."
            ),
            validator=validate_route_total,
            notes="95 + 140 + 640 = 875 miles.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
        # ---- Email triage ----
        BenchmarkTask(
            task_id="inbox_urgent_count",
            prompt=(
                "Read inbox.md. Each email block contains a 'Priority:' line. Count how many emails have Priority: urgent. "
                "Answer with exactly one line: 'Count: <integer>'."
            ),
            validator=validate_inbox_urgent_count,
            notes="3 urgent emails.",
            suite=SUITE_NAME,
            difficulty="easy",
        ),
        BenchmarkTask(
            task_id="inbox_outage_sender",
            prompt=(
                "Read inbox.md. Identify the email address that sent the message(s) about a 'production outage'. "
                "Answer with exactly one line: 'Sender: <email address>'."
            ),
            validator=validate_inbox_outage_sender,
            notes="client@acme.com sent the outage emails.",
            suite=SUITE_NAME,
            difficulty="medium",
        ),
    ]
