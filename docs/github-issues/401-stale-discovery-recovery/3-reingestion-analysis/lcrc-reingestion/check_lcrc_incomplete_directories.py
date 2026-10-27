"""Check logged incomplete Chrysalis archive paths directly on LCRC (Python 3.11+).

Self-contained, standard library only. Reads a completed DEBUG discovery log,
derives its archive root and incomplete count, then checks the listed directories.
Supports Chrysalis snapshots with or without a COMPLETED status directory.
No API/database access, ingestion, state changes, or archive writes.

Usage on LCRC:
    python check_lcrc_incomplete_directories.py --log /path/to/offline-debug.log
    python check_lcrc_incomplete_directories.py --log /path/to/offline-debug.log --report report.md
    python check_lcrc_incomplete_directories.py --log /path/to/offline-debug.log --details

Default stdout: Markdown. --details: per-path JSONL with available log diagnostics.
--archive-root overrides the logged root for a different filesystem mount.
--report optionally saves Markdown outside the archive tree. Exit 0 means no
filesystem findings; 1 means findings; 2 means invalid input or output failure.
Checks filenames, duplicates, empty directories and readable nonempty files;
does NOT parse metadata values or validate gzip integrity. No DEBUG paths means
no filesystem scan: INFO-only logs cannot identify all incomplete executions.
"""

from __future__ import annotations

import argparse
import json
import re
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Required filename rules from backend/app/features/ingestion/parsers/parser.py.
REQUIRED = (
    ("casedocs", "env_case.xml..*.gz", r"env_case\.xml\..*\.gz"),
    ("casedocs", "env_build.xml..*.gz", r"env_build\.xml\..*\.gz"),
    ("casedocs", "env_run.xml..*", r"env_run\.xml\..*"),
    ("casedocs", "README.case..*.gz", r"README\.case\..*\.gz"),
    ("root", "CaseStatus..*.gz", r"CaseStatus\..*\.gz"),
    ("root", "e3sm_timing..*..*", r"e3sm_timing\..*"),
    ("root", "GIT_DESCRIBE..*.gz", r"GIT_DESCRIBE\..*\.gz"),
    ("root", "cpl.log.<execution_id>[.gz]", r"cpl\.log\.\d+\.\d+-\d+(?:\.gz)?$"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    try:
        evidence = parse_log(args.log)
        root = args.archive_root or evidence["archive_root"]
        _validate_paths(root, args.report, args.log)
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for execution in evidence["executions"]:
            result = inspect_directory(root / execution["relative_path"])
            result.update(execution)
            result["missing_matches_log"] = (
                result["missing"] == execution["logged_missing"]
                if result["missing"] is not None
                else None
            )
            rows.append(result)
        report = render_report(rows, evidence, started)
        if args.report:
            args.report.write_text(report, encoding="utf-8")
        if args.details:
            for row in rows:
                print(json.dumps(row))
        else:
            print(report, end="")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))

    return int(any(row["status"] != "files_present" for row in rows))


def parse_log(log: Path) -> dict:
    """Require per-path evidence and reconcile against this log, not Perlmutter."""
    roots, run_ids, summaries, decisions, cases = [], [], [], [], {}
    with log.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if "event=invocation_started Run ID: " in line:
                run_ids.append(line.split("Run ID: ", 1)[1].strip())
            if "INFO CONFIG Archive root: " in line:
                roots.append(Path(line.split("Archive root: ", 1)[1].strip()))
            if "event=run_metrics payload=" in line:
                summaries.append(json.loads(line.split("payload=", 1)[1]))
            if "event=case_discovered " in line:
                fields = _fields(line.split("event=case_discovered ", 1)[1])
                cases[fields["case"]] = int(fields["incomplete"])
            if "event=execution_decision " in line:
                fields = _fields(line.split("event=execution_decision ", 1)[1])
                if fields.get("outcome") == "incomplete":
                    decisions.append((number, fields))
    metrics, root = _validate_run(run_ids, roots, summaries)
    reported = metrics["executions"]["incomplete"]
    if reported and not decisions:
        raise ValueError(
            f"Log reports {reported:,} incomplete executions but has no incomplete DEBUG decisions. "
            "Capture an offline scan with DRY_RUN=true, DRY_RUN_USE_REMOTE_STATE=false, "
            "and SIMBOARD_INGESTION_LOG_LEVEL=DEBUG; no directories were inspected."
        )
    rows = _execution_records(decisions, root)
    actual = Counter(row["relative_case"] for row in rows)
    expected = Counter(
        {_relative_case(case, root): count for case, count in cases.items() if count}
    )
    if len(rows) != reported or actual != expected:
        raise ValueError(
            f"Incomplete paths disagree with log totals: extracted={len(rows)}, summary={reported}"
        )

    return {"metrics": metrics, "archive_root": root, "executions": rows}


