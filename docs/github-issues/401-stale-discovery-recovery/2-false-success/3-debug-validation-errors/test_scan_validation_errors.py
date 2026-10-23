"""Offline tests for bulk validation diagnostics; no API or database fixtures."""

import gzip
import json
from pathlib import Path

import pytest
import scan_validation_errors as scan


@pytest.fixture
def execution(tmp_path):
    directory = tmp_path / "archive" / "2026-07" / "case" / "123.260101-000000"
    directory.mkdir(parents=True)
    docs = directory / f"CaseDocs.{directory.name}"
    docs.mkdir()
    _write(docs / "env_case.xml.test.gz", '<entry id="COMPSET" value="BHIST"/>')
    _write(docs / "env_build.xml.test.gz", '<entry id="GRID" value="ne30"/>')
    _write(
        docs / "env_run.xml.test.gz",
        '<entry id="RUN_TYPE" value="startup"/><entry id="RUN_STARTDATE" value="2000-01-01"/>',
    )
    _write(docs / "README.case.test.gz", "create_newcase --compset BHIST --res ne30")
    _write(directory / "e3sm_timing.test", f"LID: {directory.name}\n")
    _write(directory / "cpl.log.123.260101-000000", "No driver clock")

    return directory


def test_checks_all_fields_and_separates_original_errors(execution):
    docs = execution / f"CaseDocs.{execution.name}"
    _write(docs / "README.case.test.gz", "create_newcase --case example")
    _write(
        docs / "env_run.xml.test.gz",
        '<entry id="RUN_TYPE" value="startup"/><entry id="RUN_STARTDATE" value="0000-01-02"/>',
    )
    _write(execution / "GIT_CONFIG.test.gz", "url = ssh://git@example.org/repo")
    result = scan.diagnose_execution(_candidate(execution))
    invalid = {
        field["field"]: field
        for field in result["fields"]
        if field["status"] == "invalid"
    }
    assert len(result["fields"]) == 8
    assert set(invalid) == {
        "compset",
        "grid_name",
        "simulation_start_date",
        "git_repository_url",
    }
    assert invalid["compset"]["cause"] == "flag_not_found"
    assert invalid["simulation_start_date"]["cause"] == "year_zero_date"
    assert (
        invalid["git_repository_url"]["validation_input"]
        == "ssh://git@example.org/repo"
    )
    assert invalid["compset"]["errors"][0]["matches_original"]
    assert not invalid["grid_name"]["errors"][0]["matches_original"]
    summary = scan.summarize_results([result])
    assert summary["executions_with_validation_errors"] == 1
    assert summary["field_error_count"] == 4
    assert (
        sum(group["additional_errors"] for group in summary["validation_groups"]) == 3
    )


def test_valid_metadata_optional_url_and_coupler_precedence(execution):
    _write(
        execution / "cpl.log.123.260101-000000",
        "(seq_timemgr_clockPrint) Clock = drv\n(seq_timemgr_clockPrint) Curr Time = 20010102\n",
    )
    result = scan.diagnose_execution(_candidate(execution))
    fields = {field["field"]: field for field in result["fields"]}
    assert fields["simulation_start_date"]["parsed_value"] == "2001-01-02"
    assert fields["git_repository_url"]["status"] == "skipped"
    assert not result["source_issues"]
    assert scan.summarize_results([result])["field_error_count"] == 0


@pytest.mark.parametrize(
    "problem", ["missing", "ambiguous", "corrupt_gzip", "malformed_xml"]
)
def test_source_problems_are_not_scalar_failures(execution, problem):
    path = execution / f"CaseDocs.{execution.name}" / "env_case.xml.test.gz"
    if problem == "missing":
        path.unlink()
    elif problem == "ambiguous":
        _write(
            path.with_name("env_case.xml.other.gz"), '<entry id="COMPSET" value="X"/>'
        )
    elif problem == "corrupt_gzip":
        path.write_bytes(b"not gzip")
    else:
        _write(path, "<broken")
    result = scan.diagnose_execution(_candidate(execution))
    field = next(
        field for field in result["fields"] if field["field"] == "compset_alias"
    )
    assert field["status"] == "blocked"
    assert field["errors"] == []
    assert len(result["source_issues"]) == 1


