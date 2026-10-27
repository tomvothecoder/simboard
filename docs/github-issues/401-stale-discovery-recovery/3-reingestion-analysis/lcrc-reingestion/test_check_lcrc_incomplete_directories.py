"""Offline Chrysalis fixtures; never inspect production paths or call APIs."""

import json
from pathlib import Path
from unittest.mock import patch

import check_lcrc_incomplete_directories as scan
import pytest

ROOT = Path("/lcrc/group/e3sm/PERF_Chrysalis/OLD_PERF")
EXECUTION = "123.260101-000000"
CASE = "2026-01/performance_archive_chrysalis_e3sm_2026_01_01_00_00_00/ac.alice/case"


@pytest.mark.parametrize("status_bucket", [False, True])
def test_chrysalis_layouts_and_dynamic_counts(tmp_path, status_bucket):
    case = CASE.replace("/ac.alice/", "/COMPLETED/ac.alice/") if status_bucket else CASE
    log = _log(tmp_path, [case, case.replace("01_01_00_00_00", "01_02_00_00_00")])
    evidence = scan.parse_log(log)
    assert len(evidence["executions"]) == 2
    assert evidence["archive_root"] == ROOT
    assert all(row["owner"] == "ac.alice" for row in evidence["executions"])
    assert len({row["relative_path"] for row in evidence["executions"]}) == 2


def test_absolute_logged_case_path(tmp_path):
    log = _log(tmp_path, [str(ROOT / CASE)])
    assert (
        scan.parse_log(log)["executions"][0]["relative_path"] == f"{CASE}/{EXECUTION}"
    )


def test_info_log_stops_before_filesystem_scan(tmp_path):
    log = _log(tmp_path, [CASE], debug=False)
    with patch.object(scan, "inspect_directory") as inspect:
        with pytest.raises(SystemExit) as exc:
            scan.main(["--log", str(log)])
    assert exc.value.code == 2
    inspect.assert_not_called()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('"incomplete": 1', '"incomplete": 9', "totals"),
        ('"machine": "chrysalis"', '"machine": "perlmutter"', "Chrysalis"),
        (
            '"discovery_complete": true',
            '"discovery_complete": false',
            "completed archive",
        ),
        ("incomplete=1", "incomplete=2", "totals"),
        ("case=" + CASE, "case=../" + CASE, "escapes"),
    ],
)
def test_bad_evidence_is_rejected(tmp_path, old, new, message):
    log = _log(tmp_path, [CASE])
    log.write_text(log.read_text().replace(old, new))
    with pytest.raises(ValueError, match=message):
        scan.parse_log(log)


def test_failed_live_submission_does_not_invalidate_complete_discovery(tmp_path):
    log = _log(tmp_path, [CASE], dry_run=False, status="failure")
    assert scan.parse_log(log)["metrics"]["status"] == "failure"


def test_main_remaps_root_writes_report_and_keeps_compact_diagnostics(tmp_path, capsys):
    log = _log(tmp_path, [CASE])
    root = tmp_path / "archive"
    (root / CASE / EXECUTION).mkdir(parents=True)
    report = tmp_path / "report.md"
    result = scan.main(
        [
            "--log",
            str(log),
            "--archive-root",
            str(root),
            "--report",
            str(report),
            "--details",
        ]
    )
    assert result == 1
    row = json.loads(capsys.readouterr().out)
    assert row["path"] == str(root / CASE / EXECUTION)
    assert row["status"] == "empty" and row["missing_matches_log"]
    assert row["logged_errors"] == []
    assert row["logged_error_count"] == 8
    assert row["logged_error_codes"] == ["missing_required_file"]
    assert "Inspected 1 distinct Chrysalis execution paths" in report.read_text()


def test_optional_expanded_errors_remain_exact(tmp_path):
    log = _log(tmp_path, [CASE], expanded=True)
    row = scan.parse_log(log)["executions"][0]
    assert len(row["logged_errors"]) == 8
    assert row["logged_errors"][0]["message"] == 'Missing "metadata"; exact text.'


