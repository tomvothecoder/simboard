"""Offline tests for provenance counting; no production filesystem access."""

import gzip
import json
from pathlib import Path
from unittest.mock import patch

import inspect_run_scripts as scan
import pytest


@pytest.fixture
def execution(tmp_path):
    path = tmp_path / "directory-name" / "123.260101-000000"
    docs = path / "CaseDocs.test"
    docs.mkdir(parents=True)
    with gzip.open(docs / "env_case.xml.test.gz", "wt") as stream:
        stream.write('<config><entry id="CASE" value="actual.case"/></config>')

    return path, docs


def test_counts_metadata_case_name_and_excludes_wrappers(execution):
    path, docs = execution
    for name in (
        f"actual.case.sh.20260101-000000.{path.name}.gz",
        f"run.actual.case_42.sh.20260101-010000.{path.name}",
        f"directory-name.sh.20260101-000000.{path.name}.gz",
        "case.run",
        "actual.case.sh.20260101-000000.other-id.gz",
    ):
        (docs / name).touch()
    result = scan.inspect_directory(path)
    assert result["status"] == "ambiguous"
    assert result["matching_file_count"] == result["unique_script_count"] == 2


def test_gzip_plain_and_duplicate_copies_are_one_script(execution):
    path, docs = execution
    name = f"actual.case.sh.20260101-000000.{path.name}"
    (docs / name).touch()
    (docs / f"{name}.gz").touch()
    other = path / "casedocs.other"
    other.mkdir()
    (other / name).touch()
    result = scan.inspect_directory(path)
    assert result["status"] == "not_ambiguous"
    assert result["matching_file_count"] == 3
    assert result["unique_script_count"] == 1


def test_ignores_matching_directory(execution):
    path, docs = execution
    (docs / f"actual.case.sh.20260101-000000.{path.name}").mkdir()
    assert scan.inspect_directory(path)["unique_script_count"] == 0


def test_missing_and_unreadable_execution(tmp_path):
    assert scan.inspect_directory(tmp_path / "missing")["status"] == "error"
    with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
        assert "denied" in scan.inspect_directory(tmp_path)["error"]


@pytest.mark.parametrize(
    "contents",
    [b"not gzip", gzip.compress(b"not xml"), bytes.fromhex("1f8b080000000000020307")],
)
def test_corrupt_metadata_is_reported(execution, contents):
    path, docs = execution
    (docs / "env_case.xml.test.gz").write_bytes(contents)
    assert scan.inspect_directory(path)["status"] == "error"


def test_missing_case_name(execution):
    path, docs = execution
    (docs / "env_case.xml.test.gz").write_bytes(gzip.compress(b"<config/>"))
    assert "CASE is missing" in scan.inspect_directory(path)["error"]


def test_extracts_unique_snapshot_paths_and_occurrences(tmp_path):
    log = tmp_path / "run.log"
    message = (
        "Skipping run-script artifact for '{}': multiple E3SM provenance scripts.\n"
    )
    log.write_text(
        message.format("/OLD_PERF/snapshot-a/case/123") * 2
        + message.format("/OLD_PERF/snapshot-b/case/123")
    )
    assert scan.extract_paths(log, tmp_path) == {
        tmp_path / "snapshot-a/case/123": [1, 2],
        tmp_path / "snapshot-b/case/123": [3],
    }


def test_cli_reports_counts(execution, tmp_path, capsys):
    path, _ = execution
    log = tmp_path / "run.log"
    log.write_text(
        f"Skipping run-script artifact for '/OLD_PERF/directory-name/{path.name}': "
        "multiple E3SM provenance scripts.\n"
    )
    assert scan.main(["--log", str(log), "--archive-root", str(tmp_path)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["unique_script_count"] == 0
    assert json.loads(output.err)["paths"] == 1
