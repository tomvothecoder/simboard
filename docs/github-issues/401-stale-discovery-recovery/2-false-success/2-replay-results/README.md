# False success: follow-up to HTTP-error checks

## Why this follows investigation 1 HTTP Errors

[1. HTTP errors](../1-http-errors/README.md) found **no missing qualified executions
or exact mappings in the 905 failed-request snapshots**.

- All 1,311 qualified executions exist.
- Two single-case replays returned HTTP 201: three duplicates, zero creations, zero execution errors.
- Historical HTTP failure causes remain open.

## What this investigation covers

**This investigation covers a different gap: requests reported successful while
execution records are missing.** It includes cases outside the HTTP-error inventory.

The suspected chain:

1. The API returns HTTP 201 with execution errors in the response body.
2. The runner marks the execution processed; later scans skip it.
3. Source linking cannot find its catalog record.

## Baseline results

Source: [`perlmutter-full-archive-reingestion.log`](../perlmutter-full-archive-reingestion.log).
Query: [`query.sql`](query.sql). Export: [`query_results.csv`](query_results.csv).

| Baseline finding                         |     Paths |
| ---------------------------------------- | --------: |
| No exact machine/user/case match         |     2,776 |
| Case exists; expected execution does not |        19 |
| **Total unmatched paths**                | **2,795** |

All have accepted discovery outcomes and case submissions reported successful.
The export found no exact catalog matches. These are baseline results, not a live check.

**Directory names may differ from parsed metadata.** An unmatched path alone does
not prove the execution is absent under every identity or explain why ingestion failed.

## 1. Single-execution failure debug

### Confirmed single-execution failure

Case: `zender/v3.LR.I.era5_1980s_hex_cld_srt_frn_spn`.
Execution: `46898596.251223-143828`.

| Check               | Result                                                           |
| ------------------- | ---------------------------------------------------------------- |
| Direct API replay   | HTTP 201; zero created, zero duplicates, one execution error.    |
| Error               | Date validation rejected `None`: `Input should be a valid date`. |
| Normal runner retry | Skipped as `already_processed`; source linking still failed.     |

The missing date field and its upstream cause are not yet identified. Do not assume the other 2,794 paths share this error.

### a. Prerequisites

- [x] In DBeaver, run `query.sql` and filter the result to user `zender` and execution `46898596.251223-143828`.
- [x] Export **only that row**, with headers, as `replay-zender.csv` in this directory. Preserve the baseline CSV.

### b. Replay from Perlmutter

Run from the repository root. The script calls the API; it does not upload archive
files. The API container reads `/OLD_PERF` itself.

Set the external **dev API** URL and token securely.

```bash
qa='docs/github-issues/401-stale-discovery-recovery/2-false-success'
export SIMBOARD_API_BASE_URL='https://simboard-dev-api.e3sm.org/api/v1'
read -r -s -p 'Dev SimBoard API token: ' SIMBOARD_API_TOKEN
printf '\n'
export SIMBOARD_API_TOKEN
```

Preview the one-row input. Confirm the dev endpoint and selected execution:

```bash
uv run --project backend python "$qa/2-replay-results/replay_unresolved_executions.py" "$qa/replay-zender.csv" --limit 1
```

**Apply writes catalog data and ingestion history.** Confirm the deployed API supports

Send one request and retain its full response:

```bash
uv run --project backend python "$qa/2-replay-results/replay_unresolved_executions.py" "$qa/replay-zender.csv" --limit 1 --apply --log "$qa/replay-zender.jsonl"
```

### c. Match API logs by **execution path and UTC window**

**API Log**:

