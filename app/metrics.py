from __future__ import annotations

import re
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

DB_QUERY_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

BACKGROUND_JOB_BUCKETS = (
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    300.0,
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query latency in seconds",
    labelnames=("operation", "table"),
    buckets=DB_QUERY_BUCKETS,
)

background_job_duration_seconds = Histogram(
    "background_job_duration_seconds",
    "Background scheduler job duration in seconds",
    labelnames=("job_name",),
    buckets=BACKGROUND_JOB_BUCKETS,
)

background_job_failures_total = Counter(
    "background_job_failures_total",
    "Failed background scheduler jobs",
    labelnames=("job_name",),
)

websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Currently active WebSocket connections",
)

_SELECT_TABLE_PATTERN = re.compile(r"\bfrom\s+([\w\.\"]+)", re.IGNORECASE)
_INSERT_TABLE_PATTERN = re.compile(r"\binsert\s+into\s+([\w\.\"]+)", re.IGNORECASE)
_UPDATE_TABLE_PATTERN = re.compile(r"\bupdate\s+([\w\.\"]+)", re.IGNORECASE)
_DELETE_TABLE_PATTERN = re.compile(r"\bdelete\s+from\s+([\w\.\"]+)", re.IGNORECASE)


def _normalize_table_name(raw_table: str | None) -> str:
    if not raw_table:
        return "unknown"
    table = raw_table.strip().strip(";")
    table = table.split()[0]
    table = table.strip('"`')
    if "." in table:
        table = table.split(".")[-1]
    return table or "unknown"


def _extract_operation_and_table(statement: Any) -> tuple[str, str]:
    sql_text = str(statement or "").strip()
    if not sql_text:
        return "select", "unknown"

    lowered = sql_text.lower()
    if lowered.startswith("insert") or "insert into" in lowered:
        table_match = _INSERT_TABLE_PATTERN.search(sql_text)
        return "insert", _normalize_table_name(
            table_match.group(1) if table_match else None
        )

    if lowered.startswith("update"):
        table_match = _UPDATE_TABLE_PATTERN.search(sql_text)
        return "update", _normalize_table_name(
            table_match.group(1) if table_match else None
        )

    if lowered.startswith("delete") or "delete from" in lowered:
        table_match = _DELETE_TABLE_PATTERN.search(sql_text)
        return "delete", _normalize_table_name(
            table_match.group(1) if table_match else None
        )

    table_match = _SELECT_TABLE_PATTERN.search(sql_text)
    return "select", _normalize_table_name(
        table_match.group(1) if table_match else None
    )


def observe_db_query(statement: Any, duration_seconds: float) -> None:
    operation, table = _extract_operation_and_table(statement)
    db_query_duration_seconds.labels(operation=operation, table=table).observe(
        duration_seconds
    )


def observe_background_job(job_name: str, duration_seconds: float) -> None:
    background_job_duration_seconds.labels(job_name=job_name).observe(duration_seconds)


def record_background_job_failure(job_name: str) -> None:
    background_job_failures_total.labels(job_name=job_name).inc()


def increment_websocket_connections() -> None:
    websocket_connections_active.inc()


def decrement_websocket_connections() -> None:
    websocket_connections_active.dec()
