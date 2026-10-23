"""Inspect failed snapshots locally, without API or database access.

Default: preview original-log selection. --output-dir creates a NEW directory
containing inventory.csv, summary.json, and self-contained reconciliation SQL.
Requires the repository Python environment and backend on PYTHONPATH.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from replay_http_errors import (
    HOST_ARCHIVE_ROOT,
    add_inventory_arguments,
    load_failed_cases,
    local_case_path,
)

from app.common.utils import _normalize_hpc_username
from app.features.ingestion.parsers.parser import (
    _locate_metadata_files,
    _parse_all_files,
)
from app.features.machine.utils import parse_machine_name
from app.scripts.ingestion.archive_discovery import (
    EXECUTION_DIR_PATTERN,
    _validate_execution_dir,
)

FIELDS = (
    "original_http_statuses",
    "original_final_outcome",
    "archive_case_path",
    "local_case_path",
    "directory_execution_id",
    "execution_path",
    "source_execution_path",
    "fresh_discovery_qualified",
    "inventory_status",
    "reason",
    "identity_status",
    "machine",
    "hpc_username",
    "case_name",
    "execution_id",
    "identity_matches_path",
    "simulation_start_date",
    "simulation_end_date",
    "run_start_date",
    "run_end_date",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_inventory_arguments(parser)
    parser.add_argument("--archive-root", type=Path, default=HOST_ARCHIVE_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Create this new directory and scan; otherwise preview",
    )
    args = parser.parse_args(argv)
    try:
        cases = load_failed_cases(args.input_log, args.status, args.limit)
        if args.output_dir is None:
            print(
                json.dumps(
                    {
                        "mode": "preview",
                        "selected_case_paths": len(cases),
                        "first_local_path": str(
                            local_case_path(cases[0]["case_path"], args.archive_root)
                        ),
                        "api_requests": 0,
                        "archive_directories_scanned": 0,
                    },
                    indent=2,
                )
            )
            return 0
        if not args.archive_root.is_dir():
            parser.error(
                f"Archive root is not a readable directory: {args.archive_root}"
            )
        args.output_dir.mkdir()  # Refuse existing output; preserve earlier baselines.
        return inventory(cases, args.archive_root, args.output_dir, args.input_log)
    except (OSError, ValueError) as exc:
        print(
            f"Inventory stopped: {exc}. Any output directory may be incomplete.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print(
            "Inventory interrupted; output is incomplete. Do not use it as a complete baseline.",
            file=sys.stderr,
        )
        return 1


def inventory(
    cases: list[dict[str, Any]],
    archive_root: Path,
    output_dir: Path,
    input_log: Path,
) -> int:
    """Write observations incrementally; generate SQL only after every selected case is scanned."""
    rows: list[dict[str, Any]] = []
    started = datetime.now(timezone.utc).isoformat()
    with (output_dir / "inventory.csv").open(
        "x", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for index, case in enumerate(cases, 1):
            observed = scan_case(case, archive_root)
            writer.writerows(observed)
            stream.flush()
            rows.extend(observed)
            print(
                json.dumps(
                    {
                        "event": "case_scanned",
                        "index": index,
                        "case_path": case["case_path"],
                        "observations": len(observed),
                    }
                ),
                flush=True,
            )
    status_counts = Counter(row["inventory_status"] for row in rows)
    incomplete = any(
        status_counts[key]
        for key in (
            "case_unreadable",
            "unreadable",
            "parse_error",
            "identity_unresolved",
            "no_execution_directories",
        )
    )
    summary = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "input_log": str(input_log.resolve()),
        "archive_root": str(archive_root.resolve()),
        "selected_case_paths": len(cases),
        "observations": len(rows),
        "fresh_discovery_qualified": sum(
            row["fresh_discovery_qualified"] is True for row in rows
        ),
        "qualified_with_resolved_identity": sum(
            row["fresh_discovery_qualified"] is True
            and row["identity_status"] == "resolved"
            for row in rows
        ),
        "status_counts": dict(status_counts),
        "requires_investigation": incomplete,
        "api_requests": 0,
        "database_connections": 0,
    }
    with (output_dir / "query.sql").open("x", encoding="utf-8") as stream:
        stream.write(build_sql(rows, summary))
    with (output_dir / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"event": "inventory_summary", **summary}), flush=True)

    return 1 if incomplete else 0


def scan_case(case: dict[str, Any], archive_root: Path) -> list[dict[str, Any]]:
    """Inspect only immediate execution directories of one exact failed snapshot."""
    local = local_case_path(case["case_path"], archive_root)
    base = dict.fromkeys(FIELDS)
    base.update(
        {
            "original_http_statuses": ",".join(
                map(str, case["original_http_statuses"])
            ),
            "original_final_outcome": case["original_final_outcome"],
            "archive_case_path": case["case_path"],
            "local_case_path": str(local),
            "fresh_discovery_qualified": False,
            "identity_status": "not_checked",
        }
    )
    try:
        children = sorted(child for child in local.iterdir() if child.is_dir())
    except OSError as exc:
        return [{**base, "inventory_status": "case_unreadable", "reason": str(exc)}]
    rows = []
    for child in children:
        if not EXECUTION_DIR_PATTERN.fullmatch(child.name):
            continue
        row = {
            **base,
            "directory_execution_id": child.name,
            "execution_path": str(child),
            "source_execution_path": str(
                local_case_path(case["case_path"], HOST_ARCHIVE_ROOT) / child.name
            ),
        }
        rows.append(_inspect_execution(row, case, child))
    if not rows:
        rows.append(
            {
                **base,
                "inventory_status": "no_execution_directories",
                "reason": "No immediate execution directories match the runner's naming pattern",
            }
        )

    return rows


def build_sql(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    """Embed the local inventory in two read-only DBeaver SELECT statements."""
    delimiter = "$inventory_" + uuid4().hex + "$"
    payload = json.dumps(rows, ensure_ascii=True)
    assert delimiter not in payload
    common = (
        """WITH inventory AS (
    SELECT * FROM jsonb_to_recordset("""
        + delimiter
        + payload
        + delimiter
        + """::jsonb) AS i(
        original_http_statuses text, original_final_outcome text,
        archive_case_path text, local_case_path text, directory_execution_id text,
        execution_path text, source_execution_path text,
        fresh_discovery_qualified boolean, inventory_status text, reason text,
        identity_status text, machine text, hpc_username text, case_name text,
        execution_id text, identity_matches_path boolean,
        simulation_start_date text, simulation_end_date text, run_start_date text, run_end_date text
    )
), checked AS (
    SELECT i.*, c.id AS case_id, e.id AS execution_record_id,
        CASE
            WHEN i.inventory_status <> 'qualified' THEN i.inventory_status
            WHEN i.identity_status <> 'resolved' THEN 'identity_unresolved'
            WHEN m.id IS NULL THEN 'missing_machine'
            WHEN c.id IS NULL THEN 'missing_case'
            WHEN e.id IS NULL THEN 'missing_execution'
            ELSE 'execution_exists'
        END AS database_status,
        CASE WHEN e.id IS NULL THEN NULL ELSE EXISTS (
            SELECT 1 FROM source_directories sd
            WHERE sd.execution_id = e.id AND sd.kind = 'archive'
        ) END AS has_any_archive_mapping,
        CASE WHEN e.id IS NULL THEN NULL ELSE EXISTS (
            SELECT 1 FROM source_directories sd
            WHERE sd.execution_id = e.id AND sd.kind = 'archive'
              AND sd.path = i.source_execution_path
        ) END AS has_exact_archive_mapping
    FROM inventory i
    LEFT JOIN machines m ON m.name = i.machine
    LEFT JOIN cases c ON c.machine_id = m.id
        AND c.hpc_username = i.hpc_username AND c.name = i.case_name
    LEFT JOIN executions e ON e.case_id = c.id AND e.execution_id = i.execution_id
)
"""
    )
    header = (
        "-- Exact failed-snapshot inventory; self-contained, read-only PostgreSQL for DBeaver.\n"
        f"-- Selected case paths: {summary['selected_case_paths']}; observations: {len(rows)}.\n"
        "-- Fresh local discovery qualification, not cached accepted discovery results.\n"
        "-- fresh_discovery_qualified means required metadata location checks passed, not successful parsing/storage.\n"
        "-- Qualified metadata may still fail ingestion validation (for example a missing date).\n"
        "-- Unreadable/rejected/unresolved rows are not proof of missing catalog records.\n"
        "-- Counts are per observed snapshot path; one execution can occur in multiple snapshots.\n"
        "-- Two result tables: aggregate statuses, then individual observations.\n"
        "-- Run without concurrent ingestion when comparing the two results.\n\n"
    )
    aggregate = """SELECT database_status, COUNT(*) AS observations,
    COUNT(DISTINCT archive_case_path) AS affected_case_paths,
    COUNT(*) FILTER (WHERE fresh_discovery_qualified) AS fresh_discovery_qualified,
    COUNT(*) FILTER (WHERE identity_status = 'resolved') AS resolved_identities,
    COUNT(*) FILTER (WHERE execution_record_id IS NOT NULL AND NOT has_exact_archive_mapping)
        AS existing_observations_without_exact_mapping
