# Perlmutter HTTP request failures

## Overview

This document summarizes the investigation of HTTP request failures encountered on NERSC after a full-reingestion of the Perlmutter archive.
It provides an overview of affected cases, the results of inventory and replay checks, and guidance for further analysis.

## 1. Initial Checks - Run SQL query

Run [`a-initial-checks/query.sql`](a-initial-checks/query.sql) as a SQL script in DBeaver, or execute each statement
separately. Export the aggregate and detail tables separately with headers.
The query is self-contained and read-only; catalog results reflect execution time.

- Checks all accepted discoveries for affected cases, not exact failed-snapshot completeness.
- Directory-derived identities may differ from parsed metadata identities.
- An archive mapping flag confirms any archive mapping, not the exact failed path.
- Use aggregate totals; per-case request counts repeat in execution detail rows.

### SQL results analysis

**All 851 affected cases exist. Of 3,308 accepted discovery executions, 3,305 exist and three lack an exact catalog match.**

Evidence: [`a-initial-checks/query_results_agg.csv`](a-initial-checks/query_results_agg.csv) and
[`a-initial-checks/query_results.csv`](a-initial-checks/query_results.csv). Aggregate and detail exports agree.

| Case group         |   Cases | Executions checked |  Existing | Missing |
| ------------------ | ------: | -----------------: | --------: | ------: |
| HTTP 409 only      |     162 |              2,064 |     2,061 |       3 |
| HTTP 500 only      |     679 |              1,093 |     1,093 |       0 |
| Both HTTP statuses |      10 |                151 |       151 |       0 |
| **Total**          | **851** |          **3,308** | **3,305** |   **3** |

- All 3,305 existing executions have an archive mapping.
- No affected cases lack accepted discovery records.
- Groups are mutually exclusive; the total includes each case once.

### HTTP failure inventory

Source: [`../perlmutter-full-archive-reingestion.log`](../perlmutter-full-archive-reingestion.log),
run `ab0c7d0e-0a06-47c2-be72-53dccb537a11`.

- **216 HTTP 409 failures:** no retries; final case submissions failed.
  Response: `Constraint violation while writing to the database.` Exact constraints remain unknown.
- **689 HTTP 500 failures:** duplicate-case violations on
  `uq_cases_name_machine_id_hpc_username`; retries reported successful submissions.
- **905 distinct failed-request paths**, covering 851 case identities. No HTTP 401 failures.

Request outcomes are not execution outcomes. These results do not prove the
HTTP failures were harmless duplicates.

#### Missing executions: separate from HTTP 409 failures

All three belong to `zender/v3.LR.I.era5_1980s_hex_cld_srt_frn_spn`:

```text
46898596.251223-143828
46899412.251223-155819
46900644.251223-225236
```

Explanation:

- These executions belong to December snapshots reported successful, not the
  January/February HTTP 409 paths listed for the same case.
  They appear because
  the query checks all accepted discoveries for each affected case.

Reproducibility:

- A direct replay of `46898596.251223-143828` returned HTTP 201 with zero creations
  and a date validation error: `Input should be a valid date`, input `None`.
  The other two have not been confirmed to share that error.

## Next checks: run on Perlmutter

Run from the repository root. Use the repository's uv environment.
Avoid concurrent ingestion during baseline checks and replay.

```bash
qa='docs/github-issues/401-stale-discovery-recovery/1-http-errors/'
```

### 1. Build an archive baseline

**Goal:** check executions in the exact failed snapshots, not only database discovery records.
This step reads archives; it never contacts the API or database.

Preview the selected paths. No archive scan or requests occur:

```bash
PYTHONPATH=backend uv run --project backend python "$qa/inventory_http_errors.py"
```

Scan all 905 failed case paths into a new output directory:

```bash
baseline="$qa/inventory-$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH=backend uv run --project backend python "$qa/inventory_http_errors.py" --output-dir "$baseline"
```

**Results from files**

