"""Offline tests for targeted API replay; no live requests are made."""

import csv
import http.client
import io
import json
from unittest.mock import Mock, patch

import pytest
import replay_unresolved_executions as replay

PATH = (
    "/global/cfs/cdirs/e3sm/OLD_PERF/2025-12/snapshot/COMPLETED/"
    "zender/case/46898596.251223-143828"
)
EXECUTION_ID = "46898596.251223-143828"
ROW = {
    "machine": "perlmutter",
    "execution_path": PATH,
    "expected_execution_id": EXECUTION_ID,
    "database_status": "no_exact_path_identity_match",
}


def test_csv_translation_and_deduplication(tmp_path):
    path = tmp_path / "checked.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ROW))
        writer.writeheader()
        writer.writerows([ROW, ROW, {**ROW, "database_status": "execution_exists"}])
    candidates = replay.load_candidates(path)
    assert len(candidates) == 1
    assert (
        candidates[0]["case_path"] == "/OLD_PERF/2025-12/snapshot/COMPLETED/zender/case"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"machine": "chrysalis"},
        {"execution_path": PATH.replace("/2025-12/", "/../")},
        {"execution_path": PATH.replace("/OLD_PERF/", "/other/")},
        {"expected_execution_id": "wrong"},
    ],
)
def test_reject_invalid_scope(change):
    with pytest.raises(ValueError):
        replay._candidate({**ROW, **change})


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {
                "created_count": 1,
                "duplicate_count": 0,
                "errors": [],
                "executions": [{"execution_id": EXECUTION_ID}],
            },
            "created",
        ),
        (
            {"created_count": 0, "duplicate_count": 1, "errors": [], "executions": []},
            "duplicate",
        ),
        (
            {
                "created_count": 0,
                "duplicate_count": 0,
                "errors": [
                    {
                        "execution_dir": "/OLD_PERF" + PATH.split("/OLD_PERF")[1],
                        "error": "date is None",
                    }
                ],
                "executions": [],
            },
            "failed",
        ),
        (
            {"created_count": 0, "duplicate_count": 0, "errors": [], "executions": []},
            "unconfirmed",
        ),
        (
            {
                "created_count": 2,
                "duplicate_count": 0,
                "errors": [],
                "executions": [{"execution_id": EXECUTION_ID}] * 2,
            },
            "unconfirmed",
        ),
        (None, "unconfirmed"),
    ],
)
def test_classification(body, expected):
    candidate = replay._candidate(ROW)
    outcome, _ = replay.classify_response(
        body, EXECUTION_ID, candidate["container_execution_path"]
    )
    assert outcome == expected


def test_http_201_execution_error_is_failure_and_redacts_token():
    candidate = replay._candidate(ROW)
    body = {
        "created_count": 0,
        "duplicate_count": 0,
        "executions": [],
        "errors": [
            {
                "execution_dir": candidate["container_execution_path"],
                "error": "date is None secret-token",
            }
        ],
    }
    log = io.StringIO()
    with patch.object(
        replay, "_post", return_value=(201, json.dumps(body), None)
    ) as post:
        result = replay.replay(
            [candidate],
            "http://backend:8000/api/v1/ingestions/from-path",
            "secret-token",
            log,
            1,
            0,
        )
    summary = json.loads(log.getvalue().splitlines()[-1])
    assert result == 1
    assert summary["http_succeeded"] == 1
    assert summary["failed"] == 1
    assert "secret-token" not in log.getvalue()
    assert post.call_count == 1


def test_timeout_stops_without_retries():
    log = io.StringIO()
    with patch.object(replay, "_post", return_value=(None, "", "timed out")) as post:
        assert (
            replay.replay(
                [replay._candidate(ROW)] * 2, "http://backend", "token", log, 1, 0
            )
            == 1
        )
    summary = json.loads(log.getvalue().splitlines()[-1])
    assert post.call_count == 1
    assert summary["unconfirmed"] == 1
    assert summary["not_attempted"] == 1


