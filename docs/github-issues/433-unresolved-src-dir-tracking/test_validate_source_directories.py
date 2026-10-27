"""Offline filesystem tests; no production archive, API, or database access."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import validate_source_directories as scan


@pytest.fixture
def execution(tmp_path):
    directory = tmp_path / "123.260101-000000"
    directory.mkdir()
    docs = directory / "CaseDocs.test"
    docs.mkdir()
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
        (directory / name).write_bytes(b"not parsed")

    return directory


def test_all_required_files_present(execution):
    result = scan.validate_directory(execution)
    assert result["status"] == "files_present"
    assert result["empty"] is False
    assert result["missing"] == result["errors"] == []
    assert result["conflicts"] == {}


def test_empty_missing_and_not_directory_are_distinct(tmp_path):
    assert scan.validate_directory(tmp_path)["empty"] is True
    missing = scan.validate_directory(tmp_path / "absent")
    assert missing["status"] == "missing" and missing["empty"] is None
    file = tmp_path / "file"
    file.touch()
    assert scan.validate_directory(file)["status"] == "not_directory"


def test_empty_casedocs_is_not_an_empty_execution(tmp_path):
    (tmp_path / "casedocs").mkdir()
    result = scan.validate_directory(tmp_path)
    assert result["status"] == "incomplete"
    assert result["empty"] is False
    assert len(result["missing"]) == 8


def test_missing_conflicting_zero_byte_and_broken_files(execution):
    (execution / "CaseDocs.test/env_case.xml.test.gz").unlink()
    (execution / "CaseStatus.other.gz").write_bytes(b"duplicate")
    (execution / "GIT_DESCRIBE.test.gz").write_bytes(b"")
    (execution / "cpl.log.123.260101-000000.gz").unlink()
    (execution / "cpl.log.123.260101-000000.gz").symlink_to("absent")
    result = scan.validate_directory(execution)
    assert result["status"] == "invalid_files"
    assert len(result["missing"]) == 1
    assert len(result["conflicts"]) == 1
    assert len(result["errors"]) == 2


def test_matching_directory_is_not_a_file(execution):
    artifact = execution / "GIT_DESCRIBE.test.gz"
    artifact.unlink()
    artifact.mkdir()
    result = scan.validate_directory(execution)
    assert result["status"] == "invalid_files"
    assert "Not a regular file" in result["errors"][0]


def test_permission_error_is_not_empty(tmp_path):
    with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
        result = scan.validate_directory(tmp_path)
    assert result["status"] == "unreadable"
    assert result["empty"] is None
    assert "denied" in result["error"]


def test_extraction_deduplicates_without_merging_snapshots(tmp_path):
    log = tmp_path / "run.log"
    log.write_text(
        "INFO event=source_directory_unresolved error=missing execution_path=/OLD_PERF/a/case/123\n"
        "INFO event=source_directory_unresolved error=missing execution_path=/OLD_PERF/a/case/123\n"
        "INFO event=source_directory_unresolved error=missing execution_path=/OLD_PERF/b/case/123\n"
    )
    assert scan.extract_paths(log, tmp_path) == {
        tmp_path / "a/case/123": [1, 2],
        tmp_path / "b/case/123": [3],
    }


@pytest.mark.parametrize("path", ["/other/case/123", "/OLD_PERF/../escape"])
def test_rejects_unsafe_or_unrecognized_paths(tmp_path, path):
    log = tmp_path / "run.log"
    log.write_text(f"event=source_directory_unresolved execution_path={path}\n")
    with pytest.raises(ValueError):
        scan.extract_paths(log, tmp_path)


def test_rejects_log_without_paths(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("INFO unrelated event\n")
    with pytest.raises(ValueError, match="No unresolved"):
        scan.extract_paths(log, tmp_path)


def test_cli_continues_after_missing_directory(execution, tmp_path, capsys):
    log = tmp_path / "run.log"
    log.write_text(
        f"event=source_directory_unresolved execution_path=/OLD_PERF/{execution.name}\n"
        "event=source_directory_unresolved execution_path=/OLD_PERF/absent\n"
    )
    assert scan.main(["--log", str(log), "--archive-root", str(tmp_path)]) == 1
    output = capsys.readouterr()
    rows = [json.loads(line) for line in output.out.splitlines()]
    assert {row["status"] for row in rows} == {"files_present", "missing"}
    assert json.loads(output.err)["paths"] == 2
