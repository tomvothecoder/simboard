"""Inspect unresolved archive paths without API calls, database access, or writes.

Uses only the Python standard library. By default, extracts every unresolved
source-directory path from the adjacent run log and maps /OLD_PERF to Perlmutter.
Prints one JSON object per path to stdout and a status summary to stderr.

Checks directory emptiness, required artifact names, duplicate matches, readable
nonempty files, and broken symlinks. This is a filesystem check, NOT full ingestion
validation: compressed contents, metadata values, and timing LIDs are not parsed.
Exit 0 means all required files passed these checks; 1 means findings; 2 means
invalid input. Missing or unreadable directories have empty=null, not empty=true.

Run with Python 3.11+ on Perlmutter:
    python validate_source_directories.py
    python validate_source_directories.py --archive-root /OLD_PERF
"""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from collections import Counter
from pathlib import Path

DEFAULT_LOG = (
    Path(__file__).resolve().parent.parent
    / "nersc-archive-ingestor-1792807708336-59rl2_nersc-archive-ingestor.log"
)
ARCHIVE_ROOT = Path("/global/cfs/cdirs/e3sm/OLD_PERF")
# Required filename rules from backend/app/features/ingestion/parsers/parser.py.
REQUIRED = (
    ("casedocs", r"env_case\.xml\..*\.gz"),
    ("casedocs", r"env_build\.xml\..*\.gz"),
    ("casedocs", r"env_run\.xml\..*"),
    ("casedocs", r"README\.case\..*\.gz"),
    ("root", r"CaseStatus\..*\.gz"),
    ("root", r"e3sm_timing\..*"),
    ("root", r"GIT_DESCRIBE\..*\.gz"),
    ("root", r"cpl\.log\.\d+\.\d+-\d+(?:\.gz)?$"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--archive-root", type=Path, default=ARCHIVE_ROOT)
    args = parser.parse_args(argv)
    if not args.archive_root.is_absolute():
        parser.error("--archive-root must be absolute")
    try:
        paths = extract_paths(args.log, args.archive_root)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))

    counts: Counter[str] = Counter()
    for path, line_numbers in paths.items():
        result = validate_directory(path)
        result["source_lines"] = line_numbers
        print(json.dumps(result))
        counts[result["status"]] += 1
    print(json.dumps({"paths": len(paths), "statuses": counts}), file=sys.stderr)

    return int(counts["files_present"] != len(paths))


def extract_paths(log: Path, archive_root: Path) -> dict[Path, list[int]]:
    """Keep distinct snapshot paths and all source line references."""
    paths: dict[Path, list[int]] = {}
    with log.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if "event=source_directory_unresolved " not in line:
                continue
            match = re.search(r" execution_path=(/OLD_PERF/\S+)\s*$", line)
            if match is None:
                raise ValueError(f"Unrecognized execution path at {log}:{number}")
            relative = Path(match[1]).relative_to("/OLD_PERF")
            if ".." in relative.parts:
                raise ValueError(f"Path escapes archive root at {log}:{number}")
            paths.setdefault(archive_root / relative, []).append(number)
    if not paths:
        raise ValueError(f"No unresolved source-directory paths found in {log}")

    return dict(sorted(paths.items()))


def validate_directory(path: Path) -> dict:
    """Report filesystem findings; never classify unavailable paths as empty."""
    result = {"path": str(path), "status": "unreadable", "empty": None}
    try:
        entries = list(path.iterdir())
        result["empty"] = not entries
        result["entry_count"] = len(entries)
        case_docs = [
            entry
            for entry in entries
            if entry.name.lower().startswith("casedocs") and entry.is_dir()
        ]
        files = {"root": entries, "casedocs": []}
        for directory in case_docs:
            files["casedocs"].extend(directory.iterdir())
        missing, conflicts, errors = [], {}, []
        for location, pattern in REQUIRED:
            matches = [p for p in files[location] if re.match(pattern, p.name)]
            label = f"{location}: {pattern}"
            if not matches:
                missing.append(label)
            elif len(matches) > 1:
                conflicts[label] = sorted(str(p) for p in matches)
            for match in matches:
                error = _file_error(match)
                if error:
                    errors.append(error)
        result.update(missing=missing, conflicts=conflicts, errors=errors)
        result["status"] = _status(result)
    except FileNotFoundError as exc:
        result.update(status="missing", error=str(exc))
    except NotADirectoryError as exc:
        result.update(status="not_directory", error=str(exc))
    except OSError as exc:
        result["error"] = str(exc)

    return result


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
    if result["conflicts"] or result["errors"]:
        return "invalid_files"
    if result["missing"]:
        return "incomplete"

    return "files_present"


if __name__ == "__main__":
    raise SystemExit(main())
