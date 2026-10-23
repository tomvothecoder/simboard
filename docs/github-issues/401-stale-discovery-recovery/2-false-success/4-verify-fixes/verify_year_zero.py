"""Replay executions diagnosed with year-zero model dates to verify PR #424.

Preview by default. --apply sends ingestion requests and requires a new --log.
Run on Perlmutter with the backend uv environment. Uploads local executions;
the API does not need an archive mount.

Usage:
    uv run --project backend python docs/github-issues/401-stale-discovery-recovery/2-false-success/4-verify-fixes/verify_year_zero.py [OPTIONS]
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import math
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from app.scripts.ingestion.archive_ingestor_core import IngestionRequestError
from app.scripts.ingestion.hpc_upload_archive_ingestor import (
    _create_case_archive,
    _encode_multipart_form_data,
)

DIRECTORY = Path(__file__).resolve().parent
DEFAULT_SCAN = (
    DIRECTORY.parent
    / "3-debug-validation-errors/validation-scan-20261023T164756281453Z.jsonl"
)
SPEC = importlib.util.spec_from_file_location(
    "year_zero_replay_client",
    DIRECTORY.parent / "2-replay-results/replay_unresolved_executions.py",
)
assert SPEC is not None and SPEC.loader is not None
replay_client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay_client)
ORIGINAL_CLASSIFY = replay_client.classify_response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--log", type=Path, help="New JSONL output; never overwritten")
    parser.add_argument("--limit", type=int, help="Test only the first N executions")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("SIMBOARD_API_BASE_URL"),
    )
    args = parser.parse_args(argv)
    if not args.api_base_url:
        parser.error("Set SIMBOARD_API_BASE_URL or --api-base-url to the public API")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    if not math.isfinite(args.delay) or args.delay < 0:
        parser.error("--delay must be nonnegative and finite")
    try:
        candidates = load_candidates(args.scan)
        endpoint = replay_client._endpoint(args.api_base_url).replace(
            "/from-path", "/from-hpc-upload"
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    selected = candidates[: args.limit]
    if not selected:
        parser.error("No year_zero_date executions found in scan")
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "endpoint": endpoint,
                    "matching": len(candidates),
                    "selected": len(selected),
                    "requests_sent": 0,
                    "executions": selected,
                },
                indent=2,
            )
        )
        return 0

    token = os.environ.get("SIMBOARD_API_TOKEN", "")
    if not token or args.log is None:
        parser.error("--apply requires SIMBOARD_API_TOKEN and --log")
    # Keep the existing replay logging and stop rules, but use local HPC uploads.
    replay_client._post = _post_upload
    replay_client.classify_response = _classify_upload_response
    try:
        with args.log.open("x", encoding="utf-8") as log:
            return replay_client.replay(
                selected, endpoint, token, log, args.timeout, args.delay
            )
    except OSError as exc:
        parser.exit(1, f"Verification stopped: {exc}. Inspect log before restarting.\n")


def load_candidates(scan: Path) -> list[dict[str, str]]:
    """Select every year-zero execution, including secondary errors; deduplicate."""
    candidates = {}
    with scan.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not any(
                    field.get("field") == "simulation_start_date"
                    and field.get("cause") == "year_zero_date"
                    for field in record["fields"]
                ):
                    continue
                path = record["execution_path"]
                candidate = replay_client._candidate(
                    {
                        "machine": "perlmutter",
                        "execution_path": path,
                        "expected_execution_id": Path(path).name,
                        "database_status": "no_exact_path_identity_match",
                    }
                )
                candidates[path] = candidate
                candidate["case_path"] = str(Path(path).parent)
                candidate["container_execution_path"] = path
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                raise ValueError(f"{scan}:{number}: {exc}") from exc

    return list(candidates.values())


def _post_upload(endpoint, token, candidate, timeout):
    try:
        with tempfile.TemporaryDirectory() as temporary:
            archive = _create_case_archive(
                candidate["case_path"], Path(temporary), [candidate["execution_id"]]
            )
            body, boundary = _encode_multipart_form_data(
                archive_path=archive,
                machine_name="perlmutter",
                case_path=candidate["case_path"],
                processed_execution_ids=[candidate["execution_id"]],
            )
            request = urllib.request.Request(
                endpoint,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
            )
            opener = urllib.request.build_opener(replay_client._NoRedirect())
            try:
                with opener.open(request, timeout=timeout) as response:
                    return response.status, response.read().decode(), None
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read().decode(errors="replace"), None
    except (
        OSError,
        urllib.error.URLError,
        http.client.HTTPException,
        IngestionRequestError,
    ) as exc:
        return None, "", str(exc)


def _classify_upload_response(body, execution_id, execution_path):
    # Upload errors reference the API's temporary extraction path, not Perlmutter.
    # Only accept the selected case/execution suffix; preserve raw logged responses.
    if isinstance(body, dict) and isinstance(body.get("errors"), list):
        errors = []
        expected = Path(execution_path)
        for error in body["errors"]:
            if isinstance(error, dict):
                actual = Path(str(error.get("execution_dir", "")))
                if actual.parts[-2:] == expected.parts[-2:]:
                    error = {**error, "execution_dir": execution_path}
            errors.append(error)
        body = {**body, "errors": errors}

    return ORIGINAL_CLASSIFY(body, execution_id, execution_path)


if __name__ == "__main__":
    raise SystemExit(main())
