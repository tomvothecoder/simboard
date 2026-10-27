"""Count provenance scripts in execution paths with ambiguous-script warnings.

Read-only; Python 3.11+ standard library only. Extracts paths from the adjacent
ingestion log and maps /OLD_PERF to the Perlmutter host archive root. Uses CASE
from env_case.xml and SimBoard's provenance filename matching rules. Counts
physical matching files separately from unique provenance names, since duplicate
copies or gzip/plain copies of one provenance name are not distinct scripts.
Does not select a script, compare contents, ingest data, or change archive/state.

Usage: python inspect_run_scripts.py [--log PATH] [--archive-root PATH]
Output: one JSON object per execution on stdout; counts on stderr.
Exit codes: 0 = inspection completed (ambiguity is expected), 1 = inspection
errors, 2 = invalid input. This does not count unrelated shell scripts/wrappers.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from pathlib import Path

DEFAULT_LOG = Path(__file__).with_name(
    "nersc-archive-ingestor-1792807708336-59rl2_nersc-archive-ingestor.log"
)
ARCHIVE_ROOT = Path("/global/cfs/cdirs/e3sm/OLD_PERF")
WARNING = re.compile(
    r"Skipping run-script artifact for '(/OLD_PERF/[^']+)': "
    r"multiple E3SM provenance scripts\."
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

    statuses: Counter[str] = Counter()
    counts: Counter[int] = Counter()
    for path, line_numbers in paths.items():
        result = inspect_directory(path)
        result["source_lines"] = line_numbers
        print(json.dumps(result))
        statuses[result["status"]] += 1
        if result["status"] != "error":
            counts[result["unique_script_count"]] += 1
    print(
        json.dumps(
            {
                "paths": len(paths),
                "warning_occurrences": sum(map(len, paths.values())),
                "statuses": statuses,
                "unique_script_count_distribution": dict(sorted(counts.items())),
            }
        ),
        file=sys.stderr,
    )

    return int(statuses["error"] > 0)


def extract_paths(log: Path, archive_root: Path) -> dict[Path, list[int]]:
    """Deduplicate warning paths, retaining snapshots and source line numbers."""
    paths: dict[Path, list[int]] = {}
    with log.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            match = WARNING.search(line)
            if match:
                relative = Path(match[1]).relative_to("/OLD_PERF")
                if ".." in relative.parts:
                    raise ValueError(f"Path escapes archive root at {log}:{number}")
                paths.setdefault(archive_root / relative, []).append(number)
    if not paths:
        raise ValueError(f"No ambiguous run-script warnings found in {log}")

    return dict(sorted(paths.items()))


def inspect_directory(path: Path) -> dict:
    """Count exactly the provenance names considered by SimBoard's resolver."""
    result = {"path": str(path), "status": "error"}
    try:
        directories = sorted(
            entry
            for entry in path.iterdir()
            if entry.name.lower().startswith("casedocs") and entry.is_dir()
        )
        files = [entry for directory in directories for entry in directory.iterdir()]
        case_name = _read_case_name(files)
        pattern = re.compile(
            rf"(?P<provenance>(?:run\.)?{re.escape(case_name)}"
            rf"(?:_[0-9]+)?\.sh\.\d{{8}}-\d{{6}})"
            rf"\.{re.escape(path.name)}(?:\.gz)?"
        )
        matches = {}
        for file in sorted(files):
            match = pattern.fullmatch(file.name)
            if match and file.is_file():
                matches[str(file.relative_to(path))] = match["provenance"]
        scripts = sorted(set(matches.values()))
        result.update(
            status="ambiguous" if len(scripts) > 1 else "not_ambiguous",
            case_name=case_name,
            matching_file_count=len(matches),
            unique_script_count=len(scripts),
            scripts=scripts,
            files=list(matches),
        )
    except (OSError, EOFError, ValueError, ET.ParseError, zlib.error) as exc:
        result["error"] = str(exc)

    return result


def _read_case_name(files: list[Path]) -> str:
    matches = [file for file in files if re.match(r"env_case\.xml\..*\.gz", file.name)]
    if len(matches) != 1:
        raise ValueError(f"Expected one env_case.xml..*.gz file; found {len(matches)}")
    with gzip.open(matches[0], "rb") as stream:
        root = ET.parse(stream).getroot()
    entry = root.find(".//entry[@id='CASE']")
    name = entry.get("value") if entry is not None else None
    if not name or not name.strip():
        raise ValueError(f"CASE is missing in {matches[0]}")

    return name


if __name__ == "__main__":
    raise SystemExit(main())