```python
2026-10-22 23:01:21,318 [INFO]: parser.py(main_parser:201) >> Found 2 case directories across 1 base directories.
2026-10-22T23:01:21.319174202Z 2026-10-22 23:01:21,318 [INFO]: parser.py(main_parser:223) >> Processing case directory: v3.LR.I.era5_1980s_hex_cld_srt_frn_spn with 2 execution subdirectories.
2026-10-22 23:01:21,405 [INFO]: parser.py(main_parser:248) >> Completed parsing all execution directories.
2026-10-22 23:01:21,418 [WARNING]: ingest.py(_parse_date_field:881) >> Could not parse date '0000-01-02': year 0 is out of range: 0000-01-02
2026-10-22T23:01:21.419191527Z 2026-10-22 23:01:21,419 [ERROR]: ingest.py(ingest_archive:178) >> Failed to process execution from /OLD_PERF/2025-12/performance_archive_2025_12_24_07_00_54/COMPLETED/zender/v3.LR.I.era5_1980s_hex_cld_srt_frn_spn/46898596.251223-143828: 1 validation error for date
2026-10-22T23:01:21.419220544Z   Input should be a valid date [type=date_type, input_value=None, input_type=NoneType]
    For further information visit https://errors.pydantic.dev/2.12/v/date_type
INFO:     10.42.6.62:54144 - "POST /api/v1/ingestions/from-path HTTP/1.1" 201 Created
2026-10-22 23:02:30,777 [INFO]: parser.py(main_parser:201) >> Found 2 case directories across 1 base directories.
2026-10-22T23:02:30.778372299Z 2026-10-22 23:02:30,778 [INFO]: parser.py(main_parser:223) >> Processing case directory: v3.LR.I.era5_1980s_hex_cld_srt_frn_spn with 2 execution subdirectories.
2026-10-22 23:02:30,851 [INFO]: parser.py(main_parser:248) >> Completed parsing all execution directories.
2026-10-22 23:02:30,865 [WARNING]: ingest.py(_parse_date_field:881) >> Could not parse date '0000-01-02': year 0 is out of range: 0000-01-02
2026-10-22 23:02:30,866 [ERROR]: ingest.py(ingest_archive:178) >> Failed to process execution from /OLD_PERF/2025-12/performance_archive_2025_12_24_07_00_54/COMPLETED/zender/v3.LR.I.era5_1980s_hex_cld_srt_frn_spn/46898596.251223-143828: 1 validation error for date
2026-10-22T23:02:30.866247435Z   Input should be a valid date [type=date_type, input_value=None, input_type=NoneType]
2026-10-22T23:02:30.866255872Z     For further information visit https://errors.pydantic.dev/2.12/v/date_type
INFO:     10.42.6.62:40896 - "POST /api/v1/ingestions/from-path HTTP/1.1" 201 Created
```

### d. Root cause: failed parsing of date field

The field and source value were confirmed by parsing the archived metadata locally.
**This is an unsupported year-zero model date, not absent source metadata.** Do not silently replace year `0000` with `0001`.

Tracked here:

