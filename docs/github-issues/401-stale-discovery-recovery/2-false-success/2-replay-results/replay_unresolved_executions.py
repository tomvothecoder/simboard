"""Replay CSV executions sequentially against the Spin path-ingestion API.

Preview is the default. --apply writes to the API and requires a new --log file.
Uses only the standard library; run with the Spin container's Python.
"""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, TextIO
from uuid import uuid4

SOURCE_ROOT = PurePosixPath("/global/cfs/cdirs/e3sm/OLD_PERF")
CONTAINER_ROOT = PurePosixPath("/OLD_PERF")
EMPTY_RESPONSE = "No execution outcome reported; the API may have skipped parsing"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="DBeaver checked_*.csv export")
    parser.add_argument("--apply", action="store_true", help="Send API requests")
    parser.add_argument("--log", type=Path, help="New JSONL file; never overwritten")
    parser.add_argument("--limit", type=int, help="Maximum executions; default: all")
    parser.add_argument(
        "--resume-from", type=Path, help="Prior JSONL log to validate against the CSV"
    )
    parser.add_argument(
        "--start-index",
        type=int,
        help="Resume at this original 1-based index (inclusive)",
    )
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument(
        "--delay", type=float, default=0.5, help="Seconds between requests"
    )
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("SIMBOARD_API_BASE_URL", "http://backend:8000"),
    )
    args = parser.parse_args(argv)
    if (args.resume_from is None) != (args.start_index is None):
        parser.error("--resume-from and --start-index must be used together")
    start_index = args.start_index if args.start_index is not None else 1
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    if not math.isfinite(args.delay) or args.delay < 0:
        parser.error("--delay must be nonnegative and finite")
    try:
        endpoint = _endpoint(args.api_base_url)
        candidates = _select_candidates(
            args.csv, args.resume_from, start_index, args.limit
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not candidates:
        parser.error("CSV contains no unmatched executions")
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "endpoint": endpoint,
                    "selected": len(candidates),
                    "start_index": start_index,
                    "first": candidates[0],
                    "requests_sent": 0,
                },
                indent=2,
            )
        )
        return 0

    token = os.environ.get("SIMBOARD_API_TOKEN", "")
    if not token or not args.log:
        parser.error("--apply requires SIMBOARD_API_TOKEN and --log")
    try:
        with args.log.open("x", encoding="utf-8") as log:
            return replay(
                candidates,
                endpoint,
                token,
                log,
                args.timeout,
                args.delay,
                start_index=start_index,
                resume_from=str(args.resume_from) if args.resume_from else None,
            )
    except OSError as exc:
        print(
            f"Replay stopped: {exc}. Inspect the log before restarting.",
            file=sys.stderr,
        )
        return 1


def load_candidates(path: Path) -> list[dict[str, str]]:
    """Validate the complete CSV before making any requests; deduplicate paths."""
    candidates = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {
            "machine",
            "execution_path",
            "expected_execution_id",
            "database_status",
        }
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV requires columns: {', '.join(sorted(required))}")
        for row in reader:
            if row["database_status"] == "execution_exists":
                continue
            candidate = _candidate(row)
            candidates[candidate["execution_path"]] = candidate

    return list(candidates.values())


def validate_resume(path: Path, candidates: list[dict[str, str]]) -> None:
    """Check logged request identities against the original deduplicated CSV order."""
    requests = 0
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            if record.get("event") not in ("request_started", "request_finished"):
                continue
            index = record.get("index")
            if type(index) is not int or not 1 <= index <= len(candidates):
                raise ValueError(f"Invalid request index at JSONL line {line_number}")
            candidate = candidates[index - 1]
            if any(record.get(key) != value for key, value in candidate.items()):
                raise ValueError(
                    f"JSONL index {index} does not match the CSV candidate"
                )
            requests += 1
    if not requests:
        raise ValueError("JSONL contains no request events to validate")


def classify_response(
    body: Any, execution_id: str, execution_path: str
) -> tuple[str, str | None]:
    """Classify one selected execution, rejecting responses that imply wider scope."""
    if not isinstance(body, dict):
        return "unconfirmed", "Response is not a JSON object"
    created, duplicate = body.get("created_count"), body.get("duplicate_count")
    errors, executions = body.get("errors"), body.get("executions")
    if (
        type(created) is not int
        or type(duplicate) is not int
        or created < 0
        or duplicate < 0
        or not isinstance(errors, list)
        or not isinstance(executions, list)
    ):
        return "unconfirmed", "Missing or invalid response counts/lists"
    if created == duplicate == 0 and not errors and not executions:
        return "unconfirmed", EMPTY_RESPONSE
    if created + duplicate + len(errors) != 1 or len(executions) != created:
        return (
            "unconfirmed",
            "Response does not account for exactly one selected execution",
        )
    if errors:
        error = errors[0]
        if not isinstance(error, dict) or error.get("execution_dir") != execution_path:
            return (
                "unconfirmed",
                "Error identity differs from the selected execution path",
            )
        return "failed", None
    if duplicate:
        return "duplicate", None
    if (
        not isinstance(executions[0], dict)
        or executions[0].get("execution_id") != execution_id
    ):
        return (
            "unconfirmed",
            "Created execution ID differs from the selected directory ID",
        )

    return "created", None