def test_post_selects_one_execution():
    candidate = replay._candidate(ROW)
    response = io.BytesIO(b"{}")
    response.status = 201
    with patch.object(replay.urllib.request, "build_opener") as build:
        build.return_value.open.return_value = response
        replay._post("http://backend", "token", candidate, 1)
    request = build.return_value.open.call_args.args[0]
    assert json.loads(request.data) == {
        "machine_name": "perlmutter",
        "archive_path": candidate["case_path"],
        "selected_execution_ids": [EXECUTION_ID],
    }


def test_refuses_url_credentials_and_redirects():
    with pytest.raises(ValueError):
        replay._endpoint("http://user:password@backend")
    assert (
        replay._NoRedirect().redirect_request(None, None, 302, "", {}, "http://other")
        is None
    )


def test_empty_success_continues_but_remains_unconfirmed():
    body = {"created_count": 0, "duplicate_count": 0, "executions": [], "errors": []}
    log = io.StringIO()
    with patch.object(
        replay, "_post", return_value=(201, json.dumps(body), None)
    ) as post:
        assert (
            replay.replay(
                [replay._candidate(ROW)] * 2, "http://backend", "token", log, 1, 0
            )
            == 1
        )
    summary = json.loads(log.getvalue().splitlines()[-1])
    assert post.call_count == 2
    assert summary["unconfirmed"] == 2
    assert summary["not_attempted"] == 0


@pytest.mark.parametrize("http_error", [False, True])
def test_incomplete_response_is_transport_failure(http_error):
    candidate = replay._candidate(ROW)
    with patch.object(replay.urllib.request, "build_opener") as build:
        if http_error:
            stream = io.BytesIO()
            error = replay.urllib.error.HTTPError(
                "http://backend", 500, "error", {}, stream
            )
            # A broken HTTP error body must be caught by the outer transport handler.
            error.read = Mock(side_effect=http.client.IncompleteRead(b"partial"))
            build.return_value.open.side_effect = error
        else:
            build.return_value.open.return_value.__enter__.return_value.read.side_effect = http.client.IncompleteRead(
                b"partial"
            )
        status, _, error = replay._post("http://backend", "token", candidate, 1)
    assert status is None
    assert "IncompleteRead" in error


def test_json_escaped_token_is_redacted():
    token = 'secret"\\é'
    log = io.StringIO()
    replay._emit(
        log, token, "test", body={"error": token}, raw=json.dumps({"error": token})
    )
    record = json.loads(log.getvalue())
    assert record["body"]["error"] == "[REDACTED]"
    assert json.loads(record["raw"])["error"] == "[REDACTED]"


def test_interrupt_accounts_for_unknown_request():
    log = io.StringIO()
    with patch.object(replay, "_post", side_effect=KeyboardInterrupt):
        assert (
            replay.replay(
                [replay._candidate(ROW)], "http://backend", "token", log, 1, 0
            )
            == 1
        )
    summary = json.loads(log.getvalue().splitlines()[-1])
    assert summary["unconfirmed"] == summary["http_unknown"] == 1
    assert summary["interrupted"]


@pytest.fixture
def resume_inputs(tmp_path):
    csv_path = tmp_path / "checked.csv"
    rows = [
        {
            **ROW,
            "execution_path": PATH + suffix,
            "expected_execution_id": EXECUTION_ID + suffix,
        }
        for suffix in ("", "-second", "-third")
    ]
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ROW))
        writer.writeheader()
        writer.writerows(rows)
    candidates = replay.load_candidates(csv_path)
    log_path = tmp_path / "prior.jsonl"
    # An in-flight request is valid evidence, not proof that the write failed.
    records = [
        {"event": "run_started", "selected": 3},
        {"event": "request_started", "index": 1, **candidates[0]},
    ]
    log_path.write_text("".join(json.dumps(record) + "\n" for record in records))

    return csv_path, log_path, candidates


