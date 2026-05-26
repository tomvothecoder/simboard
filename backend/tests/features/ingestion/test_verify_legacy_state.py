import json
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine
from app.features.simulation.enums import SimulationStatus, SimulationType
from app.features.simulation.models import Case, Simulation
from app.scripts.ingestion import verify_legacy_state as verify_legacy_state_module
from app.scripts.ingestion.verify_legacy_state import (
    _backfill_processed_execution_ids,
    _build_db_cases,
    _load_legacy_cases,
    _normalize_legacy_cases,
    _normalize_processed_execution_ids,
    _select_backfill_target_ingestion,
    _summarize_state_diff,
    main,
)


def _create_machine(db, name: str) -> Machine:
    machine = db.query(Machine).filter(Machine.name == name).one_or_none()
    if machine is not None:
        return machine

    machine = Machine(
        name=name,
        site="Test Site",
        architecture="x86_64",
        scheduler="slurm",
        gpu=False,
    )
    db.add(machine)
    db.flush()
    return machine


def _create_hpc_path_state(
    db,
    *,
    user_id,
    machine: Machine,
    case_name: str,
    source_reference: str,
    execution_id: str,
    processed_execution_ids: list[str] | None = None,
) -> None:
    case = Case(name=case_name)
    db.add(case)
    db.flush()

    ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference=source_reference,
        machine_id=machine.id,
        triggered_by=user_id,
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
        processed_execution_ids=processed_execution_ids or [execution_id],
    )
    db.add(ingestion)
    db.flush()

    db.add(
        Simulation(
            case_id=case.id,
            execution_id=execution_id,
            compset="FHIST",
            compset_alias="fhist",
            grid_name="grid",
            grid_resolution="1x1",
            simulation_type=SimulationType.PRODUCTION,
            status=SimulationStatus.COMPLETED,
            initialization_type="branch",
            machine_id=machine.id,
            simulation_start_date=datetime.now(timezone.utc),
            created_by=user_id,
            last_updated_by=user_id,
            ingestion_id=ingestion.id,
        )
    )


def test_normalize_legacy_cases_accepts_both_execution_id_keys() -> None:
    normalized = _normalize_legacy_cases(
        {
            "/archive/a": {"execution_ids": ["101.1-1", "100.1-1"]},
            "/archive/b": {"processed_execution_ids": ["200.1-1", "200.1-1"]},
            "/archive/c": {"processed_execution_ids": "bad"},
        }
    )

    assert normalized["/archive/a"] == ["100.1-1", "101.1-1"]
    assert normalized["/archive/b"] == ["200.1-1"]
    assert normalized["/archive/c"] == []


def test_load_legacy_cases_reads_json(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"cases": {"/archive/a": {"processed_execution_ids": ["100.1-1"]}}}',
        encoding="utf-8",
    )

    assert _load_legacy_cases(state_path) == {"/archive/a": ["100.1-1"]}


def test_load_legacy_cases_raises_for_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="Legacy state file not found:"):
        _load_legacy_cases(tmp_path / "missing.json")


def test_load_legacy_cases_rejects_invalid_json_and_non_object_payload(
    tmp_path,
) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="Legacy state file is not valid JSON:"):
        _load_legacy_cases(invalid_path)

    list_path = tmp_path / "list.json"
    list_path.write_text('["bad"]', encoding="utf-8")

    with pytest.raises(ValueError, match="Legacy state payload must be a JSON object."):
        _load_legacy_cases(list_path)


def test_normalize_legacy_cases_returns_empty_for_non_dict_and_skips_invalid_entries() -> (
    None
):
    assert _normalize_legacy_cases(["bad"]) == {}

    normalized = _normalize_legacy_cases(
        {
            "/archive/valid": {"processed_execution_ids": ["100.1-1"]},
            "/archive/bad-state": "bad",
            123: {"processed_execution_ids": ["skip"]},
        }
    )

    assert normalized == {"/archive/valid": ["100.1-1"]}


def test_build_db_cases_aggregates_by_case_path(db, normal_user_sync) -> None:
    machine = _create_machine(db, "perlmutter")
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_1",
        source_reference="/archive/case_a",
        execution_id="101.1-1",
    )
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_2",
        source_reference="/archive/case_a",
        execution_id="100.1-1",
    )
    db.commit()

    assert _build_db_cases(db, machine.id) == {
        "/archive/case_a": ["100.1-1", "101.1-1"]
    }


