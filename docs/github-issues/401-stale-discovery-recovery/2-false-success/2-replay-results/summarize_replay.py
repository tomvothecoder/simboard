"""Group one saved replay JSONL log without API requests or database access."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

GROUP_FIELDS = ("http_status", "outcome", "error_type", "field", "code", "signature")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="Saved JSONL output from one replay run")
    parser.add_argument(
        "--output", type=Path, help="Save JSON to a new file; never overwrite"
    )
    args = parser.parse_args(argv)
    try:
        report = summarize_records(read_records(args.log))
        rendered = json.dumps(report, indent=2)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(rendered)

    return 0


def read_records(path: Path) -> list[dict[str, Any]]:
    """Reject malformed input and mixed-run files rather than report misleading totals."""
    records = []
    seen: dict[str, set[str]] = {"request_started": set(), "request_finished": set()}
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise ValueError(
                    f"{path}:{number}: invalid JSON; ensure the replay log is complete"
                ) from exc
            _validate_record(record, f"{path}:{number}")
            if record["event"] in seen:
                attempts = seen[record["event"]]
                if record["attempt_id"] in attempts:
                    raise ValueError(
                        f"{path}:{number}: duplicate {record['event']} attempt_id"
                    )
                attempts.add(record["attempt_id"])
            records.append(record)
    if not records:
        raise ValueError(f"{path}: no replay events found")
    if len({record["run_id"] for record in records}) > 1:
        raise ValueError(
            "Expected one replay run; do not combine logs without deduplicating execution paths"
        )

    return records


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Count finished requests and group failed/unconfirmed error items with examples."""
    finished = [record for record in records if record["event"] == "request_finished"]
    starts = {
        record["attempt_id"]: record["timestamp"]
        for record in records
        if record["event"] == "request_started"
    }
    summaries = [record for record in records if record["event"] == "run_summary"]
    counts: Counter[tuple[str, ...]] = Counter()
    examples = {}
    for record in finished:
        if record["outcome"] not in ("failed", "unconfirmed"):
            continue
        for error in _response_errors(record) or [{}]:
            key = _error_key(record, error)
            counts[key] += 1
            examples.setdefault(
                key,
                {
                    "path": record["execution_path"],
                    "started_utc": starts.get(record["attempt_id"]),
                    "finished_utc": record["timestamp"],
                },
            )

    return {
        "run_summary": summaries[-1] if summaries else None,
        "http_status_counts": dict(
            Counter(str(record["http_status"]) for record in finished)
        ),
        "outcome_counts": dict(Counter(record["outcome"] for record in finished)),
        "error_groups": [
            {
                **dict(zip(GROUP_FIELDS, key, strict=True)),
                "count": count,
                "example": examples[key],
            }
            for key, count in counts.most_common()
        ],
    }


def _validate_record(record: Any, location: str) -> None:
    if not isinstance(record, dict) or not isinstance(record.get("event"), str):
        raise ValueError(f"{location}: expected a JSON event object")
    required = {
        "request_started": {"attempt_id", "timestamp"},
        "request_finished": {"attempt_id", "timestamp", "execution_path", "outcome"},
    }
    for name in required.get(record["event"], set()) | {"run_id"}:
        if not isinstance(record.get(name), str) or not record[name]:
            raise ValueError(f"{location}: {name} must be a nonempty string")
    if record["event"] == "request_finished":
        if "http_status" not in record or (
            record["http_status"] is not None and type(record["http_status"]) is not int
        ):
            raise ValueError(f"{location}: http_status must be an integer or null")


def _response_errors(record: dict[str, Any]) -> list[dict[str, Any]]:
    body = record.get("response_body")
    errors = body.get("errors", []) if isinstance(body, dict) else []
    if not isinstance(errors, list):
        return []

    return [error for error in errors if isinstance(error, dict)]


def _error_key(record: dict[str, Any], error: dict[str, Any]) -> tuple[str, ...]:
    message = str(
        error.get("error")
        or record.get("transport_error")
        or record.get("reason")
        or ""
    )
    match = re.search(r"\[type=([^,\]]+)", message)
    code = error.get("code") or (match.group(1) if match else "unknown")

    return (
        str(record["http_status"]),
        str(record["outcome"]),
        str(error.get("error_type") or "unknown"),
        str(error.get("field") or "unknown"),
        str(code),
        message.splitlines()[0] if message else "unknown",
    )


if __name__ == "__main__":
    raise SystemExit(main())
