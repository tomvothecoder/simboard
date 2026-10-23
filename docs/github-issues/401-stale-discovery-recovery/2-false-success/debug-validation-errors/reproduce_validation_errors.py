"""Reproduce three Pydantic error codes from four representative execution fields.

Run from the repository root on a host with archive access:

    uv run --project backend python docs/github-issues/401-stale-discovery-recovery/2-false-success/debug-validation-errors/reproduce_validation_errors.py

Use --archive-root /OLD_PERF for the container mount, or --field to select one
example. Reads metadata only: no API calls, database access, or archive writes.
Each run also saves its JSON output beside this script in a new timestamped
validation-errors-*.json file, including runs with reproduction failures.
Exit 0 means every selected example reproduced its expected error code; exit 1
means an error differed, validation passed, or metadata could not be read or saved.

Only relevant metadata files are parsed, not full archive qualification. Output
includes each source's parsed value, the merged value, and the normalized input
that ingestion sends to Pydantic. Missing optional metadata remains visible.

Run deterministic scalar checks without archive access:

    uv run --project backend python -m doctest docs/github-issues/401-stale-discovery-recovery/2-false-success/debug-validation-errors/reproduce_validation_errors.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.features.ingestion.ingest import _normalize_git_url, _parse_date_field
from app.features.ingestion.parsers.parser import (
    FILE_SPECS,
    _find_casedocs_dirs,
    _find_spec_matches,
)

# One execution from each field-aware group in ../README.md.
EXAMPLES = {
    "compset": (
        "string_type",
        "2025-07/performance_archive_2025_07_30_08_03_25/COMPLETED/"
        "ajonko/BHIST_10xGFED_BC/41134444.250729-031144",
        ("readme_case",),
    ),
    "git_repository_url": (
        "url_scheme",
        "2025-09/performance_archive_2025_09_20_08_05_12/COMPLETED/"
        "gr7610/FAQP-v3.0-ZMv1.AVG_TIME-dt_1800-ne30_ne30/42924507.250919-092412",
        ("git_config",),
    ),
    "grid_name": (
        "string_type",
        "2026-07/performance_archive_2026_07_15_07_26_41/COMPLETED/"
        "anolan/omega-oQU240/55916377.260714-145127",
        ("readme_case",),
    ),
    "simulation_start_date": (
        "date_type",
        "2026-07/performance_archive_2026_07_15_07_26_41/COMPLETED/"
        "sprice/20260624.ERA5r025_r05_IcoswISC30E3r5.pm-cpu.20TR/54984820.260624-163227",
        ("case_docs_env_run", "cpl_log"),
    ),
}
ADAPTERS = {
    "compset": TypeAdapter(str),
    "grid_name": TypeAdapter(str),
    "git_repository_url": TypeAdapter(HttpUrl),
    "simulation_start_date": TypeAdapter(date),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path("/global/cfs/cdirs/e3sm/OLD_PERF"),
        help="Archive mount containing the monthly directories",
    )
    parser.add_argument("--field", choices=EXAMPLES, help="Run only this field")
    args = parser.parse_args(argv)
    results = []
    fields = [args.field] if args.field else EXAMPLES
    for field in fields:
        code, relative_path, specs = EXAMPLES[field]
        execution = args.archive_root / relative_path
        result = {
            "field": field,
            "expected_code": code,
            "execution_dir": str(execution),
        }
        try:
            value, sources = _read_metadata(execution, field, specs)
            normalized = _normalize_value(field, value)
            result.update(
                sources=sources,
                parsed_value=value,
                validation_input=normalized,
                validation_input_type=type(normalized).__name__,
                validation_schema=ADAPTERS[field].json_schema(),
                **_validate_value(field, normalized, code),
            )
        except (OSError, ValueError) as exc:
            result.update(status="read_error", message=str(exc))
        results.append(result)
    rendered = json.dumps(results, indent=2, default=str)
    print(rendered)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path(__file__).resolve().with_name(f"validation-errors-{timestamp}.json")
    try:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    except OSError as exc:
        parser.exit(1, f"Could not save output to {output}: {exc}\n")
    print(f"Saved output to {output}", file=sys.stderr)

    return 0 if all(item["status"] == "reproduced" for item in results) else 1


def _read_metadata(
    execution: Path, field: str, specs: tuple[str, ...]
) -> tuple[str | None, list[dict]]:
    if not execution.is_dir():
        raise FileNotFoundError(f"Execution directory unavailable: {execution}")
    casedocs = _find_casedocs_dirs(str(execution))
    metadata = {}
    sources = []
    for key in specs:
        spec = FILE_SPECS[key]
        matches = _find_spec_matches(str(execution), casedocs, spec)
        if len(matches) > 1:
            raise ValueError(f"Ambiguous {key} metadata: {matches}")
        if not matches:
            sources.append({"file_spec": key, "status": "missing"})
            continue
        parsed = spec["parser"](matches[0])
        sources.append(
            {
                "file_spec": key,
                "path": matches[0],
                "field_present": field in parsed,
                "parsed_value": parsed.get(field),
            }
        )
        # Match ingestion precedence: the coupler clock overrides XML dates.
        metadata.update(parsed)

    return metadata.get(field), sources


def _normalize_value(field: str, value: str | None) -> object:
    if field == "simulation_start_date":
        return _parse_date_field(value)
    if field == "git_repository_url":
        return _normalize_git_url(value)

    return value


def _validate_value(field: str, value: object, expected_code: str) -> dict:
    """Check actual scalar validation, not a hardcoded exception message.

    >>> _validate_value("compset", None, "string_type")["status"]
    'reproduced'
    >>> _validate_value("grid_name", None, "string_type")["status"]
    'reproduced'
    >>> _validate_value("git_repository_url", "ssh://example.org/repo", "url_scheme")["status"]
    'reproduced'
    >>> _validate_value("simulation_start_date", _normalize_value("simulation_start_date", "0000-01-02"), "date_type")["status"]
    'reproduced'
    >>> _validate_value("compset", "BHIST", "string_type")["status"]
    'validated'
    >>> _validate_value("git_repository_url", "not a URL", "url_scheme")["status"]
    'different_error'
    >>> _validate_value("git_repository_url", None, "url_scheme")["status"]
    'skipped'
    >>> _validate_value("git_repository_url", _normalize_value("git_repository_url", "git@github.com:E3SM-Project/E3SM.git"), "url_scheme")["status"]
    'validated'
    """
    # Ingestion validates the optional URL only when normalization returns a value.
    if field == "git_repository_url" and value is None:
        return {"status": "skipped", "errors": []}
    try:
        ADAPTERS[field].validate_python(value)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        reproduced = len(errors) == 1 and errors[0]["type"] == expected_code

        return {
            "status": "reproduced" if reproduced else "different_error",
            "errors": errors,
            "message": str(exc),
        }

    return {"status": "validated", "errors": []}


if __name__ == "__main__":
    raise SystemExit(main())