def inspect_directory(path: Path) -> dict:
    """Distinguish confirmed empty roots from unavailable or partial inspections."""
    result = {
        "path": str(path),
        "status": "inspection_error",
        "empty": None,
        "missing": None,
    }
    try:
        entries = sorted(path.iterdir())
    except FileNotFoundError as exc:
        return {**result, "status": "missing_directory", "error": str(exc)}
    except NotADirectoryError as exc:
        return {**result, "status": "not_directory", "error": str(exc)}
    except OSError as exc:
        return {**result, "error": str(exc)}
    result.update(empty=not entries, entry_count=len(entries))
    try:
        files = _metadata_entries(entries)
        missing, conflicts, errors = [], {}, []
        for location, label, pattern in REQUIRED:
            matches = [file for file in files[location] if re.match(pattern, file.name)]
            if not matches:
                missing.append(label)
            elif len(matches) > 1:
                conflicts[label] = [str(file.relative_to(path)) for file in matches]
            errors.extend(error for file in matches if (error := _file_error(file)))
        result.update(missing=sorted(missing), conflicts=conflicts, file_errors=errors)
        result["status"] = _status(result)
    except OSError as exc:
        result["error"] = str(exc)

    return result


def render_report(rows: list[dict], evidence: dict, started: str) -> str:
    metrics = evidence["metrics"]
    counts = Counter(row["status"] for row in rows)
    comparisons = Counter(row["missing_matches_log"] for row in rows)
    owners = Counter(row["owner"] for row in rows)
    lines = [
        "# LCRC incomplete-directory inspection",
        "",
        f"**Inspected {len(rows):,} distinct Chrysalis execution paths.**",
        "",
        f"- **Inspection started (UTC):** `{started}`.",
        f"- **Source run:** `{metrics['run_id']}`; discovery complete; dry run: `{metrics['dry_run']}`.",
        "- **Scope:** only incomplete paths recorded in this log. Remote-state/checkpoint filtering may limit a state-aware run.",
        "",
        "| Current finding | Paths |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{status}` | {count:,} |" for status, count in counts.most_common()
    )
    lines.extend(
        [
            "",
            f"**Missing patterns:** {comparisons[True]:,} match the log; {comparisons[False]:,} differ; {comparisons[None]:,} could not be checked.",
            "",
            "## Largest owner groups",
            "",
            "| Owner | Paths |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| `{owner}` | {count:,} |" for owner, count in owners.most_common(5))
    other = len(rows) - sum(count for _, count in owners.most_common(5))
    if other:
        lines.append(f"| Others | {other:,} |")
    lines.extend(["", "## Example paths", ""])
    examples = {}
    for row in rows:
        examples.setdefault((row["status"], tuple(row["missing"] or [])), row)
    for row in list(examples.values())[:3]:
        lines.extend(
            [
                f"**{row['owner']}: `{row['status']}`; log line {row['source_lines'][0]}.**",
                "",
                "```text",
                row["path"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "**Limits:** empty means zero entries, including hidden entries. Checks cover required filename matches and readable nonempty files, not gzip integrity or metadata values. Causes remain unconfirmed. No archive files, API/database records, or ingestion state were changed.",
            "",
        ]
    )

    return "\n".join(lines)


def _validate_run(run_ids: list, roots: list, summaries: list) -> tuple[dict, Path]:
    if len(run_ids) != 1 or len(roots) != 1 or len(summaries) != 1:
        raise ValueError(
            "Expected one invocation, archive root, and final run_metrics record"
        )
    metrics, root = summaries[0], roots[0]
    if metrics["run_id"] != run_ids[0] or metrics["machine"] != "chrysalis":
        raise ValueError("Expected matching Chrysalis invocation and run_metrics")
    if not metrics["discovery_complete"] or metrics["scan_mode"] != "archive":
        raise ValueError("Expected completed archive discovery")
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("Invalid logged archive root")

    return metrics, root


def _execution_records(decisions: list, root: Path) -> list[dict]:
    rows = {}
    for number, fields in decisions:
        case = _relative_case(fields["case"], root)
        execution_id = fields["execution_id"]
        if len(Path(case).parts) < 4 or not re.fullmatch(r"\d+\.\d+-\d+", execution_id):
            raise ValueError(f"Invalid execution path at line {number}")
        relative = str(Path(case) / execution_id)
        errors = fields.get("errors", [])
        if not isinstance(errors, list) or any(
            not isinstance(error, dict) for error in errors
        ):
            raise ValueError(f"Malformed error payload at line {number}")
        for error in errors:
            if (
                "execution_dir" in error
                and _relative_case(error["execution_dir"], root) != relative
            ):
                raise ValueError(f"Error path disagrees with decision at line {number}")
        missing = fields.get("missing_file_specs")
        if not isinstance(missing, list) or any(
            not isinstance(spec, str) for spec in missing
        ):
            raise ValueError(f"Missing required-file specifications at line {number}")
        row = {
            "owner": Path(case).parts[-2],
            "execution_id": execution_id,
            "relative_case": case,
            "relative_path": relative,
            "logged_missing": sorted(set(missing)),
            "logged_errors": errors,
            "logged_error_codes": fields.get("error_codes", []),
            "logged_error_count": int(fields["error_count"])
            if "error_count" in fields
            else None,
            "logged_detail": fields.get("detail"),
            "source_lines": [number],
        }
        _add_record(rows, relative, row)

    return [rows[path] for path in sorted(rows)]


def _add_record(rows: dict, path: str, row: dict) -> None:
    if path in rows:
        previous = rows[path]
        if (previous["logged_missing"], previous["logged_errors"]) != (
            row["logged_missing"],
            row["logged_errors"],
        ):
            raise ValueError(f"Conflicting incomplete evidence for {path}")
        previous["source_lines"].extend(row["source_lines"])
    else:
        rows[path] = row


def _relative_case(case: str, root: Path) -> str:
    path = Path(case)
    if ".." in path.parts:
        raise ValueError("Case path escapes the archive root")
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            path = path.relative_to(root.resolve())

    return str(path)


def _fields(text: str) -> dict:
    result = {}
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
        result[match[1]] = value

    return result


def _validate_paths(root: Path, report: Path | None, log: Path) -> None:
    if not root.is_absolute():
        raise ValueError("--archive-root must be absolute")
    if report is not None:
        target = report.resolve()
        if target == log.resolve() or target.is_relative_to(root.resolve()):
            raise ValueError(
                "Report must not overwrite the log or write inside the archive"
            )


def _metadata_entries(entries: list[Path]) -> dict[str, list[Path]]:
    files = {"root": entries, "casedocs": []}
    for entry in entries:
        if entry.name.lower().startswith("casedocs") and stat.S_ISDIR(
            entry.stat().st_mode
        ):
            files["casedocs"].extend(sorted(entry.iterdir()))

    return files


def _file_error(path: Path) -> str | None:
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            return f"Not a regular file: {path}"
        if metadata.st_size == 0:
            return f"Zero-byte file: {path}"
        with path.open("rb") as stream:
            stream.read(1)
    except OSError as exc:
        return f"{path}: {exc}"

    return None


def _status(result: dict) -> str:
    if result["empty"]:
        return "empty"
    if result["conflicts"] or result["file_errors"]:
        return "invalid_files"
    if result["missing"]:
        return "incomplete"

    return "files_present"


if __name__ == "__main__":
    raise SystemExit(main())