| File                                                        | Result                                                                                                          |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| [`inventory.csv`](b-inventory-before/inventory.csv)         | 905 paths; 1,353 observations: 1,311 qualified, 42 incomplete.                                                  |
| [`summary.json`](b-inventory-before/summary.json)           | Scan completed. No read, parsing, or identity errors. No API requests or database connections.                  |
| [`query_agg.csv`](b-inventory-before/query_agg.csv)         | All 1,311 qualified executions exist with exact archive mappings. The 42 incomplete observations span 19 paths. |
| [`query_details.csv`](b-inventory-before/query_details.csv) | Confirms each qualified identity, execution record, and exact mapping. All four files agree.                    |

**Overall results**

**No data recovery is needed for the qualified executions in these 905 checked paths.**

- All 1,311 submission-qualified executions exist with exact archive mappings: 368 from HTTP 409 paths and 943 from HTTP 500 paths.
- The other 42 observations were incomplete and did not qualify for submission.
- Replay would investigate **why the HTTP errors occurred**, not recover missing records in this baseline.
- The three missing `zender` executions belong to other snapshots. Continue in [2. False success](../2-false-success/README.md).

Scope: immediate execution directories in the scanned snapshots at query time, not the full archive. HTTP failure causes remain unresolved.
Next: Why did the HTTP errors occur even though all qualified executions exist?

### 2. Replay one request from each HTTP group

**Goal:** capture full responses and identify the constraints behind HTTP 409/500 failures.

#### Set these environment variables for the API base URL and token:

```bash
export SIMBOARD_API_BASE_URL="https://simboard-dev-api.e3sm.org/api/v1"
read -r -s -p 'Dev SimBoard API token: ' SIMBOARD_API_TOKEN
printf '\n'
export SIMBOARD_API_TOKEN
```

#### Preview one original HTTP 409 case path:

```bash
qa='docs/github-issues/401-stale-discovery-recovery/1-http-errors'
uv run --project backend python "$qa/replay_http_errors.py" --status 409 --limit 1
```

```bash
{
  "mode": "preview",
  "endpoint": "https://simboard-dev.e3sm.org/api/v1/ingestions/from-path",
  "external_https_api_required": false,
  "selected_case_paths": 1,
  "http_status_filter": "409",
  "first": {
    "case_path": "/OLD_PERF/2025-01/performance_archive_2025_01_05_07_01_00/COMPLETED/ndk/gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001304",
    "path_username": "ndk",
    "path_case_name": "gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001304",
    "original_final_outcome": "failed",
    "failed_attempts": [
      {
        "timestamp_utc": "2026-10-20T23:17:07.736Z",
        "attempt": 1,
        "http_status": 409
      }
    ],
    "original_http_statuses": [
      409
    ]
  },
  "requests_sent": 0
}
```

**Apply writes catalog data and ingestion history.** It reprocesses the whole original
case snapshot, bypassing runner selection. The API reads `/OLD_PERF`; no upload is needed.

#### Confirm the destination is dev, then replay one case from each group.

```bash
uv run --project backend python "$qa/replay_http_errors.py" --status 409 --limit 1 --apply --log "$qa/replay-409-single.jsonl"
uv run --project backend python "$qa/replay_http_errors.py" --status 500 --limit 1 --apply --log "$qa/replay-500-single.jsonl"
```

#### Replay results — October 22, 2026

Both replays succeeded without reproducing the original errors.

| Original error | Case                            | Replay HTTP | Created | Duplicates | Execution errors |
| -------------- | ------------------------------- | ----------- | ------: | ---------: | ---------------: |
| 409            | `ndk/...nid001304`              | 201         |       0 |          1 |                0 |
| 500            | `zhangtao/v3.HR.F2010.STE.tune` | 201         |       0 |          2 |                0 |

**Takeaway:** the API recognized all three existing executions as duplicates.
Neither replay created executions or reported execution errors.

Duplicate handling works for these two cases now. The historical HTTP 409/500
causes remain unresolved; successful replays do not explain the original failures.
Continue the separate [false-success investigation](../2-false-success/README.md)
for missing executions.

