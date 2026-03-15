from __future__ import annotations

import argparse
import base64
import json
import shutil
from pathlib import Path


APP_LOG = """2026-03-12T09:00:01Z INFO Boot sequence started
2026-03-12T09:00:02Z INFO Loading configuration from config.json
2026-03-12T09:00:03Z WARN Cache warmup took longer than expected
2026-03-12T09:01:10Z ERROR Failed to fetch customer profile for user 183
2026-03-12T09:02:44Z INFO Retrying profile fetch
2026-03-12T09:03:11Z ERROR Payment gateway timeout while creating invoice 9921
2026-03-12T09:03:15Z INFO Invoice retry queued
2026-03-12T09:04:27Z ERROR Worker crashed while processing queue billing-high
2026-03-12T09:04:29Z WARN Worker recovered after supervisor restart
2026-03-12T09:05:01Z ERROR Failed to connect to redis replica
2026-03-12T09:05:14Z INFO Replica connection restored
2026-03-12T09:06:33Z ERROR Timeout while calling shipping partner API
2026-03-12T09:06:55Z INFO Shipping retry succeeded
2026-03-12T09:07:42Z ERROR Failed to persist audit event for order 5518
2026-03-12T09:08:00Z INFO Shutdown complete
"""

CONFIG_JSON = {
    "mode": "production",
    "timeout": 45,
    "retries": 5,
    "feature_flags": {
        "timeout_monitoring": True,
        "beta_checkout": False,
    },
}

NOTES_MD = """# Incident notes

- Investigate timeout spikes seen in the payment flow after 09:00 UTC.
- Shipping timeout may be related to a slow upstream partner.
- Remember to verify retry defaults before changing the config.
"""

SALES_CSV = """country,city,revenue,quarter
India,Bangalore,980,Q1
India,Mumbai,870,Q1
India,Delhi,1025,Q2
India,Hyderabad,760,Q2
India,Pune,815,Q3
India,Chennai,910,Q4
USA,Seattle,1200,Q1
USA,Austin,1110,Q2
Germany,Berlin,720,Q3
Japan,Tokyo,1330,Q4
Brazil,Sao Paulo,640,Q2
India,Ahmedabad,705,Q4
"""

MAIN_PY = """from src.utils import process_order


def main() -> None:
    order = {"id": "SO-1001", "country": "India", "amount": 980}
    result = process_order(order)
    print(result)


if __name__ == "__main__":
    main()
"""

UTILS_PY = """from __future__ import annotations

from typing import Any


def calculate_retry_delay(retries: int) -> int:
    return min(retries * 5, 30)


def process_order(order: dict[str, Any]) -> dict[str, Any]:
    status = "approved" if order.get("amount", 0) < 1000 else "manual_review"
    return {
        "order_id": order["id"],
        "status": status,
        "timeout_policy": "standard-timeout-window",
    }
"""

CACHE_PY = """from __future__ import annotations

import os


REDIS_HOST = os.getenv("REDIS_HOST", "cache.internal")


def get_cache_host() -> str:
    return REDIS_HOST
"""

WORKER_PY = """from __future__ import annotations

import os


REDIS_URL = os.getenv("REDIS_URL", "redis://worker-cache.internal:6379/0")


def get_worker_redis_url() -> str:
    return REDIS_URL
"""

SETTINGS_PY = """from __future__ import annotations

APP_NAME = "agent-benchmark"
DEFAULT_TIMEOUT_SECONDS = 30
"""

PROD_ENV = """APP_ENV=production
DB_HOST=prod-db.internal
REDIS_URL=redis://prod-cache.internal:6379/0
LOG_LEVEL=warn
FEATURE_BILLING_V2=true
API_BASE_URL=https://api.example.com
"""

STAGING_ENV = """APP_ENV=staging
DB_HOST=staging-db.internal
REDIS_URL=redis://staging-cache.internal:6379/0
LOG_LEVEL=debug
FEATURE_BILLING_V2=false
API_BASE_URL=https://staging-api.example.com
"""

CUSTOMERS_CSV = """customer_id,name,email
1,Alex Stone,alex@example.com
2,Mia Chen,mia@example.com
3,Raj Patel,raj@example.com
4,Sam Ortiz,sam@example.com
5,Alex Stone,alex@example.com
6,Mia Chen,mia@example.com
7,Lina Park,lina@example.com
8,Sam Ortiz,sam@example.com
9,Mia Chen,mia@example.com
"""