def test_missing_directory_remains_distinct(tmp_path):
    result = scan.diagnose_execution(_candidate(tmp_path / "missing"))
    summary = scan.summarize_results([result])
    assert summary["executions_with_source_issues"] == 1
    assert summary["field_error_count"] == 0


def test_unreadable_coupler_keeps_xml_fallback(execution):
    (execution / "cpl.log.123.260101-000000").unlink()
    (execution / "cpl.log.123.260101-000000.gz").write_bytes(b"not gzip")
    docs = execution / f"CaseDocs.{execution.name}"
    _write(
        docs / "env_run.xml.test.gz",
        '<entry id="RUN_TYPE" value="startup"/><entry id="RUN_STARTDATE" value="0000-01-02"/>',
    )
    result = scan.diagnose_execution(_candidate(execution))
    field = next(
        field for field in result["fields"] if field["field"] == "simulation_start_date"
    )
    assert field["status"] == "invalid"
    assert field["cause"] == "year_zero_date"
    assert result["source_issues"][0]["file_spec"] == "cpl_log"


def test_coupler_date_does_not_depend_on_xml_readability(execution):
    (execution / f"CaseDocs.{execution.name}" / "env_run.xml.test.gz").write_bytes(
        b"not gzip"
    )
    _write(
        execution / "cpl.log.123.260101-000000",
        "(seq_timemgr_clockPrint) Clock = drv\n(seq_timemgr_clockPrint) Curr Time = 20010102\n",
    )
    fields = {
        field["field"]: field
        for field in scan.diagnose_execution(_candidate(execution))["fields"]
    }
    assert fields["simulation_start_date"]["status"] == "validated"
    assert fields["initialization_type"]["status"] == "blocked"


def test_missing_timing_lid_blocks_without_source_read_issue(execution):
    _write(execution / "e3sm_timing.test", "No LID")
    summary = scan.summarize_results([scan.diagnose_execution(_candidate(execution))])
    assert summary["blocked_fields"] == 1
    assert summary["executions_with_source_issues"] == 0


def test_sources_are_parsed_once(execution, monkeypatch):
    spec = {**scan.FILE_SPECS["readme_case"]}
    calls = []
    original = spec["parser"]

    def counting_parser(path):
        calls.append(path)
        return original(path)

    spec["parser"] = counting_parser
    monkeypatch.setitem(scan.FILE_SPECS, "readme_case", spec)
    scan.diagnose_execution(_candidate(execution))
    assert len(calls) == 1


def test_latest_completed_attempt_wins_before_filtering(tmp_path):
    first = _event("/source/2026-07/a", "2026-01-01T00:00:00+00:00")
    later = {
        **first,
        "timestamp": "2026-01-01T01:00:00+00:00",
        "outcome": "created",
        "response_body": {"errors": []},
    }
    other = _event("/source/2026-07/b", "2026-01-01T00:00:00+00:00")
    log = tmp_path / "replay.jsonl"
    log.write_text(
        "\n".join(json.dumps(record) for record in [later, first, other, other])
    )
    candidates = scan.read_candidates(log, Path("/source"), Path("/mounted"))
    assert len(candidates) == 1
    assert candidates[0]["local_execution_path"] == "/mounted/2026-07/b"


@pytest.mark.parametrize(
    "problem", ["truncated", "outside_root", "parent_escape", "mixed_runs"]
)
def test_rejects_invalid_input(tmp_path, problem):
    records = [_event("/source/a", "2026-01-01T00:00:00+00:00")]
    if problem == "outside_root":
        records[0]["execution_path"] = "/elsewhere/a"
    elif problem == "parent_escape":
        records[0]["execution_path"] = "/source/../elsewhere/a"
    elif problem == "mixed_runs":
        records.append({**records[0], "run_id": "other-run"})
    log = tmp_path / "replay.jsonl"
    log.write_text(
        "\n".join(json.dumps(record) for record in records)
        + ("\n{" if problem == "truncated" else "")
    )
    with pytest.raises(ValueError):
        scan.read_candidates(log, Path("/source"), Path("/mounted"))


