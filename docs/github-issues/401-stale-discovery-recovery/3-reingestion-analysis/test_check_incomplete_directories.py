"""Direct-check tests using temporary directories only."""

from pathlib import Path
from unittest.mock import patch

import check_incomplete_directories as scan
import pytest


@pytest.fixture
def execution(tmp_path):
    path = tmp_path / "123.260101-000000"
    docs = path / "CaseDocs.test"
    docs.mkdir(parents=True)
    for name in (
        "env_case.xml.test.gz",
        "env_build.xml.test.gz",
        "env_run.xml.test",
        "README.case.test.gz",
    ):
        (docs / name).write_bytes(b"not parsed")
    for name in (
        "CaseStatus.test.gz",
        "e3sm_timing.test",
        "GIT_DESCRIBE.test.gz",
        "cpl.log.123.260101-000000.gz",
    ):
        (path / name).write_bytes(b"not parsed")

    return path


def test_required_files_present(execution):
    result = scan.inspect_directory(execution)
    assert result["status"] == "files_present"
    assert result["empty"] is False and result["missing"] == []
    assert len(result["matched_files"]) == 8


def test_empty_and_empty_subdirectory_are_distinct(tmp_path):
    assert scan.inspect_directory(tmp_path)["status"] == "empty"
    (tmp_path / "casedocs").mkdir()
    result = scan.inspect_directory(tmp_path)
    assert result["empty"] is False
    assert result["status"] == "incomplete"
    assert len(result["missing"]) == 8


def test_missing_and_not_directory_are_not_empty(tmp_path):
    result = scan.inspect_directory(tmp_path / "absent")
    assert result["status"] == "missing_directory" and result["empty"] is None
    file = tmp_path / "file"
    file.touch()
    assert scan.inspect_directory(file)["status"] == "not_directory"


def test_duplicate_broken_and_zero_byte_files(execution):
    (execution / "CaseStatus.duplicate.gz").write_bytes(b"duplicate")
    (execution / "GIT_DESCRIBE.test.gz").write_bytes(b"")
    cpl = execution / "cpl.log.123.260101-000000.gz"
    cpl.unlink()
    cpl.symlink_to("absent")
    result = scan.inspect_directory(execution)
    assert result["status"] == "invalid_files"
    assert len(result["conflicts"]) == 1
    assert len(result["file_errors"]) == 2


def test_matching_directory_is_not_regular_file(execution):
    artifact = execution / "GIT_DESCRIBE.test.gz"
    artifact.unlink()
    artifact.mkdir()
    assert scan.inspect_directory(execution)["status"] == "invalid_files"


def test_permission_error_preserves_unknown_emptiness(tmp_path):
    with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
        result = scan.inspect_directory(tmp_path)
    assert result["status"] == "inspection_error"
    assert result["empty"] is result["missing"] is None


def test_casedocs_failure_does_not_claim_missing_files(execution):
    with patch.object(scan, "_metadata_entries", side_effect=PermissionError("denied")):
        result = scan.inspect_directory(execution)
    assert result["status"] == "inspection_error"
    assert result["empty"] is False and result["missing"] is None


def test_snapshot_paths_remain_separate_and_comparison_is_explicit(tmp_path):
    rows = []
    for snapshot in ("a", "b"):
        case = f"2026-01/{snapshot}/COMPLETED/alice/case"
        path = tmp_path / case / "123.260101-000000"
        path.mkdir(parents=True)
        rows.append(
            {
                "container_path": f"/OLD_PERF/{case}/{path.name}",
                "owner": "alice",
                "execution_id": path.name,
                "source_lines": [4],
                "missing_file_specs": sorted(spec for _, spec, _ in scan.REQUIRED),
            }
        )
    results = scan.inspect_executions(rows, tmp_path)
    assert len({row["path"] for row in results}) == 2
    assert all(row["empty"] and row["missing_matches_log"] for row in results)
    report = scan.render_report(results, "run-test", "2026-01-01T00:00:00+00:00")
    assert "Inspected 2 distinct execution paths" in report
    assert "2 match the log; 0 differ; 0 could not be checked" in report


def test_report_guard_protects_source_and_archive(tmp_path):
    log = tmp_path / "log"
    archive = tmp_path / "archive"
    with pytest.raises(ValueError):
        scan._validate_output(log, log, archive)
    with pytest.raises(ValueError):
        scan._validate_output(archive / "report.md", log, archive)
