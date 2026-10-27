"""Offline tests for exact DEBUG evidence extraction and reconciliation."""

import json

import parse_incomplete_executions as scan
import pytest

CASE = "2026-01/performance_archive_test/COMPLETED/alice/case"
EXECUTION = "123.260101-000000"


def test_extracts_errors_and_preserves_snapshot_paths(tmp_path):
    other = CASE.replace("performance_archive_test", "performance_archive_other")
    log = _log(tmp_path, [(CASE, EXECUTION), (other, EXECUTION)])
    evidence = scan.parse_log(log, expected=2)
    rows = evidence["executions"]
    assert len(rows) == 2
    assert rows[0]["host_path"].startswith("/global/cfs/cdirs/e3sm/OLD_PERF/")
    assert rows[0]["container_path"] != rows[1]["container_path"]
    assert (
        rows[0]["errors"][0]["message"]
        == "Missing \"metadata\"; keep exact apostrophe: 'x'"
    )
    assert evidence["cases_without_selected_executions"] == 2
    report = scan.render_report(evidence, log)
    assert "Recovered all 2 incomplete execution paths" in report
    assert "do not prove directories are empty" in report


def test_duplicate_events_keep_occurrences_without_inflating_paths(tmp_path):
    log = _log(tmp_path, [(CASE, EXECUTION)], repeat=True)
    rows = scan.parse_log(log, expected=1)["executions"]
    assert len(rows) == 1
    assert len(rows[0]["source_lines"]) == 2


def test_rejects_mismatched_expected_total(tmp_path):
    log = _log(tmp_path, [(CASE, EXECUTION)])
    with pytest.raises(ValueError, match="count mismatch"):
        scan.parse_log(log, expected=1883)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('"incomplete": 1', '"incomplete": 2', "count mismatch"),
        ("incomplete=1", "incomplete=2", "per-case totals"),
        ("error_count=1", "error_count=2", "Error count"),
        ("errors=[", "errors=broken[", "Malformed event fields"),
        ("disabled (offline)", "enabled", "remote state disabled"),
        (
            '"discovery_complete": true',
            '"discovery_complete": false',
            "complete dry-run",
        ),
        ('"run_id": "run-test"', '"run_id": "other"', "mismatched"),
    ],
)
def test_rejects_inconsistent_or_missing_evidence(tmp_path, old, new, message):
    log = _log(tmp_path, [(CASE, EXECUTION)])
    log.write_text(log.read_text().replace(old, new))
    with pytest.raises(ValueError, match=message):
        scan.parse_log(log, expected=1)


def test_rejects_path_traversal(tmp_path):
    log = _log(tmp_path, [("../" + CASE, EXECUTION)])
    with pytest.raises(ValueError, match="Unsafe execution path"):
        scan.parse_log(log, expected=1)


def test_main_writes_report_and_details(tmp_path, capsys):
    log = _log(tmp_path, [(CASE, EXECUTION)])
    report = tmp_path / "report.md"
    assert (
        scan.main(
            ["--log", str(log), "--expected", "1", "--report", str(report), "--details"]
        )
        == 0
    )
    row = json.loads(capsys.readouterr().out)
    assert row["execution_id"] == EXECUTION
    assert row["errors"][0]["file_spec"] == "env_case.xml..*.gz"
    assert report.read_text().startswith("# Incomplete execution discovery")


def test_report_cannot_overwrite_source(tmp_path):
    log = _log(tmp_path, [(CASE, EXECUTION)])
    original = log.read_bytes()
    with pytest.raises(SystemExit) as exc:
        scan.main(["--log", str(log), "--expected", "1", "--report", str(log)])
    assert exc.value.code == 2
    assert log.read_bytes() == original


def _log(tmp_path, executions, repeat=False):
    lines = [
        "INFO event=invocation_started Run ID: run-test",
        "INFO CONFIG Remote state: disabled (offline)",
    ]
    for case, execution in executions:
        error = {
            "code": "missing_required_file",
            "file_spec": "env_case.xml..*.gz",
            "execution_dir": f"/OLD_PERF/{case}/{execution}",
            "message": "Missing \"metadata\"; keep exact apostrophe: 'x'",
        }
        decision = (
            f"DEBUG event=execution_decision case={case} execution_id={execution} "
            f"outcome=incomplete reason=incomplete error_count=1 errors={json.dumps([error])}"
        )
        lines.extend([decision] * (2 if repeat else 1))
        lines.append(
            f"INFO event=case_discovered case={case} EXECUTIONS total=1 "
            "selected=0 incomplete=1"
        )
    metrics = {
        "run_id": "run-test",
        "dry_run": True,
        "discovery_complete": True,
        "status": "success",
        "executions": {"incomplete": len(executions)},
    }
    lines.append("INFO event=run_metrics payload=" + json.dumps(metrics))
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n")

    return log