- Year-zero handling is tracked in [#418](https://github.com/E3SM-Project/simboard/issues/418).
- Processed-state/false-success reporting remains part of [#417](https://github.com/E3SM-Project/simboard/issues/417).

Evidence:

| Finding        | Evidence                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------- |
| Field          | `simulation_start_date`                                                                                       |
| Archived value | `0000-01-02`                                                                                                  |
| Metadata file  | `CaseDocs.46898596.251223-143828/env_run.xml.46898596.251223-143828.gz`, under the execution directory above. |
| Conversion     | `_parse_date_field()` rejects year 0 and returns `None`.                                                      |
| Validation     | The required start-date field rejects `None`; the execution is not created.                                   |
| API response   | HTTP 201, but zero creations and one execution error.                                                         |

## 3. Full diagnosis error classification

**Scope:** all remaining unmatched execution paths, including failures inside HTTP
201 responses. The original 905 HTTP-409/500 request paths are a separate inventory
in [1. HTTP errors](../1-http-errors/README.md).

### Prequisites

- [x] 1. In DBeaver, add this filter after `FROM checked`, before `ORDER BY` in `query.sql`.

  Replace any single-execution or sample filter:

  ```sql
  WHERE database_status IN (
      'no_exact_path_case_match', 'no_exact_path_identity_match'
  )
  AND NOT (
      hpc_username = 'zender'
      AND expected_execution_id = '46898596.251223-143828'
  )
  ```

- [x] 2. Export all matching rows with headers as `replay-remaining.csv`. Preserve the baseline.
     Only the confirmed #418 execution is excluded; other year-zero cases may remain.

- [x] 3. Field-aware diagnostics are tracked in [#419](https://github.com/E3SM-Project/simboard/issues/419).
     Deploy that change before replay if field-level counts are required. Older responses
     can still be grouped by error signature, but the field will be `unknown`.

### Preview all remaining executions

Run from the repository root with the dev API URL and token configured above.
No `--limit` means the full CSV, not a sample:

```bash
qa='docs/github-issues/401-stale-discovery-recovery/2-false-success'
uv run --project backend python "$qa/2-replay-results/replay_unresolved_executions.py" "$qa/1-stale-discovery/replay-remaining.csv"
```

### Run the full diagnostic pass

**Apply writes catalog data and ingestion history.** Avoid concurrent ingestion.
Requests run sequentially, without automatic retries:

```bash
runlog="$qa/replay-full-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
uv run --project backend python "$qa/2-replay-results/replay_unresolved_executions.py" "$qa/1-stale-discovery/replay-remaining.csv" --apply --log "$runlog"
```

A failure exit code can mean every request ran but executions failed. Check
`run_summary`: complete coverage requires `attempted = selected` and `not_attempted = 0`.
Also inspect `interrupted` and `unconfirmed`; attempted requests can have unknown outcomes.
After a timeout or interrupted run, check database state before retrying uncertain requests.

### Resume at a specific index

Keep the original CSV in the same order. The JSONL records only attempted requests;
the CSV supplies executions that the interrupted run never reached. Use
`--resume-from` with `--start-index`, an **inclusive, 1-based candidate index**, not
a JSONL line number. Indices refer to unmatched paths after CSV deduplication.
The script validates logged request identities against the CSV before any requests.

For example, resume at index 101 after confirming the state of request 100:

```bash
uv run --project backend python "$qa/2-replay-results/replay_unresolved_executions.py" "$qa/1-stale-discovery/replay-remaining.csv" --resume-from "$runlog" --start-index 101
resumed_log="$qa/replay-resumed-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
uv run --project backend python "$qa/2-replay-results/replay_unresolved_executions.py" "$qa/1-stale-discovery/replay-remaining.csv" --resume-from "$runlog" --start-index 101 --apply --log "$resumed_log"
```

Preview sends no requests. Apply requires a new output log and never changes the
source log. New request events retain original CSV indices; `--limit` limits only
the resumed selection. The chosen index explicitly controls replay: the script
does not automatically skip successful requests or retry unknown outcomes.
All candidates before the chosen index are excluded, even if the prior run never attempted them.
Inspect in-flight or unconfirmed requests before choosing whether to replay them.
Malformed or truncated JSONL is rejected; preserve the original evidence before
repairing a copy for use as resume input.

### Group results and counts

[`summarize_replay.py`](summarize_replay.py) reads one saved JSONL log; it sends no
requests. It prints HTTP/outcome counts, error groups, and an example path with its
UTC request window per group. Set `runlog` to the completed replay log:

```bash
uv run --project backend python "$qa/summarize_replay.py" "$runlog"
```

To also save the report in a new file:

```bash
uv run --project backend python "$qa/summarize_replay.py" "$runlog" --output "${runlog%.jsonl}-groups.json"
```

Existing output files are rejected. If `run_summary` is `null`, the log does not
contain a final summary; its counts cover only requests with `request_finished` events.

HTTP/outcome totals count completed requests. Error groups count returned errors,
or one unresolved request when no execution error is available. Do not add counts
from earlier replay logs without deduplicating execution paths.

```python
(.venv) vo13@login22:~/tomvothecoder/simboard$ uv run --project backend python "$qa/summarize_replay.py" "/global/homes/v/vo13/tomvothecoder/simboard/docs/github-issues/401-stale-discovery-recovery/2-false-success/replay-final.jsonl"
{
  "run_summary": {
    "timestamp": "2026-10-23T04:55:50.392376+00:00",
    "run_id": "ae019c30-855e-441b-bd2c-c812a9f378c5",
    "derived": true,
    "event": "run_summary",
    "status": "failure",
    "selected": 2794,
    "attempted": 2794,
    "not_attempted": 0,
    "interrupted": false,
    "http_succeeded": 2794,
    "http_failed": 0,
    "http_unknown": 0,
    "created": 0,
    "duplicate": 0,
    "failed": 2794,
    "unconfirmed": 0
  },
  "http_status_counts": {
    "201": 2794
  },
  "outcome_counts": {
    "failed": 2794
  },
  "error_groups": [
    {
      "http_status": "201",
      "outcome": "failed",
      "error_type": "ValidationError",
      "field": "compset",
      "code": "string_type",
      "signature": "1 validation error for str",
      "count": 2740,
      "example": {
        "path": "/global/cfs/cdirs/e3sm/OLD_PERF/2025-07/performance_archive_2025_07_30_08_03_25/COMPLETED/ajonko/BHIST_10xGFED_BC/41134444.250729-031144",
        "started_utc": "2026-10-22T23:52:52.348470+00:00",
        "finished_utc": "2026-10-22T23:52:52.997076+00:00"
      }
    },
    {
      "http_status": "201",
      "outcome": "failed",
      "error_type": "ValidationError",
      "field": "git_repository_url",
      "code": "url_scheme",
      "signature": "1 validation error for function-wrap[wrap_val()]",
      "count": 36,
      "example": {
        "path": "/global/cfs/cdirs/e3sm/OLD_PERF/2025-09/performance_archive_2025_09_20_08_05_12/COMPLETED/gr7610/FAQP-v3.0-ZMv1.AVG_TIME-dt_1800-ne30_ne30/42924507.250919-092412",
        "started_utc": "2026-10-23T00:14:31.937265+00:00",
        "finished_utc": "2026-10-23T00:14:33.691085+00:00"
      }
    },
    {
      "http_status": "201",
      "outcome": "failed",
      "error_type": "ValidationError",
      "field": "grid_name",
      "code": "string_type",
      "signature": "1 validation error for str",
      "count": 13,
      "example": {
        "path": "/global/cfs/cdirs/e3sm/OLD_PERF/2026-07/performance_archive_2026_07_15_07_26_41/COMPLETED/anolan/omega-oQU240/55916377.260714-145127",
        "started_utc": "2026-10-22T23:53:00.627439+00:00",
        "finished_utc": "2026-10-22T23:53:02.487082+00:00"
      }
    },
    {
      "http_status": "201",
      "outcome": "failed",
      "error_type": "ValidationError",
      "field": "simulation_start_date",
      "code": "date_type",
      "signature": "1 validation error for date",
      "count": 5,
      "example": {
        "path": "/global/cfs/cdirs/e3sm/OLD_PERF/2026-07/performance_archive_2026_07_15_07_26_41/COMPLETED/sprice/20260624.ERA5r025_r05_IcoswISC30E3r5.pm-cpu.20TR/54984820.260624-163227",
        "started_utc": "2026-10-23T00:41:16.098086+00:00",
        "finished_utc": "2026-10-23T00:41:16.443628+00:00"
      }
    }
  ]
}
```

#### Deduplicated error counts

The final log contains 2,794 unique execution paths after removing one overlapping
attempt at index 1822. All requests returned HTTP 201 but reported execution
failures; none created executions or reported duplicates.

| Error type        | Field                   | Error code    |     Count |
| ----------------- | ----------------------- | ------------- | --------: |
| `ValidationError` | `compset`               | `string_type` |     2,740 |
| `ValidationError` | `git_repository_url`    | `url_scheme`  |        36 |
| `ValidationError` | `grid_name`             | `string_type` |        13 |
| `ValidationError` | `simulation_start_date` | `date_type`   |         5 |
| **Total**         |                         |               | **2,794** |

### Trace representative causes

Use each group's example path and UTC window to locate matching API logs.
Identical messages do not prove the same field or source-data problem. In particular,
`date_type` alone does not prove year zero; confirm the source value before linking #418.

For created/duplicate outcomes, verify actual metadata identities and archive mappings.
Rerun `query.sql` and save new results; path-derived identities can differ from metadata.
Keep unresolved requests separate until their state is checked. Never delete discovery
state or checkpoints to force recovery.