def test_build_db_cases_prefers_persisted_processed_execution_ids(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_partial",
        source_reference="/archive/case_partial",
        execution_id="100.1-1",
        processed_execution_ids=["100.1-1", "101.1-1"],
    )
    ingestion = (
        db.query(Ingestion)
        .filter(Ingestion.source_reference == "/archive/case_partial")
        .first()
    )
    assert ingestion is not None
    ingestion.status = IngestionStatus.PARTIAL
    ingestion.error_count = 1

    duplicate_only_ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference="/archive/case_duplicate_only",
        machine_id=machine.id,
        triggered_by=normal_user_sync["id"],
        status=IngestionStatus.FAILED,
        created_count=0,
        duplicate_count=1,
        error_count=0,
        processed_execution_ids=["200.1-1"],
    )
    db.add(duplicate_only_ingestion)
    db.commit()

    assert _build_db_cases(db, machine.id) == {
        "/archive/case_duplicate_only": ["200.1-1"],
        "/archive/case_partial": ["100.1-1", "101.1-1"],
    }


def test_build_db_cases_falls_back_to_simulation_ids_for_legacy_rows(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")
    case = Case(name="verify_case_legacy")
    db.add(case)
    db.flush()

    ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference="/archive/case_legacy",
        machine_id=machine.id,
        triggered_by=normal_user_sync["id"],
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
        processed_execution_ids=None,
    )
    db.add(ingestion)
    db.flush()
    db.add(
        Simulation(
            case_id=case.id,
            execution_id="legacy-100.1-1",
            compset="FHIST",
            compset_alias="fhist",
            grid_name="grid",
            grid_resolution="1x1",
            simulation_type=SimulationType.PRODUCTION,
            status=SimulationStatus.COMPLETED,
            initialization_type="branch",
            machine_id=machine.id,
            simulation_start_date=datetime.now(timezone.utc),
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            ingestion_id=ingestion.id,
        )
    )
    db.commit()

    assert _build_db_cases(db, machine.id) == {
        "/archive/case_legacy": ["legacy-100.1-1"]
    }


def test_build_db_cases_skips_blank_case_paths_and_blank_execution_ids(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")

    db.add(
        Ingestion(
            source_type=IngestionSourceType.HPC_PATH,
            source_reference="",
            machine_id=machine.id,
            triggered_by=normal_user_sync["id"],
            status=IngestionStatus.SUCCESS,
            created_count=0,
            duplicate_count=1,
            error_count=0,
            processed_execution_ids=["100.1-1"],
        )
    )

    case = Case(name="verify_case_blank_exec")
    db.add(case)
    db.flush()

    ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference="/archive/blank_exec",
        machine_id=machine.id,
        triggered_by=normal_user_sync["id"],
        status=IngestionStatus.SUCCESS,
        created_count=1,
        duplicate_count=0,
        error_count=0,
        processed_execution_ids=None,
    )
    db.add(ingestion)
    db.flush()
    db.add(
        Simulation(
            case_id=case.id,
            execution_id="",
            compset="FHIST",
            compset_alias="fhist",
            grid_name="grid",
            grid_resolution="1x1",
            simulation_type=SimulationType.PRODUCTION,
            status=SimulationStatus.COMPLETED,
            initialization_type="branch",
            machine_id=machine.id,
            simulation_start_date=datetime.now(timezone.utc),
            created_by=normal_user_sync["id"],
            last_updated_by=normal_user_sync["id"],
            ingestion_id=ingestion.id,
        )
    )
    db.commit()

    assert _build_db_cases(db, machine.id) == {}


def test_backfill_processed_execution_ids_recovers_legacy_duplicate_only_case(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")
    duplicate_only_ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference="/archive/case_duplicate_only",
        machine_id=machine.id,
        triggered_by=normal_user_sync["id"],
        status=IngestionStatus.FAILED,
        created_count=0,
        duplicate_count=1,
        error_count=0,
        processed_execution_ids=None,
    )
    db.add(duplicate_only_ingestion)
    db.commit()

    summary = _backfill_processed_execution_ids(
        db,
        machine.id,
        {"/archive/case_duplicate_only": ["200.1-1"]},
    )

    db.refresh(duplicate_only_ingestion)

    assert summary["updated_cases"] == ["/archive/case_duplicate_only"]
    assert summary["unresolved_cases"] == []
    assert duplicate_only_ingestion.processed_execution_ids == ["200.1-1"]
    assert _build_db_cases(db, machine.id) == {
        "/archive/case_duplicate_only": ["200.1-1"]
    }