FROM checked GROUP BY database_status ORDER BY database_status;
"""
    detail = """SELECT * FROM checked
ORDER BY database_status, archive_case_path, directory_execution_id;
"""

    return (
        header
        + "-- 1. AGGREGATED RESULTS\n"
        + common
        + aggregate
        + "\n-- 2. DETAILS\n"
        + common
        + detail
    )


def _inspect_execution(
    row: dict[str, Any], case: dict[str, Any], child: Path
) -> dict[str, Any]:
    decision = _validate_execution_dir(
        child.parent, child.name, _locate_metadata_files, None
    )
    if decision is not None:
        status = (
            "unreadable"
            if decision.reason == "transient"
            else "rejected_" + decision.reason
        )
        return {
            **row,
            "inventory_status": status,
            "reason": decision.detail or decision.reason,
        }
    row.update(fresh_discovery_qualified=True)
    try:
        parsed = _parse_all_files(str(child), _locate_metadata_files(str(child)))
        machine, _ = parse_machine_name(parsed.machine or "")
        username = _normalize_hpc_username(parsed.hpc_username)
        row.update(
            {
                "machine": machine,
                "hpc_username": username,
                "case_name": parsed.case_name,
                "execution_id": parsed.execution_id,
                "simulation_start_date": parsed.simulation_start_date,
                "simulation_end_date": parsed.simulation_end_date,
                "run_start_date": parsed.run_start_date,
                "run_end_date": parsed.run_end_date,
            }
        )
    except Exception as exc:
        # Keep parser failures visible; never substitute a guessed metadata identity.
        return {
            **row,
            "inventory_status": "parse_error",
            "identity_status": "parse_error",
            "reason": f"{type(exc).__name__}: {exc}",
        }
    if not all(
        row[key] for key in ("machine", "hpc_username", "case_name", "execution_id")
    ):
        return {
            **row,
            "inventory_status": "identity_unresolved",
            "identity_status": "missing_fields",
            "reason": "Parsed machine/user/case/execution identity has missing fields",
        }
    row.update(
        {
            "inventory_status": "qualified",
            "identity_status": "resolved",
            "identity_matches_path": (
                machine == "perlmutter"
                and username == case["path_username"]
                and parsed.case_name == case["path_case_name"]
                and parsed.execution_id == child.name
            ),
        }
    )

    return row


if __name__ == "__main__":
    raise SystemExit(main())