JOBS_CSV = """job_id,owner_name,queue,priority
J100,Ana,imports,low
J101,Rohit,exports,high
J102,Priya,retry,high
J103,Noah,images,medium
J104,Omar,retry,medium
J105,Sofia,cleanup,low
J106,Mei,emails,medium
J107,Jia,retry,high
"""

FAILED_JOBS_LOG = """2026-03-01T09:58:10 job_id=J101 reason=network
2026-03-01T10:02:44 job_id=J102 reason=timeout
2026-03-01T10:04:01 job_id=J104 reason=timeout
2026-03-01T10:07:18 job_id=J105 reason=crash
2026-03-01T10:08:30 job_id=J107 reason=timeout
"""

TIMELINE_LOG = """2026-03-01T09:55:00 service=api-gateway status=OK
2026-03-01T09:57:00 service=billing-worker status=OK
2026-03-01T09:59:30 service=cache-sync status=OK
2026-03-01T10:01:00 service=billing-worker status=FAIL
2026-03-01T10:02:00 service=billing-worker status=FAIL
2026-03-01T10:03:00 service=billing-worker status=FAIL
2026-03-01T10:04:00 service=cache-sync status=OK
2026-03-01T10:05:00 service=billing-worker status=FAIL
"""

APPLICATION_LOG = """2026-03-01T09:50:00 INFO startup complete
WARN code=W204 service=cache message=stale shard metadata
WARN code=W301 service=worker message=slow downstream ack
WARN code=W204 service=cache message=stale shard metadata
WARN code=W110 service=auth message=missing device fingerprint
WARN code=W204 service=cache message=stale shard metadata
WARN code=W301 service=worker message=slow downstream ack
WARN code=W204 service=cache message=stale shard metadata
WARN code=W301 service=worker message=slow downstream ack
WARN code=W204 service=cache message=stale shard metadata
WARN code=W110 service=auth message=missing device fingerprint
"""

AUTH_LOG = """2026-03-01T09:40:00 LOGIN user=alice
2026-03-01T09:41:00 FAILED_LOGIN user=alice
2026-03-01T09:42:00 FAILED_LOGIN user=bob
2026-03-01T09:43:00 FAILED_LOGIN user=carol
2026-03-01T09:44:00 LOGIN user=derek
2026-03-01T09:45:00 FAILED_LOGIN user=bob
2026-03-01T09:46:00 FAILED_LOGIN user=dina
2026-03-01T09:47:00 PASSWORD_RESET user=carol
"""

REQUESTS_LOG = """2026-03-01T09:50:00 path=/api/orders/list latency_ms=210 status=200
2026-03-01T09:51:00 path=/api/auth/session latency_ms=810 status=200
2026-03-01T09:52:00 path=/api/payments/charge latency_ms=640 status=500
2026-03-01T09:53:00 path=/api/reports/export latency_ms=910 status=200
2026-03-01T09:54:00 path=/api/billing/retry latency_ms=870 status=502
2026-03-01T09:55:00 path=/api/profile/view latency_ms=180 status=200
2026-03-01T09:56:00 path=/api/inventory/search latency_ms=430 status=200
"""

SERVER_LOG = """2026-03-01T09:55:00 500 /api/payments/charge user=u01
2026-03-01T09:55:12 200 /api/orders/list user=u02
2026-03-01T09:55:35 500 /api/orders/list user=u03
2026-03-01T09:56:00 500 /api/payments/charge user=u04
2026-03-01T09:56:10 500 /api/auth/session user=u05
2026-03-01T09:56:45 404 /api/health user=u06
2026-03-01T09:57:10 500 /api/payments/charge user=u07
2026-03-01T09:57:20 500 /api/orders/list user=u08
2026-03-01T09:57:50 200 /api/payments/charge user=u09
2026-03-01T09:58:00 500 /api/payments/charge user=u10
2026-03-01T09:58:30 500 /api/orders/list user=u11
2026-03-01T09:59:00 500 /api/payments/charge user=u12
2026-03-01T09:59:10 500 /api/auth/session user=u13
2026-03-01T09:59:30 500 /api/reports/export user=u14
2026-03-01T09:59:45 500 /api/payments/charge user=u15
2026-03-01T10:00:00 500 /api/orders/list user=u16
2026-03-01T10:00:15 500 /api/reports/export user=u17
"""

ALERTS_LOG = """2026-03-01T10:03:00 alert=billing-api-high-error-rate severity=critical
2026-03-01T10:04:00 alert=billing-api-latency-p95 severity=critical
2026-03-01T10:05:00 alert=worker-queue-depth severity=warning
"""

