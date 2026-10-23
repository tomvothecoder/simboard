"""Replay original failed case requests from Perlmutter; preview unless --apply.

Use the external dev HTTPS API URL. The API reads /OLD_PERF itself; no files are
uploaded. Each request processes a whole original case snapshot and can write
catalog records and ingestion history. There are no automatic retries.

Use:
    uv run --project backend python docs/github-issues/401-stale-discovery-recovery/1-http-errors/replay_http_errors.py
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import re
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

DEFAULT_LOG = (
    Path(__file__).resolve().parent.parent / "perlmutter-full-archive-reingestion.log"
)
HOST_ARCHIVE_ROOT = Path("/global/cfs/cdirs/e3sm/OLD_PERF")
FAILURE_PATTERN = re.compile(
    r"^(\S+ \S+)Z .*event=case_ingestion_request_failed attempt=(\d+) "
    r"case_path=(\S+)[^\n]*status_code=(\d+)",
    re.MULTILINE,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_inventory_arguments(parser)
    parser.add_argument(
        "--api-base-url", default=os.environ.get("SIMBOARD_API_BASE_URL")
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--log", type=Path, help="New JSONL output; never overwritten")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    if not math.isfinite(args.delay) or args.delay < 0:
        parser.error("--delay must be nonnegative and finite")
    try:
        cases = load_failed_cases(args.input_log, args.status, args.limit)
        endpoint = api_endpoint(args.api_base_url) if args.api_base_url else None
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "endpoint": endpoint,
                    "external_https_api_required": endpoint is None,
                    "selected_case_paths": len(cases),
                    "http_status_filter": args.status,
                    "first": cases[0],
                    "requests_sent": 0,
                },
                indent=2,
            )
        )
        return 0
    token = os.environ.get("SIMBOARD_API_TOKEN", "")
    if not endpoint or not token or not args.log:
        parser.error(
            "--apply requires an external HTTPS API URL, SIMBOARD_API_TOKEN, and --log"
        )
    try:
        # A new file and a flushed start record are required before any request.
        with args.log.open("x", encoding="utf-8") as stream:
            return replay(cases, endpoint, token, stream, args.timeout, args.delay)
    except (OSError, ValueError) as exc:
        print(
            f"Replay stopped: {str(exc).replace(token, '[REDACTED]')}", file=sys.stderr
        )
        return 1


def add_inventory_arguments(parser: argparse.ArgumentParser) -> None:
    """Share the original-log selection between the inventory and replay tools."""
    parser.add_argument("--input-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--status", choices=("all", "409", "500"), default="all")
    parser.add_argument("--limit", type=int, help="Limit distinct case snapshot paths")


def load_failed_cases(
    log_path: Path,
    status: str = "all",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load every failed attempt, group by original case snapshot, and preserve order."""
    if limit is not None and limit < 1:
        raise ValueError("--limit must be positive")
    text = log_path.read_text(encoding="utf-8")
    outcomes = dict(re.findall(r"event=case_submission case=(\S+) outcome=(\S+)", text))
    grouped: dict[str, dict[str, Any]] = {}
    for timestamp, attempt, path, code in FAILURE_PATTERN.findall(text):
        relative = _relative_case_path(path)
        case = grouped.setdefault(
            path,
            {
                "case_path": path,
                "path_username": relative.parts[3],
                "path_case_name": relative.parts[4],
                "original_final_outcome": outcomes.get(str(relative), "unknown"),
                "failed_attempts": [],
            },
        )
        case["failed_attempts"].append(
            {
                "timestamp_utc": timestamp.replace(" ", "T").replace(",", ".") + "Z",
                "attempt": int(attempt),
                "http_status": int(code),
            }
        )
    selected = []
    for case in grouped.values():
        codes = {attempt["http_status"] for attempt in case["failed_attempts"]}
        if status != "all" and int(status) not in codes:
            continue
        case["original_http_statuses"] = sorted(codes)
        selected.append(case)
    if not selected:
        raise ValueError("No matching failed case requests found in the input log")

    return selected if limit is None else selected[:limit]


def local_case_path(case_path: str, archive_root: Path) -> Path:
    """Translate only validated /OLD_PERF paths to the host's read-only archive root."""
    return archive_root.joinpath(*_relative_case_path(case_path).parts)


def api_endpoint(base: str) -> str:
    """Require an explicit external HTTPS URL; never use Spin's internal backend host."""
    parsed = urllib.parse.urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname == "backend"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") not in ("", "/api/v1")
    ):
        raise ValueError(
            "Use the external dev HTTPS origin, optionally ending /api/v1, without credentials"
        )
    base = base.rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"

    return base + "/ingestions/from-path"