**Recorded command output**:

```bash
(.venv) vo13@login37:~/tomvothecoder/simboard$ uv run --project backend python "$qa/replay_http_errors.py" --status 409 --limit 1 --apply --log "$qa/replay-409-single.jsonl"
{
  "timestamp": "2026-10-22T22:37:29.696405+00:00",
  "event": "run_started",
  "run_id": "345a8a0b-544d-445d-83ee-9af945cf8ac7",
  "endpoint": "https://simboard-dev-api.e3sm.org/api/v1/ingestions/from-path",
  "selected_case_paths": 1,
  "retries": 0
}
{
  "timestamp": "2026-10-22T22:37:29.696718+00:00",
  "event": "request_started",
  "run_id": "345a8a0b-544d-445d-83ee-9af945cf8ac7",
  "attempt_id": "1d4e99ed-8030-4222-9462-40bf2e4dad18",
  "index": 1,
  "case_path": "/OLD_PERF/2025-01/performance_archive_2025_01_05_07_01_00/COMPLETED/ndk/gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001304",
  "path_username": "ndk",
  "path_case_name": "gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001304",
  "original_final_outcome": "failed",
  "failed_attempts": [
    {
      "timestamp_utc": "2026-10-20T23:17:07.736Z",
      "attempt": 1,
      "http_status": 409
    }
  ],
  "original_http_statuses": [
    409
  ]
}
{
  "timestamp": "2026-10-22T22:37:30.570276+00:00",
  "event": "request_finished",
  "run_id": "345a8a0b-544d-445d-83ee-9af945cf8ac7",
  "attempt_id": "1d4e99ed-8030-4222-9462-40bf2e4dad18",
  "index": 1,
  "case_path": "/OLD_PERF/2025-01/performance_archive_2025_01_05_07_01_00/COMPLETED/ndk/gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001304",
  "path_username": "ndk",
  "path_case_name": "gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001304",
  "original_final_outcome": "failed",
  "failed_attempts": [
    {
      "timestamp_utc": "2026-10-20T23:17:07.736Z",
      "attempt": 1,
      "http_status": 409
    }
  ],
  "original_http_statuses": [
    409
  ],
  "http_status": 201,
  "outcome": "successful_case_requests",
  "response_body": {
    "created_count": 0,
    "duplicate_count": 1,
    "executions": [],
    "errors": []
  },
  "raw_response": "{\"created_count\":0,\"duplicate_count\":1,\"executions\":[],\"errors\":[]}",
  "transport_error": null,
  "duration_seconds": 0.873
}
{
  "timestamp": "2026-10-22T22:37:30.570732+00:00",
  "event": "run_summary",
  "run_id": "345a8a0b-544d-445d-83ee-9af945cf8ac7",
  "status": "success",
  "selected_case_paths": 1,
  "not_attempted_case_requests": 0,
  "interrupted": false,
  "attempted_case_requests": 1,
  "http_succeeded": 1,
  "http_failed": 0,
  "http_unknown": 0,
  "http_409": 0,
  "http_500": 0,
  "successful_case_requests": 1,
  "execution_error_requests": 0,
  "empty_response_requests": 0,
  "invalid_response": 0,
  "unconfirmed_case_requests": 0,
  "created_executions": 0,
  "duplicate_executions": 1,
  "failed_executions_reported": 0
}
(.venv) vo13@login37:~/tomvothecoder/simboard$ uv run --project backend python "$qa/replay_http_errors.py" --status 500 --limit 1 --apply --log "$qa/replay-500-single.jsonl"
{
  "timestamp": "2026-10-22T22:37:42.247753+00:00",
  "event": "run_started",
  "run_id": "ec5c630e-5ba2-4250-bfca-50a1780273e2",
  "endpoint": "https://simboard-dev-api.e3sm.org/api/v1/ingestions/from-path",
  "selected_case_paths": 1,
  "retries": 0
}
{
  "timestamp": "2026-10-22T22:37:42.248088+00:00",
  "event": "request_started",
  "run_id": "ec5c630e-5ba2-4250-bfca-50a1780273e2",
  "attempt_id": "7f09cd20-5bfd-47ee-8e8f-b2815e45d089",
  "index": 1,
  "case_path": "/OLD_PERF/2025-01/performance_archive_2025_01_03_07_00_18/COMPLETED/zhangtao/v3.HR.F2010.STE.tune",
  "path_username": "zhangtao",
  "path_case_name": "v3.HR.F2010.STE.tune",
  "original_final_outcome": "succeeded",
  "failed_attempts": [
    {
      "timestamp_utc": "2026-10-20T23:15:39.105Z",
      "attempt": 1,
      "http_status": 500
    }
  ],
  "original_http_statuses": [
    500
  ]
}
{
  "timestamp": "2026-10-22T22:37:43.103120+00:00",
  "event": "request_finished",
  "run_id": "ec5c630e-5ba2-4250-bfca-50a1780273e2",
  "attempt_id": "7f09cd20-5bfd-47ee-8e8f-b2815e45d089",
  "index": 1,
  "case_path": "/OLD_PERF/2025-01/performance_archive_2025_01_03_07_00_18/COMPLETED/zhangtao/v3.HR.F2010.STE.tune",
  "path_username": "zhangtao",
  "path_case_name": "v3.HR.F2010.STE.tune",
  "original_final_outcome": "succeeded",
  "failed_attempts": [
    {
      "timestamp_utc": "2026-10-20T23:15:39.105Z",
      "attempt": 1,
      "http_status": 500
    }
  ],
  "original_http_statuses": [
    500
  ],
  "http_status": 201,
  "outcome": "successful_case_requests",
  "response_body": {
    "created_count": 0,
    "duplicate_count": 2,
    "executions": [],
    "errors": []
  },
  "raw_response": "{\"created_count\":0,\"duplicate_count\":2,\"executions\":[],\"errors\":[]}",
  "transport_error": null,
  "duration_seconds": 0.855
}
{
  "timestamp": "2026-10-22T22:37:43.103526+00:00",
  "event": "run_summary",
  "run_id": "ec5c630e-5ba2-4250-bfca-50a1780273e2",
  "status": "success",
  "selected_case_paths": 1,
  "not_attempted_case_requests": 0,
  "interrupted": false,
  "attempted_case_requests": 1,
  "http_succeeded": 1,
  "http_failed": 0,
  "http_unknown": 0,
  "http_409": 0,
  "http_500": 0,
  "successful_case_requests": 1,
  "execution_error_requests": 0,
  "empty_response_requests": 0,
  "invalid_response": 0,
  "unconfirmed_case_requests": 0,
  "created_executions": 0,
  "duplicate_executions": 2,
  "failed_executions_reported": 0
}
(.venv) vo13@login37:~/tomvothecoder/simboard$

```

#### API log confirmation

- [x] Match API logs by **case path and UTC window**.
- [x] Review responses before expanding replay.

Matching API logs on October 22, 2026 confirm all three duplicate skips:

| UTC time     | Execution ID             | API log result                     |
| ------------ | ------------------------ | ---------------------------------- |
| 22:37:30.562 | `34589901.250105-000759` | Already exists; skipped duplicate. |
| 22:37:43.086 | `34524149.250102-231307` | Already exists; skipped duplicate. |
| 22:37:43.096 | `34524149.250103-010226` | Already exists; skipped duplicate. |

The supplied excerpts contain no errors and agree with both replay responses.
Neither historical HTTP failure reproduced. Their causes remain unresolved.
No full 905-path replay is needed for this closeout.

Replays write data and ingestion history. Never overwrite evidence or automatically
retry after a timeout; check database state first.

### 4. Follow up on false success

- Investigate the three missing identities in [2. False success](../2-false-success/README.md).

That investigation covers HTTP-success requests with missing execution identities.
Its replay uses a separate 2,795-path CSV, not these HTTP-result CSVs.