DEPLOYMENTS_LOG = """2026-03-01T09:20:00 service=auth-api version=2026.03.01-rc1 status=success
2026-03-01T09:52:00 service=billing-api version=2026.03.01-rc3 status=success
2026-03-01T11:15:00 service=worker version=2026.03.01-rc4 status=success
"""

INCIDENT_NOTES_MD = """# March 1 incident

The billing-api started throwing elevated errors shortly after the 09:52 deployment.
The likely cause is connection pool exhaustion introduced by the new billing-api rollout.
Operations mitigated by reducing background reconciliation load.
"""

PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO"
    "QnK3sAAAAASUVORK5CYII="
)

CSV_SOURCE_NAME = "annual-enterprise-survey-2024-financial-year-provisional.csv"
CSV_DEST_NAME = "industry_financial.csv"


def build_huge_log() -> str:
    lines: list[str] = []
    for idx in range(1, 2201):
        if idx in {823, 1974}:
            lines.append(
                f"2026-03-12T10:{idx % 60:02d}:17Z ERROR database connection failed for replica db-{idx % 3}"
            )
        elif idx % 175 == 0:
            lines.append(f"2026-03-12T10:{idx % 60:02d}:11Z WARN retry scheduled for worker {idx}")
        else:
            lines.append(f"2026-03-12T10:{idx % 60:02d}:00Z INFO processed event batch {idx}")
    return "\n".join(lines) + "\n"


def build_deepgram_docs() -> str:
    lines = ["# Deepgram Streaming Guide", "", "This is a long generated markdown file used to test ranged reading.", ""]
    for section in range(1, 181):
        lines.append(f"## Section {section}")
        lines.append(f"Overview for section {section}.")
        for item in range(1, 36):
            lines.append(f"- Detail {section}.{item}: Example guidance for streaming integrations and diagnostics.")
        if section == 132:
            lines.append("")
            lines.append("### Live captions example")
            lines.append("Set `DG_STREAM_MODE=live-captions` before starting the streaming demo.")
            lines.append("This environment variable controls whether the sample client renders live captions.")
            lines.append("")
    return "\n".join(lines) + "\n"


def copy_csv_fixture(root: Path, force: bool) -> None:
    source = Path(__file__).resolve().parents[2] / CSV_SOURCE_NAME
    destination = root / CSV_DEST_NAME
    if not source.exists():
        return
    if force or not destination.exists():
        shutil.copyfile(source, destination)


def create_workspace(root: Path, force: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / ".artifacts").mkdir(parents=True, exist_ok=True)

    files: dict[Path, str] = {
        root / "app.log": APP_LOG,
        root / "huge.log": build_huge_log(),
        root / "deepgram_fixture_long.md": build_deepgram_docs(),
        root / "sales.csv": SALES_CSV,
        root / "config.json": json.dumps(CONFIG_JSON, indent=2) + "\n",
        root / "notes.md": NOTES_MD,
        root / "server.log": SERVER_LOG,
        root / "application.log": APPLICATION_LOG,
        root / "auth.log": AUTH_LOG,
        root / "requests.log": REQUESTS_LOG,
        root / "timeline.log": TIMELINE_LOG,
        root / "failed_jobs.log": FAILED_JOBS_LOG,
        root / "jobs.csv": JOBS_CSV,
        root / "customers.csv": CUSTOMERS_CSV,
        root / "incident_notes.md": INCIDENT_NOTES_MD,
        root / "alerts.log": ALERTS_LOG,
        root / "deployments.log": DEPLOYMENTS_LOG,
        root / "configs" / "prod.env": PROD_ENV,
        root / "configs" / "staging.env": STAGING_ENV,
        root / "src" / "main.py": MAIN_PY,
        root / "src" / "utils.py": UTILS_PY,
        root / "src" / "cache.py": CACHE_PY,
        root / "src" / "worker.py": WORKER_PY,
        root / "src" / "settings.py": SETTINGS_PY,
    }

    for path, content in files.items():
        if force or not path.exists():
            path.write_text(content, encoding="utf-8")

    png_path = root / "diagram.png"
    if force or not png_path.exists():
        png_path.write_bytes(base64.b64decode(PNG_1X1_BASE64))

    copy_csv_fixture(root, force)



def main() -> None:
    parser = argparse.ArgumentParser(description="Create benchmark workspace fixtures.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing workspace files.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[2] / "workspace_data"),
        help="Workspace directory to populate.",
    )
    args = parser.parse_args()
    create_workspace(Path(args.root), force=args.force)


if __name__ == "__main__":
    main()