def test_backfill_processed_execution_ids_reports_file_only_case_without_ingestion_row(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_present",
        source_reference="/archive/case_present",
        execution_id="100.1-1",
    )
    db.commit()

    summary = _backfill_processed_execution_ids(
        db,
        machine.id,
        {"/archive/case_missing": ["200.1-1"]},
    )

    assert summary["updated_cases"] == []
    assert summary["unresolved_cases"] == ["/archive/case_missing"]


def test_backfill_processed_execution_ids_skips_cases_that_already_match(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_match",
        source_reference="/archive/case_match",
        execution_id="100.1-1",
    )
    db.commit()

    summary = _backfill_processed_execution_ids(
        db,
        machine.id,
        {"/archive/case_match": ["100.1-1"]},
    )

    assert summary["updated_cases"] == []
    assert summary["unresolved_cases"] == []


def test_select_backfill_target_ingestion_prefers_row_missing_persisted_state(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_existing",
        source_reference="/archive/case_target",
        execution_id="100.1-1",
        processed_execution_ids=["100.1-1"],
    )
    missing_state_ingestion = Ingestion(
        source_type=IngestionSourceType.HPC_PATH,
        source_reference="/archive/case_target",
        machine_id=machine.id,
        triggered_by=normal_user_sync["id"],
        status=IngestionStatus.FAILED,
        created_count=0,
        duplicate_count=1,
        error_count=0,
        processed_execution_ids=None,
    )
    db.add(missing_state_ingestion)
    db.commit()

    ingestions = (
        db.query(Ingestion)
        .filter(
            Ingestion.source_type == IngestionSourceType.HPC_PATH,
            Ingestion.machine_id == machine.id,
            Ingestion.source_reference == "/archive/case_target",
        )
        .order_by(Ingestion.created_at.desc())
        .all()
    )

    assert _select_backfill_target_ingestion(ingestions) == missing_state_ingestion


def test_select_backfill_target_ingestion_returns_first_when_all_have_persisted_ids(
    db, normal_user_sync
) -> None:
    machine = _create_machine(db, "perlmutter")
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_target_old",
        source_reference="/archive/case_target_default",
        execution_id="100.1-1",
        processed_execution_ids=["100.1-1"],
    )
    _create_hpc_path_state(
        db,
        user_id=normal_user_sync["id"],
        machine=machine,
        case_name="verify_case_target_new",
        source_reference="/archive/case_target_default",
        execution_id="101.1-1",
        processed_execution_ids=["101.1-1"],
    )
    db.commit()

    ingestions = (
        db.query(Ingestion)
        .filter(
            Ingestion.source_type == IngestionSourceType.HPC_PATH,
            Ingestion.machine_id == machine.id,
            Ingestion.source_reference == "/archive/case_target_default",
        )
        .order_by(Ingestion.created_at.desc())
        .all()
    )

    assert _select_backfill_target_ingestion(ingestions) == ingestions[0]


def test_normalize_processed_execution_ids_returns_none_for_non_list() -> None:
    assert _normalize_processed_execution_ids("bad") is None


def test_summarize_state_diff_reports_file_only_db_only_and_mismatch() -> None:
    summary = _summarize_state_diff(
        legacy_cases={
            "/archive/file_only": ["100.1-1"],
            "/archive/mismatch": ["200.1-1"],
        },
        db_cases={
            "/archive/db_only": ["300.1-1"],
            "/archive/mismatch": ["201.1-1"],
        },
    )

    assert summary["matches"] is False
    assert summary["file_only_cases"] == ["/archive/file_only"]
    assert summary["db_only_cases"] == ["/archive/db_only"]
    assert summary["mismatched_cases"]["/archive/mismatch"] == {
        "legacy_only_execution_ids": ["200.1-1"],
        "db_only_execution_ids": ["201.1-1"],
    }