def test_rejects_response_errors_for_another_execution(tmp_path):
    record = _event("/source/a", "2026-01-01T00:00:00+00:00")
    record["container_execution_path"] = "/OLD_PERF/a"
    record["response_body"]["errors"][0]["execution_dir"] = "/OLD_PERF/other"
    log = tmp_path / "replay.jsonl"
    log.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="another execution"):
        scan.read_candidates(log, Path("/source"), Path("/mounted"))
    record["response_body"]["errors"][0]["execution_dir"] = "/OLD_PERF/a"
    log.write_text(json.dumps(record))
    assert len(scan.read_candidates(log, Path("/source"), Path("/mounted"))) == 1


def test_unexpected_execution_error_does_not_stop_scan(
    execution, tmp_path, monkeypatch, capsys
):
    log = tmp_path / "replay.jsonl"
    first = _event(str(execution), "2026-01-01T00:00:00+00:00")
    second = _event(str(execution.parent / "missing"), "2026-01-01T00:00:00+00:00")
    log.write_text(json.dumps(first) + "\n" + json.dumps(second))
    monkeypatch.setattr(scan, "__file__", str(tmp_path / "scan_validation_errors.py"))
    original = scan.diagnose_execution

    def failing_execution(candidate):
        if candidate["execution_path"] == str(execution):
            raise IndexError("unexpected parser failure")
        return original(candidate)

    monkeypatch.setattr(scan, "diagnose_execution", failing_execution)
    assert (
        scan.main(
            [
                str(log),
                "--source-root",
                str(execution.parent),
                "--archive-root",
                str(execution.parent),
            ]
        )
        == 1
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["completed"] == 2
    assert summary["blocked_fields"] == 16
    assert any(
        group["code"] == "unexpected_error" for group in summary["source_issue_groups"]
    )


def test_cli_saves_identical_summary_and_execution_details(
    execution, tmp_path, monkeypatch, capsys
):
    log = tmp_path / "replay.jsonl"
    log.write_text(json.dumps(_event(str(execution), "2026-01-01T00:00:00+00:00")))
    monkeypatch.setattr(scan, "__file__", str(tmp_path / "scan_validation_errors.py"))
    assert (
        scan.main(
            [
                str(log),
                "--source-root",
                str(execution.parent),
                "--archive-root",
                str(execution.parent),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    saved = json.loads(next(tmp_path.glob("*-groups.json")).read_text())
    assert saved == summary
    details = [
        json.loads(line)
        for line in Path(summary["details_file"]).read_text().splitlines()
    ]
    assert len(details) == 1
    assert details[0]["execution_path"] == str(execution)
    assert len(details[0]["fields"]) == 8
    assert (
        scan.main(
            [
                str(log),
                "--source-root",
                str(execution.parent),
                "--archive-root",
                str(tmp_path / "missing"),
            ]
        )
        == 1
    )


def _candidate(execution):
    return {
        "execution_path": str(execution),
        "local_execution_path": str(execution),
        "original_errors": [
            {"error_type": "ValidationError", "field": "compset", "code": "string_type"}
        ],
    }


def _event(path, timestamp):
    return {
        "event": "request_finished",
        "run_id": "run",
        "attempt_id": "attempt",
        "execution_path": path,
        "timestamp": timestamp,
        "outcome": "failed",
        "response_body": {"errors": _candidate(path)["original_errors"]},
    }


def _write(path, text):
    if path.name.startswith("env_") and text.startswith("<entry"):
        text = f"<config>{text}</config>"
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            stream.write(text)
    else:
        path.write_text(text, encoding="utf-8")