def test_resume_preview_is_inclusive_and_limits_after_index(resume_inputs, capsys):
    csv_path, log_path, candidates = resume_inputs
    with patch.object(replay, "_post") as post:
        assert (
            replay.main(
                [
                    str(csv_path),
                    "--resume-from",
                    str(log_path),
                    "--start-index",
                    "2",
                    "--limit",
                    "1",
                ]
            )
            == 0
        )
    preview = json.loads(capsys.readouterr().out)
    assert preview["selected"] == 1
    assert preview["start_index"] == 2
    assert preview["first"] == candidates[1]
    post.assert_not_called()


def test_resume_apply_preserves_indices_and_source(
    resume_inputs, monkeypatch, tmp_path
):
    csv_path, log_path, candidates = resume_inputs
    original = log_path.read_bytes()
    output = tmp_path / "resumed.jsonl"
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "secret-token")
    body = {"created_count": 0, "duplicate_count": 1, "errors": [], "executions": []}
    with patch.object(
        replay, "_post", return_value=(201, json.dumps(body), None)
    ) as post:
        assert (
            replay.main(
                [
                    str(csv_path),
                    "--resume-from",
                    str(log_path),
                    "--start-index",
                    "2",
                    "--apply",
                    "--log",
                    str(output),
                    "--delay",
                    "0",
                ]
            )
            == 0
        )
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert [
        record["index"] for record in records if record["event"] == "request_started"
    ] == [2, 3]
    assert [call.args[2] for call in post.call_args_list] == candidates[1:]
    assert records[0]["resume_from"] == str(log_path)
    assert records[-1]["selected"] == records[-1]["attempted"] == 2
    assert log_path.read_bytes() == original


@pytest.mark.parametrize("index", ["0", "-1", "4"])
def test_resume_rejects_invalid_index(resume_inputs, index):
    csv_path, log_path, _ = resume_inputs
    with patch.object(replay, "_post") as post, pytest.raises(SystemExit):
        replay.main(
            [str(csv_path), "--resume-from", str(log_path), "--start-index", index]
        )
    post.assert_not_called()


@pytest.mark.parametrize("option", ["--resume-from", "--start-index"])
def test_resume_requires_both_options(resume_inputs, option):
    csv_path, log_path, _ = resume_inputs
    value = str(log_path) if option == "--resume-from" else "2"
    with pytest.raises(SystemExit):
        replay.main([str(csv_path), option, value])


@pytest.mark.parametrize(
    "contents",
    [
        '{"event":',
        "[]\n",
        '{"event": "run_started"}\n',
        '{"event": "request_started", "index": true}\n',
        '{"event": "request_started", "index": 99}\n',
        '{"event": "request_finished", "index": 1, "execution_path": "/wrong"}\n',
    ],
)
def test_resume_rejects_invalid_log_before_writes(
    resume_inputs, tmp_path, monkeypatch, contents
):
    csv_path, log_path, _ = resume_inputs
    log_path.write_text(contents)
    output = tmp_path / "new.jsonl"
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "secret-token")
    with patch.object(replay, "_post") as post, pytest.raises(SystemExit):
        replay.main(
            [
                str(csv_path),
                "--resume-from",
                str(log_path),
                "--start-index",
                "2",
                "--apply",
                "--log",
                str(output),
            ]
        )
    post.assert_not_called()
    assert not output.exists()


def test_resume_refuses_to_overwrite_source_log(resume_inputs, monkeypatch):
    csv_path, log_path, _ = resume_inputs
    original = log_path.read_bytes()
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "secret-token")
    with patch.object(replay, "_post") as post:
        assert (
            replay.main(
                [
                    str(csv_path),
                    "--resume-from",
                    str(log_path),
                    "--start-index",
                    "2",
                    "--apply",
                    "--log",
                    str(log_path),
                ]
            )
            == 1
        )
    post.assert_not_called()
    assert log_path.read_bytes() == original