def replay(
    cases: list[dict[str, Any]],
    endpoint: str,
    token: str,
    stream: TextIO,
    timeout: float,
    delay: float,
) -> int:
    """Log request-level and returned execution-level outcomes separately."""
    run_id = str(uuid4())
    counts: Counter[str] = Counter()
    interrupted = False
    _emit(
        stream,
        token,
        "run_started",
        run_id=run_id,
        endpoint=endpoint,
        selected_case_paths=len(cases),
        retries=0,
    )
    try:
        for index, case in enumerate(cases, 1):
            attempt_id = str(uuid4())
            fields = {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "index": index,
                **case,
            }
            _emit(stream, token, "request_started", **fields)
            counts["attempted_case_requests"] += 1
            started = time.monotonic()
            status, raw, transport_error = _post(
                endpoint, token, case["case_path"], timeout
            )
            http_outcome = (
                "http_unknown"
                if status is None
                else ("http_succeeded" if 200 <= status < 300 else "http_failed")
            )
            counts[http_outcome] += 1
            counts[f"http_{status}"] += 1
            body = _decode(raw)
            if http_outcome == "http_succeeded":
                outcome, returned = _response_outcome(body)
                counts.update(returned)
            else:
                outcome = "unconfirmed_case_requests"
            counts[outcome] += 1
            _emit(
                stream,
                token,
                "request_finished",
                **fields,
                http_status=status,
                outcome=outcome,
                response_body=body,
                raw_response=raw,
                transport_error=transport_error,
                duration_seconds=round(time.monotonic() - started, 3),
            )
            if (
                transport_error
                or status in (401, 403)
                or outcome == "invalid_response"
                or (status is not None and 300 <= status < 400)
            ):
                _emit(
                    stream,
                    token,
                    "run_stopped",
                    run_id=run_id,
                    reason="Transport/authentication/redirect failure or invalid response; inspect before restarting",
                )
                break
            if index < len(cases):
                time.sleep(delay)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        counts["http_unknown"] += counts["attempted_case_requests"] - sum(
            counts[key] for key in ("http_succeeded", "http_failed", "http_unknown")
        )
        counts["unconfirmed_case_requests"] = counts["attempted_case_requests"] - sum(
            counts[key]
            for key in (
                "successful_case_requests",
                "execution_error_requests",
            )
        )
        not_attempted = len(cases) - counts["attempted_case_requests"]
        failed = bool(
            interrupted
            or not_attempted
            or any(
                counts[key]
                for key in (
                    "http_failed",
                    "http_unknown",
                    "invalid_response",
                    "execution_error_requests",
                    "empty_response_requests",
                )
            )
        )
        _emit(
            stream,
            token,
            "run_summary",
            run_id=run_id,
            status="failure" if failed else "success",
            selected_case_paths=len(cases),
            not_attempted_case_requests=not_attempted,
            interrupted=interrupted,
            **{
                key: counts[key]
                for key in (
                    "attempted_case_requests",
                    "http_succeeded",
                    "http_failed",
                    "http_unknown",
                    "http_409",
                    "http_500",
                    "successful_case_requests",
                    "execution_error_requests",
                    "empty_response_requests",
                    "invalid_response",
                    "unconfirmed_case_requests",
                    "created_executions",
                    "duplicate_executions",
                    "failed_executions_reported",
                )
            },
        )

    return 1 if failed else 0


def _relative_case_path(path: str) -> PurePosixPath:
    value = PurePosixPath(path)
    try:
        relative = value.relative_to("/OLD_PERF")
    except ValueError as exc:
        raise ValueError(f"Original request is outside /OLD_PERF: {path}") from exc
    if (
        len(relative.parts) != 5
        or ".." in relative.parts
        or relative.parts[2] != "COMPLETED"
    ):
        raise ValueError(f"Unexpected case snapshot path: {path}")

    return relative


def _response_outcome(body: Any) -> tuple[str, dict[str, int]]:
    if not isinstance(body, dict):
        return "invalid_response", {}
    created, duplicate = body.get("created_count"), body.get("duplicate_count")
    errors, executions = body.get("errors"), body.get("executions")
    if (
        type(created) is not int
        or type(duplicate) is not int
        or created < 0
        or duplicate < 0
        or not isinstance(errors, list)
        or not isinstance(executions, list)
        or len(executions) != created
    ):
        return "invalid_response", {}
    returned = {
        "created_executions": created,
        "duplicate_executions": duplicate,
        "failed_executions_reported": len(errors),
    }
    outcome = (
        "execution_error_requests"
        if errors
        else (
            "successful_case_requests"
            if created + duplicate
            else "empty_response_requests"
        )
    )

    return outcome, returned


def _post(
    endpoint: str, token: str, case_path: str, timeout: float
) -> tuple[int | None, str, str | None]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(
            {"machine_name": "perlmutter", "archive_path": case_path}
        ).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
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


def _emit(stream: TextIO, token: str, event: str, **fields: Any) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **_redact(fields, token),
    }
    stream.write(json.dumps(record) + "\n")
    stream.flush()
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
    """Do not forward credentials to redirected destinations."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
