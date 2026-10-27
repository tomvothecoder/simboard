"""Summarize incomplete discovery decisions from an offline DEBUG ingestion log.

Standard library only; reads the log, not archive directories, state, or APIs.
Default output is Markdown. --details prints one JSON object per unique execution
path, preserving exact logged errors and source lines. Snapshot paths stay distinct.
--report PATH saves the Markdown report. Exit 2 means invalid/inconsistent evidence.

Usage:
    python parse_incomplete_executions.py
    python parse_incomplete_executions.py --report incomplete-executions-report.md
    python parse_incomplete_executions.py --details
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

DEFAULT_LOG = Path(__file__).with_name(
    "nersc-archive-ingestor-1793036867985-zfdtd_nersc-archive-ingestor.log"
)
HOST_ROOT = Path("/global/cfs/cdirs/e3sm/OLD_PERF")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--expected", type=int, default=1883)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = parse_log(args.log, expected=args.expected)
        report = render_report(evidence, args.log)
        if args.report:
            if args.report.resolve() == args.log.resolve():
                raise ValueError("Report must not overwrite the source log")
            args.report.write_text(report, encoding="utf-8")
        if args.details:
            for row in evidence["executions"]:
                print(json.dumps(row))
        else:
            print(report, end="")
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))

    return 0


def parse_log(log: Path, expected: int = 1883) -> dict:
    """Recover paths and exact errors, then reconcile against case/run totals."""
    rows = {}
    cases = {}
    metrics = None
    run_id = None
    offline = False
    with log.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if "event=invocation_started Run ID: " in line:
                if run_id is not None:
                    raise ValueError("Expected a single invocation in the log")
                run_id = line.split("Run ID: ", 1)[1].strip()
            if "Remote state: disabled (offline)" in line:
                offline = True
            if "event=run_metrics payload=" in line:
                metrics = json.loads(line.split("payload=", 1)[1])
            if "event=case_discovered " in line:
                fields = _parse_fields(line.split("event=case_discovered ", 1)[1])
                cases[fields["case"]] = fields
            if "event=execution_decision " not in line:
                continue
            fields = _parse_fields(line.split("event=execution_decision ", 1)[1])
            if fields.get("outcome") != "incomplete":
                continue
            row = _execution_record(fields, number)
            _add_record(rows, row)
    _validate_run(metrics, run_id, offline)
    _reconcile(rows, cases, metrics, expected)

    return {
        "metrics": metrics,
        "executions": [rows[path] for path in sorted(rows)],
        "cases_without_selected_executions": sum(
            int(case["selected"]) == 0
            for case in cases.values()
            if int(case["incomplete"]) > 0
        ),
    }


def render_report(evidence: dict, log: Path) -> str:
    """Render counts and representative paths without guessing filesystem state."""
    rows = evidence["executions"]
    owners = Counter(row["owner"] for row in rows)
    missing = Counter(spec for row in rows for spec in row["missing_file_specs"])
    codes = Counter(code for row in rows for code in {e["code"] for e in row["errors"]})
    profiles = Counter(tuple(row["missing_file_specs"]) for row in rows)
    case_count = len({row["case_path"] for row in rows})
    unselected = evidence["cases_without_selected_executions"]
    lines = [
        "# Incomplete execution discovery",
        "",
        f"**Recovered all {len(rows):,} incomplete execution paths**, matching per-case and run-summary totals.",
        "",
        f"- **Run:** `{evidence['metrics']['run_id']}`; offline dry run with DEBUG logging.",
        f"- **Source:** `{log.name}`.",
        f"- **Coverage:** {case_count:,} case directories; {unselected:,} with no selected executions and {case_count - unselected:,} with selected siblings. No uploads occurred.",
        "- **Error codes (paths affected):** "
        + "; ".join(f"`{code}`: {count:,}" for code, count in codes.most_common())
        + ".",
        "",
        "## Missing artifacts",
        "",
        "| Required filename pattern | Paths missing it |",
        "|---|---:|",
    ]
    lines.extend(f"| `{spec}` | {count:,} |" for spec, count in missing.most_common())
    lines.extend(["", "**Missing-artifact combinations:**"])
    lines.extend(
        f"- **{count:,} {'path' if count == 1 else 'paths'}:** {len(profile)} required artifact types missing."
        for profile, count in profiles.most_common()
    )
    lines.extend(["", "## Largest owner groups", "", "| Owner | Paths |", "|---|---:|"])
    lines.extend(f"| `{owner}` | {count:,} |" for owner, count in owners.most_common(5))
    lines.append(
        f"| Others | {len(rows) - sum(count for _, count in owners.most_common(5)):,} |"
    )
    lines.extend(["", "## Example Perlmutter paths", ""])
    for profile, _ in profiles.most_common():
        row = next(row for row in rows if tuple(row["missing_file_specs"]) == profile)
        lines.extend(
            [
                f"**{row['owner']} — {len(profile)} missing artifact types; log line {row['source_lines'][0]}:**",
                "",
                "```text",
                row["host_path"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "**Interpretation:** these are discovery exclusions, not failed uploads. Missing patterns do not prove directories are empty. This parser did not inspect archive contents or determine why metadata is missing.",
            "",
            "**Next step:** inspect example directories and compare archived copies before choosing recovery or parser fixes. Do not add overlapping source-directory tracking gaps to this total.",
            "",
        ]
    )

    return "\n".join(lines)


def _add_record(rows: dict, row: dict) -> None:
    path = row["container_path"]
    if path in rows:
        if rows[path]["errors"] != row["errors"]:
            raise ValueError(f"Conflicting errors for {path}")
        rows[path]["source_lines"].extend(row["source_lines"])
    else:
        rows[path] = row


def _validate_run(metrics: dict | None, run_id: str | None, offline: bool) -> None:
    if not metrics or metrics.get("run_id") != run_id:
        raise ValueError("Missing or mismatched run_metrics/invocation run ID")
    if (
        not offline
        or not metrics.get("dry_run")
        or not metrics.get("discovery_complete")
    ):
        raise ValueError(
            "Expected a complete dry-run discovery with remote state disabled"
        )
    if metrics.get("status") != "success":
        raise ValueError("Discovery run did not finish successfully")


def _parse_fields(text: str) -> dict:
    """Read mixed bare values and JSON strings/lists/objects without shlex loss."""
    fields = {}
    decoder = json.JSONDecoder()
    while text.strip():
        text = text.lstrip()
        if text.startswith("EXECUTIONS "):
            text = text[len("EXECUTIONS ") :]
        match = re.match(r"(\w+)=", text)
        if not match:
            raise ValueError(f"Malformed event fields: {text[:80]}")
        text = text[match.end() :]
        if not text:
            raise ValueError(f"Missing value for {match[1]}")
        if text[0] in '"[{':
            value, end = decoder.raw_decode(text)
            text = text[end:]
        else:
            parts = text.split(maxsplit=1)
            value, text = parts[0], parts[1] if len(parts) > 1 else ""
        fields[match[1]] = value

    return fields


def _execution_record(fields: dict, number: int) -> dict:
    case = Path(fields["case"])
    execution_id = fields["execution_id"]
    if (
        case.is_absolute()
        or ".." in case.parts
        or Path(execution_id).name != execution_id
    ):
        raise ValueError(f"Unsafe execution path at line {number}")
    if not re.fullmatch(r"\d+\.\d+-\d+", execution_id) or len(case.parts) < 5:
        raise ValueError(f"Unrecognized archive path at line {number}")
    path = str(Path("/OLD_PERF") / case / execution_id)
    errors = fields.get("errors")
    if not isinstance(errors, list) or not errors:
        raise ValueError(f"Missing detailed errors at line {number}")
    for error in errors:
        if not isinstance(error, dict) or not {"code", "message"} <= error.keys():
            raise ValueError(f"Malformed detailed error at line {number}")
        if error["code"] == "missing_required_file" and not error.get("file_spec"):
            raise ValueError(f"Missing file specification at line {number}")
        if error.get("execution_dir", path) != path:
            raise ValueError(f"Error path disagrees with decision at line {number}")
    if int(fields.get("error_count", len(errors))) != len(errors):
        raise ValueError(f"Error count disagrees with payload at line {number}")

    return {
        "owner": case.parts[-2],
        "case_name": case.name,
        "case_path": str(case),
        "execution_id": execution_id,
        "container_path": path,
        "host_path": str(HOST_ROOT / case / execution_id),
        "missing_file_specs": sorted(
            {
                error["file_spec"]
                for error in errors
                if error["code"] == "missing_required_file"
            }
        ),
        "errors": errors,
        "source_lines": [number],
    }


def _reconcile(rows: dict, cases: dict, metrics: dict, expected: int) -> None:
    counts = Counter(row["case_path"] for row in rows.values())
    case_counts = {case: int(fields["incomplete"]) for case, fields in cases.items()}
    if counts != Counter({case: count for case, count in case_counts.items() if count}):
        raise ValueError("Incomplete execution paths disagree with per-case totals")
    reported = metrics["executions"]["incomplete"]
    if len(rows) != reported or len(rows) != expected:
        raise ValueError(
            f"Incomplete count mismatch: extracted={len(rows)}, summary={reported}, expected={expected}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