def test_symlinked_root_accepts_resolved_case_paths(tmp_path):
    real = tmp_path / "real_archive"
    real.mkdir()
    alias = tmp_path / "alias_archive"
    alias.symlink_to(real, target_is_directory=True)
    log = _log(tmp_path, [CASE], root=alias, expanded=True)
    text = log.read_text().replace(f"case={CASE}", f"case={real / CASE}")
    text = text.replace(str(alias / CASE), str(real / CASE))
    log.write_text(text)
    assert (
        scan.parse_log(log)["executions"][0]["relative_path"] == f"{CASE}/{EXECUTION}"
    )


def test_empty_missing_and_unreadable_are_distinct(tmp_path):
    assert scan.inspect_directory(tmp_path)["status"] == "empty"
    missing = scan.inspect_directory(tmp_path / "absent")
    assert missing["status"] == "missing_directory" and missing["empty"] is None
    with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
        result = scan.inspect_directory(tmp_path)
    assert result["status"] == "inspection_error" and result["missing"] is None


def test_empty_subdirectory_is_not_empty_execution(tmp_path):
    (tmp_path / "CaseDocs.test").mkdir()
    result = scan.inspect_directory(tmp_path)
    assert result["empty"] is False and result["status"] == "incomplete"


def test_readable_required_files_and_invalid_artifacts(tmp_path):
    docs = tmp_path / "CaseDocs.test"
    docs.mkdir()
    for name in (
        "env_case.xml.x.gz",
        "env_build.xml.x.gz",
        "env_run.xml.x",
        "README.case.x.gz",
    ):
        (docs / name).write_bytes(b"not parsed")
    for name in (
        "CaseStatus.x.gz",
        "e3sm_timing.x",
        "GIT_DESCRIBE.x.gz",
        f"cpl.log.{EXECUTION}.gz",
    ):
        (tmp_path / name).write_bytes(b"not parsed")
    assert scan.inspect_directory(tmp_path)["status"] == "files_present"
    (tmp_path / "CaseStatus.y.gz").write_bytes(b"duplicate")
    (tmp_path / "GIT_DESCRIBE.x.gz").write_bytes(b"")
    artifact = tmp_path / f"cpl.log.{EXECUTION}.gz"
    artifact.unlink()
    artifact.symlink_to("absent")
    result = scan.inspect_directory(tmp_path)
    assert result["status"] == "invalid_files"
    assert len(result["conflicts"]) == 1 and len(result["file_errors"]) == 2


def test_output_guard_protects_log_and_archive(tmp_path):
    log = tmp_path / "log"
    root = tmp_path / "archive"
    for report in (log, root / "report.md"):
        with pytest.raises(ValueError):
            scan._validate_paths(root, report, log)


def _log(
    tmp_path,
    cases,
    debug=True,
    dry_run=True,
    status="success",
    root=ROOT,
    expanded=False,
):
    lines = [
        "INFO CONFIG event=invocation_started Run ID: run-test",
        f"INFO CONFIG Archive root: {root}",
    ]
    for case in cases:
        relative = (
            Path(case).relative_to(root) if Path(case).is_absolute() else Path(case)
        )
        errors = [
            {
                "execution_dir": str(root / relative / EXECUTION),
                "code": "missing_required_file",
                "file_spec": label,
                "message": 'Missing "metadata"; exact text.',
            }
            for _, label, _ in scan.REQUIRED
        ]
        if debug:
            line = (
                f"DEBUG event=execution_decision case={case} execution_id={EXECUTION} "
                "outcome=incomplete reason=incomplete "
                'error_count=8 error_codes=["missing_required_file"] '
                f"missing_file_specs={json.dumps(sorted(label for _, label, _ in scan.REQUIRED))} "
            )
            if expanded:
                line += f"errors={json.dumps(errors)}"
            lines.append(line)
        lines.append(
            f"INFO event=case_discovered case={case} EXECUTIONS selected=0 incomplete=1"
        )
    metrics = {
        "run_id": "run-test",
        "machine": "chrysalis",
        "scan_mode": "archive",
        "discovery_complete": True,
        "dry_run": dry_run,
        "status": status,
        "executions": {"incomplete": len(cases)},
    }
    lines.append("INFO event=run_metrics payload=" + json.dumps(metrics))
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n")

    return log
