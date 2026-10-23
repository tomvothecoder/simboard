"""Read failed replay executions and collect all ingestion pre-case field errors.

No API calls, database access, or archive writes. Save timestamped detail JSONL
and summary JSON beside this script. This is scalar diagnosis, not full ingestion.
Exit 0 means the scan completed, even when validation errors exist. Exit 1 means
some fields could not be checked; exit 2 means invalid input or an output failure.

Run from the repository root on a host with archive access:

    uv run --project backend python docs/github-issues/401-stale-discovery-recovery/2-false-success/debug-validation-errors/scan_validation_errors.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.features.ingestion.ingest import _normalize_git_url, _parse_date_field
from app.features.ingestion.parsers.parser import (
    FILE_SPECS,
    _find_casedocs_dirs,
    _find_spec_matches,
    _resolve_execution_id,
)
from app.features.ingestion.parsers.utils import _open_text

SOURCE_ROOT = Path("/global/cfs/cdirs/e3sm/OLD_PERF")
FIELD_SOURCES = {
    "execution_id": ("e3sm_timing",),
    "compset": ("readme_case",),
    "compset_alias": ("case_docs_env_case",),
    "grid_name": ("readme_case",),
    "grid_resolution": ("case_docs_env_build",),
    "initialization_type": ("case_docs_env_run",),
    "simulation_start_date": ("case_docs_env_run", "cpl_log"),
    "git_repository_url": ("git_config",),
}
ADAPTERS = {field: TypeAdapter(str) for field in FIELD_SOURCES}
ADAPTERS.update(
    simulation_start_date=TypeAdapter(date), git_repository_url=TypeAdapter(HttpUrl)
)
READ_ERRORS = (
    OSError,
    EOFError,
    UnicodeError,
    ValueError,
    TypeError,
    ET.ParseError,
    zlib.error,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent.parent
        / "2-replay-results/replay-final.jsonl",
    )
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--archive-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument(
        "--limit", type=int, help="Scan only the first N unique candidates"
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    try:
        candidates = read_candidates(args.log, args.source_root, args.archive_root)
        selected = candidates[: args.limit]
        if not selected:
            parser.error("No failed executions with ValidationError found")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = (
            Path(__file__).resolve().with_name(f"validation-scan-{timestamp}.jsonl")
        )
        summary_path = output.with_name(f"{output.stem}-groups.json")
        results = []
        with output.open("x", encoding="utf-8") as stream:
            print(f"Saving execution details to {output}", file=sys.stderr)
            for candidate in selected:
                try:
                    result = diagnose_execution(candidate)
                except Exception as exc:
                    result = _blocked_execution(candidate, "unexpected_error", exc)
                stream.write(json.dumps(result, default=str) + "\n")
                stream.flush()
                results.append(result)
        summary = summarize_results(results)
        summary.update(
            source_log=str(args.log.resolve()),
            source_root=str(args.source_root),
            archive_root=str(args.archive_root),
            candidates=len(candidates),
            selected=len(selected),
            not_selected=len(candidates) - len(selected),
            details_file=str(output),
        )
        rendered = json.dumps(summary, indent=2, default=str)
        with summary_path.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        print(
            "Scan interrupted; detail JSONL may be partial. No complete summary.",
            file=sys.stderr,
        )
        return 130
    print(rendered)
    print(f"Saved grouped counts to {summary_path}", file=sys.stderr)

    return (
        1
        if summary["executions_with_source_issues"] or summary["blocked_fields"]
        else 0
    )


def read_candidates(log: Path, source_root: Path, archive_root: Path) -> list[dict]:
    """Keep the latest completed attempt per path, then select validation failures."""
    latest = {}
    run_ids = set()
    with log.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or not isinstance(
                    record.get("event"), str
                ):
                    raise ValueError("Expected a JSON event object")
                if not isinstance(record.get("run_id"), str) or not record["run_id"]:
                    raise ValueError("run_id must be a nonempty string")
                run_ids.add(record["run_id"])
                if record["event"] != "request_finished":
                    continue
                timestamp, candidate = _candidate_from_record(
                    record, source_root, archive_root
                )
                path = candidate["execution_path"]
                if path not in latest or timestamp >= latest[path][0]:
                    latest[path] = (timestamp, candidate)
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                raise ValueError(f"{log}:{number}: {exc}") from exc
    if len(run_ids) != 1:
        raise ValueError("Expected one nonempty replay run; do not mix run IDs")

    return [
        candidate
        for _, candidate in latest.values()
        if candidate["outcome"] == "failed"
        and any(
            error.get("error_type") == "ValidationError"
            for error in candidate["original_errors"]
        )
    ]


def diagnose_execution(candidate: dict) -> dict:
    """Parse each relevant source once and validate every pre-case scalar field."""
    execution = Path(candidate["local_execution_path"])
    result = {**candidate, "sources": {}, "fields": [], "source_issues": []}
    try:
        if not execution.is_dir():
            raise FileNotFoundError(f"Execution directory unavailable: {execution}")
        casedocs = _find_casedocs_dirs(str(execution))
    except OSError as exc:
        return _blocked_execution(candidate, "read_error", exc)
    metadata = {}
    for key in dict.fromkeys(key for keys in FIELD_SOURCES.values() for key in keys):
        source = _read_source(execution, casedocs, key)
        result["sources"][key] = source
        if source["status"] == "parsed":
            metadata.update(source["metadata"])
        elif source["status"] != "missing_optional":
            result["source_issues"].append(
                {
                    "file_spec": key,
                    "code": source["status"],
                    "message": source.get("message", ""),
                }
            )
    for field, keys in FIELD_SOURCES.items():
        sources = [result["sources"][key] for key in keys]
        detail = {
            "field": field,
            "source_specs": keys,
            "parsed_value": metadata.get(field),
            "validation_schema": ADAPTERS[field].json_schema(),
        }
        if _sources_block_field(field, sources):
            detail.update(status="blocked", cause="source_unavailable", errors=[])
        else:
            detail.update(_check_field(field, metadata.get(field), execution, sources))
        for error in detail["errors"]:
            error["matches_original"] = any(
                original.get("field") == field and original.get("code") == error["type"]
                for original in candidate["original_errors"]
            )
        result["fields"].append(detail)

    return result


def summarize_results(results: list[dict]) -> dict:
    """Count executions separately from field errors, including secondary failures."""
    groups = {}
    original_groups = {}
    source_groups = {}
    statuses = Counter()
    affected = set()
    for result in results:
        path = result["execution_path"]
        for original in result["original_errors"]:
            key = (
                str(original.get("field") or "unknown"),
                str(original.get("code") or "unknown"),
            )
            original_groups.setdefault(key, set()).add(path)
        for issue in result["source_issues"]:
            key = (issue["file_spec"], issue["code"])
            source_groups.setdefault(key, set()).add(path)
        for field in result["fields"]:
            statuses[field["status"]] += 1
            for error in field["errors"]:
                affected.add(path)
                key = (field["field"], error["type"], field["cause"])
                group = groups.setdefault(
                    key,
                    {
                        "executions": set(),
                        "field_errors": 0,
                        "matching_original_errors": 0,
                    },
                )
                group["executions"].add(path)
                group["field_errors"] += 1
                group["matching_original_errors"] += int(error["matches_original"])

    return {
        "completed": len(results),
        "executions_with_validation_errors": len(affected),
        "field_error_count": sum(group["field_errors"] for group in groups.values()),
        "executions_with_source_issues": sum(
            bool(result["source_issues"]) for result in results
        ),
        "blocked_fields": statuses["blocked"],
        "field_status_counts": dict(statuses),
        "validation_groups": [
            {
                "field": field,
                "code": code,
                "cause": cause,
                "affected_executions": len(group["executions"]),
                "field_errors": group["field_errors"],
                "matching_original_errors": group["matching_original_errors"],
                "additional_errors": group["field_errors"]
                - group["matching_original_errors"],
                "examples": sorted(group["executions"])[:3],
            }
            for (field, code, cause), group in sorted(groups.items())
        ],
        "original_error_groups": [
            {"field": field, "code": code, "affected_executions": len(paths)}
            for (field, code), paths in sorted(original_groups.items())
        ],
        "source_issue_groups": [
            {
                "file_spec": spec,
                "code": code,
                "affected_executions": len(paths),
                "examples": sorted(paths)[:3],
            }
            for (spec, code), paths in sorted(source_groups.items())
        ],
    }


def _candidate_from_record(
    record: dict, source_root: Path, archive_root: Path
) -> tuple[datetime, dict]:
    path = Path(record["execution_path"])
    if (
        not path.is_absolute()
        or not source_root.is_absolute()
        or not archive_root.is_absolute()
    ):
        raise ValueError("Execution path and archive roots must be absolute")
    relative = path.relative_to(source_root)
    if not relative.parts or ".." in relative.parts:
        raise ValueError("Execution path escapes source root")
    timestamp = datetime.fromisoformat(record["timestamp"])
    if timestamp.tzinfo is None:
        raise ValueError("Completed timestamp must include a timezone")
    body = record.get("response_body")
    errors = body.get("errors", []) if isinstance(body, dict) else []
    if not isinstance(errors, list) or any(
        not isinstance(error, dict) for error in errors
    ):
        raise ValueError("Response errors must be a list of objects")
    expected_paths = {str(path)}
    if record.get("container_execution_path"):
        expected_paths.add(str(Path(record["container_execution_path"])))
    for error in errors:
        if (
            error.get("execution_dir")
            and str(Path(error["execution_dir"])) not in expected_paths
        ):
            raise ValueError(
                "Response contains errors for another execution; expected a single-execution replay"
            )
    candidate = {
        "execution_path": str(path),
        "local_execution_path": str(archive_root / relative),
        "original_errors": errors,
        "outcome": record["outcome"],
        "timestamp": record["timestamp"],
        "attempt_id": record["attempt_id"],
    }

    return timestamp, candidate


def _blocked_execution(candidate: dict, code: str, exc: Exception) -> dict:
    return {
        **candidate,
        "sources": {},
        "source_issues": [
            {
                "file_spec": "execution_directory",
                "code": code,
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        ],
        "fields": [
            {
                "field": field,
                "status": "blocked",
                "cause": "source_unavailable",
                "errors": [],
            }
            for field in FIELD_SOURCES
        ],
    }


def _sources_block_field(field: str, sources: list[dict]) -> bool:
    if field == "simulation_start_date":
        xml, coupler = sources
        if (
            coupler["status"] == "parsed"
            and "simulation_start_date" in coupler["metadata"]
        ):
            return False
        # Production suppresses coupler read errors and falls back to XML dates.
        if xml["status"] == "parsed" and coupler["status"] in {
            "parsed",
            "missing_required",
            "read_or_parse_error",
        }:
            return False

    return any(
        source["status"] not in {"parsed", "missing_optional"} for source in sources
    )


def _read_source(execution: Path, casedocs: list[str], key: str) -> dict:
    spec = FILE_SPECS[key]
    matches = []
    try:
        matches = sorted(_find_spec_matches(str(execution), casedocs, spec))
        if not matches:
            return {
                "status": "missing_required"
                if spec.get("required")
                else "missing_optional"
            }
        if len(matches) > 1:
            return {"status": "ambiguous", "paths": matches}
        path = Path(matches[0])
        # Preflight detects read/XML failures that production parsers can suppress.
        text = _open_text(path)
        xml = ET.fromstring(text) if key.startswith("case_docs_") else None
        metadata = spec["parser"](path)
        source = {"status": "parsed", "path": str(path), "metadata": metadata}
        if xml is not None:
            entries = {
                "COMPSET",
                "GRID",
                "RUN_TYPE",
                "RUN_STARTDATE",
                "RUN_REFDATE",
                "CONTINUE_RUN",
            }
            source["xml_entries"] = {
                entry.get("id"): entry.get("value", entry.text)
                for entry in xml.iter("entry")
                if entry.get("id") in entries
            }
        if key == "readme_case":
            commands = [line for line in text.splitlines() if "create_newcase" in line]
            source["create_newcase_lines"] = [line[:2000] for line in commands[:5]]
            source["flag_mentions"] = {
                field: any(flag in line for line in commands)
                for field, flag in (("compset", "--compset"), ("grid_name", "--res"))
            }
        return source
    except READ_ERRORS as exc:
        return {
            "status": "parse_error"
            if isinstance(exc, ET.ParseError)
            else "read_or_parse_error",
            "paths": matches,
            "message": str(exc),
        }


def _check_field(field: str, raw: object, execution: Path, sources: list[dict]) -> dict:
    value = raw
    if field == "execution_id":
        try:
            value = _resolve_execution_id(raw, str(execution))
        except FileNotFoundError as exc:
            return {
                "status": "blocked",
                "cause": "missing_timing_lid",
                "message": str(exc),
                "errors": [],
            }
    elif field == "simulation_start_date":
        value = _parse_date_field(raw)
    elif field == "git_repository_url":
        value = _normalize_git_url(raw)
    detail = {
        "validation_input": value,
        "validation_input_type": type(value).__name__,
        "status": "validated",
        "errors": [],
    }
    if field == "git_repository_url" and value is None:
        return {**detail, "status": "skipped"}
    try:
        ADAPTERS[field].validate_python(value)
    except ValidationError as exc:
        detail.update(
            status="invalid",
            errors=exc.errors(include_url=False),
            cause=_observed_cause(field, raw, value, sources),
        )

    return detail


def _observed_cause(field: str, raw: object, value: object, sources: list[dict]) -> str:
    if raw is not None and value is None:
        return (
            "year_zero_date"
            if re.match(r"^0000-", str(raw))
            else "normalization_returned_none"
        )
    if raw is None:
        if field in {"compset", "grid_name"}:
            source = sources[0]
            if not source.get("create_newcase_lines"):
                return "create_newcase_not_found"
            return (
                "flag_present_but_unparsed"
                if source["flag_mentions"][field]
                else "flag_not_found"
            )
        return "parser_returned_none"
    if field == "git_repository_url":
        return (
            f"url_scheme:{str(value).split(':', 1)[0]}"
            if ":" in str(value)
            else "url_without_scheme"
        )

    return "invalid_parsed_value"


if __name__ == "__main__":
    raise SystemExit(main())