def test_summarize_state_diff_reports_match_when_states_are_equal() -> None:
    summary = _summarize_state_diff(
        legacy_cases={"/archive/match": ["100.1-1"]},
        db_cases={"/archive/match": ["100.1-1"]},
    )

    assert summary == {
        "matches": True,
        "legacy_case_count": 1,
        "db_case_count": 1,
        "file_only_cases": [],
        "db_only_cases": [],
        "mismatched_cases": {},
    }


class _FakeSessionLocal:
    def __init__(self, db) -> None:
        self._db = db

    def __call__(self):
        return self

    def __enter__(self):
        return self._db

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_main_returns_success_for_matching_state(monkeypatch, tmp_path, capsys) -> None:
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_legacy_state",
            "--machine-name",
            "pm",
            "--state-path",
            str(state_path),
        ],
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "_load_legacy_cases",
        lambda path: {"/archive/a": ["100.1-1"]},
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "resolve_machine_by_name",
        lambda db, name: SimpleNamespace(id="machine-1"),
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "SessionLocal",
        _FakeSessionLocal(object()),
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "_build_db_cases",
        lambda db, machine_id: {"/archive/a": ["100.1-1"]},
    )

    assert main() == 0
    assert json.loads(capsys.readouterr().out) == {
        "db_case_count": 1,
        "db_only_cases": [],
        "file_only_cases": [],
        "legacy_case_count": 1,
        "matches": True,
        "mismatched_cases": {},
    }


def test_main_returns_failure_when_machine_is_missing(
    monkeypatch, tmp_path, capsys
) -> None:
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_legacy_state",
            "--machine-name",
            "pm",
            "--state-path",
            str(state_path),
        ],
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "_load_legacy_cases",
        lambda path: {},
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "resolve_machine_by_name",
        lambda db, name: None,
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "SessionLocal",
        _FakeSessionLocal(object()),
    )

    assert main() == 1
    assert capsys.readouterr().err.strip() == "Machine 'pm' not found."


def test_main_backfill_includes_summary_and_returns_mismatch(
    monkeypatch, tmp_path, capsys
) -> None:
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_legacy_state",
            "--machine-name",
            "pm",
            "--state-path",
            str(state_path),
            "--backfill",
        ],
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "_load_legacy_cases",
        lambda path: {"/archive/a": ["100.1-1"]},
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "resolve_machine_by_name",
        lambda db, name: SimpleNamespace(id="machine-1"),
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "SessionLocal",
        _FakeSessionLocal(object()),
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "_backfill_processed_execution_ids",
        lambda db, machine_id, legacy_cases: {
            "requested": True,
            "updated_case_count": 0,
            "updated_cases": [],
            "unresolved_case_count": 1,
            "unresolved_cases": ["/archive/a"],
        },
    )
    monkeypatch.setattr(
        verify_legacy_state_module,
        "_build_db_cases",
        lambda db, machine_id: {},
    )

    assert main() == 2
    assert json.loads(capsys.readouterr().out) == {
        "backfill": {
            "requested": True,
            "unresolved_case_count": 1,
            "unresolved_cases": ["/archive/a"],
            "updated_case_count": 0,
            "updated_cases": [],
        },
        "db_case_count": 0,
        "db_only_cases": [],
        "file_only_cases": ["/archive/a"],
        "legacy_case_count": 1,
        "matches": False,
        "mismatched_cases": {},
    }


def test_main_returns_failure_when_state_load_fails(
    tmp_path, capsys, monkeypatch
) -> None:
    missing_path = tmp_path / "missing.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_legacy_state",
            "--machine-name",
            "pm",
            "--state-path",
            str(missing_path),
        ],
    )

    assert main() == 1
    assert "Legacy state file not found:" in capsys.readouterr().err


def test_module_main_guard_exits_via_system_exit_on_missing_state_file(
    monkeypatch, tmp_path
) -> None:
    script_path = (
        Path(__file__).resolve().parents[3]
        / "app/scripts/ingestion/verify_legacy_state.py"
    )
    missing_path = tmp_path / "missing.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script_path),
            "--machine-name",
            "pm",
            "--state-path",
            str(missing_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(script_path), run_name="__main__")

    assert exc_info.value.code == 1