def replay(
    candidates: list[dict[str, str]],
    endpoint: str,
    token: str,
    log: TextIO,
    timeout: float,
    delay: float,
    *,
    start_index: int = 1,
    resume_from: str | None = None,
) -> int:
    """Log before and after each request; never retry or mutate discovery state directly."""
    run_id = str(uuid4())
    counts: Counter[str] = Counter()
    interrupted = False
    _emit(
        log,
        token,
        "run_started",
        run_id=run_id,
        endpoint=endpoint,
        selected=len(candidates),
        start_index=start_index,
        resume_from=resume_from,
        retries=0,
        timeout_seconds=timeout,
    )
    try:
        for index, candidate in enumerate(candidates, start_index):
            attempt_id = str(uuid4())
            _emit(
                log,
                token,
                "request_started",
                run_id=run_id,
                attempt_id=attempt_id,
                index=index,
                **candidate,
            )
            counts["attempted"] += 1
            started = time.monotonic()
            status, raw, transport_error = _post(endpoint, token, candidate, timeout)
            counts[
                "http_succeeded"
                if status and 200 <= status < 300
                else "http_failed"
                if status
                else "http_unknown"
            ] += 1
            body = _decode(raw)
            outcome, reason = (
                classify_response(
                    body,
                    candidate["execution_id"],
                    candidate["container_execution_path"],
                )
                if status and 200 <= status < 300
                else (
                    "unconfirmed",
                    "HTTP/transport failure; write outcome not inferred",
                )
            )
            counts[outcome] += 1
            _emit(
                log,
                token,
                "request_finished",
                run_id=run_id,
                attempt_id=attempt_id,
                index=index,
                **candidate,
                http_status=status,
                outcome=outcome,
                reason=reason,
                response_body=body,
                raw_response=raw,
                transport_error=transport_error,
                duration_seconds=round(time.monotonic() - started, 3),
            )
            if (
                transport_error
                or status in (401, 403)
                or (
                    status
                    and 200 <= status < 300
                    and outcome == "unconfirmed"
                    and reason != EMPTY_RESPONSE
                )
            ):
                _emit(
                    log,
                    token,
                    "run_stopped",
                    run_id=run_id,
                    reason="Transport/authentication failure or ambiguous response; inspect before restarting",
                )
                break
            if index < start_index + len(candidates) - 1:
                time.sleep(delay)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        # An interruption during an in-flight request leaves its outcome unknown.
        counts["unconfirmed"] += counts["attempted"] - sum(
            counts[key] for key in ("created", "duplicate", "failed", "unconfirmed")
        )
        counts["http_unknown"] += counts["attempted"] - sum(
            counts[key] for key in ("http_succeeded", "http_failed", "http_unknown")
        )
        not_attempted = len(candidates) - counts["attempted"]
        failed = bool(
            counts["failed"] or counts["unconfirmed"] or not_attempted or interrupted
        )
        _emit(
            log,
            token,
            "run_summary",
            run_id=run_id,
            status="failure" if failed else "success",
            selected=len(candidates),
            not_attempted=not_attempted,
            interrupted=interrupted,
            **{
                key: counts[key]
                for key in (
                    "attempted",
                    "http_succeeded",
                    "http_failed",
                    "http_unknown",
                    "created",
                    "duplicate",
                    "failed",
                    "unconfirmed",
                )
            },
        )

    return 1 if failed else 0


def _select_candidates(
    csv_path: Path, resume_from: Path | None, start_index: int, limit: int | None
) -> list[dict[str, str]]:
    if start_index < 1:
        raise ValueError("--start-index must be positive")
    candidates = load_candidates(csv_path)
    if resume_from is not None:
        validate_resume(resume_from, candidates)
        if start_index > len(candidates):
            raise ValueError("--start-index exceeds the CSV candidate count")
    candidates = candidates[start_index - 1 :]

    return candidates[:limit]


def _endpoint(base: str) -> str:
    parsed = urllib.parse.urlsplit(base)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") not in ("", "/api/v1")
    ):
        raise ValueError(
            "API base must be an HTTP(S) origin, optionally ending /api/v1, without credentials"
        )
    base = base.rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"

    return base + "/ingestions/from-path"


def _candidate(row: dict[str, str]) -> dict[str, str]:
    if row["machine"] != "perlmutter" or row["database_status"] not in (
        "no_exact_path_case_match",
        "no_exact_path_identity_match",
    ):
        raise ValueError("Only Perlmutter unmatched-identity rows are supported")
    path = PurePosixPath(row["execution_path"])
    try:
        relative = path.relative_to(SOURCE_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path is outside the expected source root: {path}") from exc
    if (
        ".." in relative.parts
        or len(relative.parts) != 6
        or relative.parts[2] != "COMPLETED"
    ):
        raise ValueError(f"Unexpected archive layout: {path}")
    if path.name != row["expected_execution_id"]:
        raise ValueError(f"Execution ID does not match directory name: {path}")
    container_path = CONTAINER_ROOT / relative

    return {
        "machine": "perlmutter",
        "execution_path": str(path),
        "container_execution_path": str(container_path),
        "case_path": str(container_path.parent),
        "execution_id": path.name,
    }


def _post(
    endpoint: str,
    token: str,
    candidate: dict[str, str],
    timeout: float,
) -> tuple[int | None, str, str | None]:
    payload = {
        "machine_name": candidate["machine"],
        "archive_path": candidate["case_path"],
        "selected_execution_ids": [candidate["execution_id"]],
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        try:
            with opener.open(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read().decode("utf-8", errors="replace"),
                    None,
                )
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace"), None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        return None, "", str(exc)


def _decode(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _emit(log: TextIO, token: str, event: str, **fields: Any) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **_redact(fields, token),
    }
    log.write(json.dumps(record) + "\n")
    log.flush()
    print(json.dumps(record, indent=2), flush=True)


def _redact(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return value.replace(token, "[REDACTED]").replace(
            json.dumps(token)[1:-1], "[REDACTED]"
        )
    if isinstance(value, dict):
        return {key: _redact(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, token) for item in value]
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward API credentials to a redirected destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
