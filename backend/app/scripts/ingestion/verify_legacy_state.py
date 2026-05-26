"""Compare or backfill legacy file-backed ingestion state against DB state.

Usage:
    uv run python -m app.scripts.ingestion.verify_legacy_state \
        --machine-name perlmutter \
        --state-path /path/to/state.json

    uv run python -m app.scripts.ingestion.verify_legacy_state \
        --machine-name perlmutter \
        --state-path /path/to/state.json \
        --backfill
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import app.models  # noqa: F401 # required to register models with SQLAlchemy
from app.core.database import SessionLocal
from app.features.ingestion.enums import IngestionSourceType
from app.features.ingestion.models import Ingestion
from app.features.machine.utils import resolve_machine_by_name
from app.features.simulation.models import Simulation


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare legacy ingestion state.json against DB state."
    )
    parser.add_argument("--machine-name", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Persist legacy-only execution IDs into processed_execution_ids on "
            "matching ingestion rows before re-checking DB state."
        ),
    )
    args = parser.parse_args()

    state_path = Path(args.state_path).resolve()

    try:
        legacy_cases = _load_legacy_cases(state_path)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    backfill_summary: dict[str, Any] | None = None

    with SessionLocal() as db:
        machine = resolve_machine_by_name(db, args.machine_name)
        if machine is None:
            print(f"Machine '{args.machine_name}' not found.", file=sys.stderr)
            return 1

        if args.backfill:
            backfill_summary = _backfill_processed_execution_ids(
                db,
                machine.id,
                legacy_cases,
            )

        db_cases = _build_db_cases(db, machine.id)

    summary = _summarize_state_diff(legacy_cases, db_cases)
    if backfill_summary is not None:
        summary["backfill"] = backfill_summary
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["matches"] else 2


def _load_legacy_cases(state_path: Path) -> dict[str, list[str]]:
    if not state_path.exists():
        raise FileNotFoundError(f"Legacy state file not found: {state_path}")

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Legacy state file is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Legacy state payload must be a JSON object.")

    return _normalize_legacy_cases(payload.get("cases", {}))


def _normalize_legacy_cases(raw_cases: Any) -> dict[str, list[str]]:
    if not isinstance(raw_cases, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for case_path, case_state in raw_cases.items():
        if not isinstance(case_path, str) or not isinstance(case_state, dict):
            continue

        raw_execution_ids = case_state.get("processed_execution_ids")
        if raw_execution_ids is None:
            raw_execution_ids = case_state.get("execution_ids")

        if not isinstance(raw_execution_ids, list):
            normalized[case_path] = []
            continue

        normalized[case_path] = sorted(
            {value for value in raw_execution_ids if isinstance(value, str)}
        )

    return normalized


def _build_db_cases(db, machine_id) -> dict[str, list[str]]:
    execution_ids_by_case: dict[str, set[str]] = {}
    ingestion_rows = (
        db.query(
            Ingestion.id, Ingestion.source_reference, Ingestion.processed_execution_ids
        )
        .filter(
            Ingestion.source_type == IngestionSourceType.HPC_PATH,
            Ingestion.machine_id == machine_id,
        )
        .all()
    )
    fallback_ingestion_ids: list[UUID] = []

    for ingestion_id, case_path, processed_execution_ids in ingestion_rows:
        if not case_path:
            continue

        normalized_execution_ids = _normalize_processed_execution_ids(
            processed_execution_ids
        )
        if normalized_execution_ids is None:
            fallback_ingestion_ids.append(ingestion_id)
            continue

        execution_ids_by_case.setdefault(case_path, set()).update(
            normalized_execution_ids
        )

    if fallback_ingestion_ids:
        simulation_rows = (
            db.query(Ingestion.source_reference, Simulation.execution_id)
            .join(Simulation, Simulation.ingestion_id == Ingestion.id)
            .filter(Ingestion.id.in_(fallback_ingestion_ids))
            .all()
        )

        for case_path, execution_id in simulation_rows:
            if not case_path or not execution_id:
                continue
            execution_ids_by_case.setdefault(case_path, set()).add(execution_id)

    return {
        case_path: sorted(execution_ids)
        for case_path, execution_ids in sorted(execution_ids_by_case.items())
    }


def _backfill_processed_execution_ids(
    db,
    machine_id: UUID,
    legacy_cases: dict[str, list[str]],
) -> dict[str, Any]:
    current_db_cases = _build_db_cases(db, machine_id)
    ingestions = (
        db.query(Ingestion)
        .filter(
            Ingestion.source_type == IngestionSourceType.HPC_PATH,
            Ingestion.machine_id == machine_id,
            Ingestion.source_reference.in_(legacy_cases),
        )
        .order_by(Ingestion.source_reference.asc(), Ingestion.created_at.desc())
        .all()
    )

    ingestions_by_case: dict[str, list[Ingestion]] = {}
    for ingestion in ingestions:
        ingestions_by_case.setdefault(ingestion.source_reference, []).append(ingestion)

    updated_cases: list[str] = []
    unresolved_cases: list[str] = []

    for case_path, legacy_execution_ids in sorted(legacy_cases.items()):
        missing_execution_ids = sorted(
            set(legacy_execution_ids) - set(current_db_cases.get(case_path, []))
        )
        if not missing_execution_ids:
            continue

        target_ingestion = _select_backfill_target_ingestion(
            ingestions_by_case.get(case_path, [])
        )
        if target_ingestion is None:
            unresolved_cases.append(case_path)
            continue

        persisted_execution_ids = _normalize_processed_execution_ids(
            target_ingestion.processed_execution_ids
        )
        target_ingestion.processed_execution_ids = sorted(
            set(persisted_execution_ids or []) | set(missing_execution_ids)
        )
        current_db_cases[case_path] = sorted(
            set(current_db_cases.get(case_path, [])) | set(missing_execution_ids)
        )
        updated_cases.append(case_path)

    if updated_cases:
        db.commit()

    return {
        "requested": True,
        "updated_case_count": len(updated_cases),
        "updated_cases": updated_cases,
        "unresolved_case_count": len(unresolved_cases),
        "unresolved_cases": unresolved_cases,
    }


def _select_backfill_target_ingestion(ingestions: list[Ingestion]) -> Ingestion | None:
    if not ingestions:
        return None

    ingestions_missing_persisted_ids = [
        ingestion
        for ingestion in ingestions
        if _normalize_processed_execution_ids(ingestion.processed_execution_ids) is None
    ]
    if ingestions_missing_persisted_ids:
        return ingestions_missing_persisted_ids[0]

    return ingestions[0]


def _normalize_processed_execution_ids(raw_execution_ids: Any) -> list[str] | None:
    if raw_execution_ids is None:
        return None
    if not isinstance(raw_execution_ids, list):
        return None

    return sorted({value for value in raw_execution_ids if isinstance(value, str)})


def _summarize_state_diff(
    legacy_cases: dict[str, list[str]],
    db_cases: dict[str, list[str]],
) -> dict[str, Any]:
    legacy_paths = set(legacy_cases)
    db_paths = set(db_cases)

    file_only_cases = sorted(legacy_paths - db_paths)
    db_only_cases = sorted(db_paths - legacy_paths)
    mismatched_cases: dict[str, dict[str, list[str]]] = {}

    for case_path in sorted(legacy_paths & db_paths):
        legacy_ids = set(legacy_cases[case_path])
        db_ids = set(db_cases[case_path])
        if legacy_ids == db_ids:
            continue

        mismatched_cases[case_path] = {
            "legacy_only_execution_ids": sorted(legacy_ids - db_ids),
            "db_only_execution_ids": sorted(db_ids - legacy_ids),
        }

    return {
        "matches": not file_only_cases and not db_only_cases and not mismatched_cases,
        "legacy_case_count": len(legacy_cases),
        "db_case_count": len(db_cases),
        "file_only_cases": file_only_cases,
        "db_only_cases": db_only_cases,
        "mismatched_cases": mismatched_cases,
    }


if __name__ == "__main__":
    raise SystemExit(main())
