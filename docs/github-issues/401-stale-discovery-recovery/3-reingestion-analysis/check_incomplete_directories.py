"""Inspect actual incomplete execution directories using the adjacent log parser.

Python 3.11+; standard library and sibling parse_incomplete_executions.py only.
Reads each unique logged path on Perlmutter. No API, database, or archive writes.
Checks root-directory emptiness, required filename matches, duplicate matches,
and readable nonempty regular files. Does not parse metadata or gzip contents.

Default output: Markdown summary. --details: JSONL with every path and finding.
--report PATH also saves the Markdown report outside the archive tree.
Exit 0: no findings; 1: filesystem findings; 2: invalid input/output error.

Usage: python check_incomplete_directories.py [--archive-root /OLD_PERF]
"""

from __future__ import annotations

import argparse
import json
import re
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from parse_incomplete_executions import DEFAULT_LOG, HOST_ROOT, parse_log

# Required filename matching rules from ingestion/parsers/parser.py:FILE_SPECS.
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
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--expected", type=int, default=1883)
    parser.add_argument("--archive-root", type=Path, default=HOST_ROOT)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if not args.archive_root.is_absolute():
        parser.error("--archive-root must be absolute")
    try:
        _validate_output(args.report, args.log, args.archive_root)
        evidence = parse_log(args.log, expected=args.expected)
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = inspect_executions(evidence["executions"], args.archive_root)
        report = render_report(rows, evidence["metrics"]["run_id"], started)
        if args.report:
            args.report.write_text(report, encoding="utf-8")
        if args.details:
            for row in rows:
                print(json.dumps(row))
        else:
            print(report, end="")
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))

    return int(any(row["status"] != "files_present" for row in rows))


def inspect_executions(executions: list[dict], archive_root: Path) -> list[dict]:
    """Use reconciled log paths; compare current missing patterns to log evidence."""
    rows = []
    for execution in executions:
        relative = Path(execution["container_path"]).relative_to("/OLD_PERF")
        if ".." in relative.parts:
            raise ValueError("Execution path escapes archive root")
        result = inspect_directory(archive_root / relative)
        result.update(
            owner=execution["owner"],
            execution_id=execution["execution_id"],
            source_lines=execution["source_lines"],
            logged_missing=execution["missing_file_specs"],
            missing_matches_log=(
                result["missing"] == execution["missing_file_specs"]
                if result["missing"] is not None
                else None
            ),
        )
        rows.append(result)

    return rows


def inspect_directory(path: Path) -> dict:
    """Keep missing/unreadable directories distinct from confirmed empty ones."""
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
    result.update(
        empty=not entries,
        entry_count=len(entries),
        root_entries=[p.name for p in entries],
    )
    try:
        files = _metadata_entries(entries)
        missing, conflicts, file_errors, matched = [], {}, [], {}
        for location, label, pattern in REQUIRED:
            matches = [p for p in files[location] if re.match(pattern, p.name)]
            matched[label] = [str(p.relative_to(path)) for p in matches]
            if not matches:
                missing.append(label)
            elif len(matches) > 1:
                conflicts[label] = matched[label]
            file_errors.extend(error for p in matches if (error := _file_error(p)))
        result.update(
            missing=sorted(missing),
            conflicts=conflicts,
            file_errors=file_errors,
            matched_files=matched,
        )
        result["status"] = _status(result)
    except OSError as exc:
        result["error"] = str(exc)

    return result


def render_report(rows: list[dict], run_id: str, started: str) -> str:
    counts = Counter(row["status"] for row in rows)
    owners = Counter((row["owner"], row["status"]) for row in rows)
    comparisons = Counter(row["missing_matches_log"] for row in rows)
    lines = [
        "# Direct inspection of incomplete execution directories",
        "",
        f"**Inspected {len(rows):,} distinct execution paths from the DEBUG log.**",
        "",
        f"- **Inspection started (UTC):** `{started}`.",
        f"- **Source run:** `{run_id}`.",
        "- **Method:** read-only filesystem checks using `check_incomplete_directories.py`.",
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
            f"**Missing-artifact comparison:** {comparisons[True]:,} match the log; {comparisons[False]:,} differ; {comparisons[None]:,} could not be checked.",
            "",
            "## Owner breakdown",
            "",
            "| Owner | Current finding | Paths |",
            "|---|---|---:|",
        ]
    )
    lines.extend(
        f"| `{owner}` | `{status}` | {count:,} |"
        for (owner, status), count in owners.most_common(6)
    )
    remaining = len(rows) - sum(count for _, count in owners.most_common(6))
    if remaining:
        lines.append(f"| Others | Combined | {remaining:,} |")
    lines.extend(["", "## Example paths", ""])
    examples = {}
    for row in rows:
        examples.setdefault((row["status"], tuple(row["missing"] or [])), row)
    for row in list(examples.values())[:4]:
        entries = row.get("entry_count", "unknown")
        lines.extend(
            [
                f"**{row['owner']}: `{row['status']}`, {entries} entries; log line {row['source_lines'][0]}.**",
                "",
                "```text",
                row["path"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "**Limits:** `empty` means zero directory entries, including hidden entries. A directory containing an empty subdirectory is not empty. Checks cover required filename matches and readable nonempty files, not gzip integrity or metadata values. Why artifacts are missing remains unconfirmed.",
            "",
            "**Next step:** inspect collection/cleanup history and locate complete copies. No archive files, database records, or ingestion state were changed. These paths overlap source-directory tracking gaps; do not add those counts.",
            "",
        ]
    )

    return "\n".join(lines)


def _validate_output(report: Path | None, log: Path, archive_root: Path) -> None:
    if report is None:
        return
    target = report.resolve()
    if target == log.resolve() or target.is_relative_to(archive_root.resolve()):
        raise ValueError(
            "Report must not overwrite the source log or write inside the archive"
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
    if result["file_errors"] or result["conflicts"]:
        return "invalid_files"
    if result["missing"]:
        return "incomplete"

    return "files_present"


if __name__ == "__main__":
    raise SystemExit(main())
