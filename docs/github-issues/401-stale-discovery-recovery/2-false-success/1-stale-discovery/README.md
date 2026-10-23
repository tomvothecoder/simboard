# Test #401: stale discovery recovery

Issue evidence and diagnostic scripts live in `docs/github-issues/401-stale-discovery-recovery/`.
Historical result files retain paths recorded at capture time, before this move.
The baseline log is explicitly allowed by the local `.gitignore`; Python caches
and other runtime logs remain ignored. No files are staged or committed automatically.

Test [PR #405](https://github.com/E3SM-Project/simboard/pull/405) inside the
**NERSC Spin dev ingestion container**, not a Perlmutter login shell.
**Do not delete discovery state or checkpoints.** Recovery without deletion is the test.

## Full reingestion investigations

Keep these two investigations separate. Their inventories differ and may overlap;
do not add their counts together as a total number of missing executions.

- [1. HTTP errors](1-http-errors/): HTTP 409 failed case submissions and retried
  duplicate-case HTTP 500 responses. Contains aggregate and detailed SQL results
  for all 851 affected case identities.
- [2. False success](2-false-success/): follow-up for all 2,795 unresolved
  source-directory paths after reported success. Contains the DBeaver query, baseline CSV,
  sequential replay script, tests, and replay instructions.

Shared evidence remains [`perlmutter-full-archive-reingestion.log`](perlmutter-full-archive-reingestion.log), run
`ab0c7d0e-0a06-47c2-be72-53dccb537a11`. Do not duplicate or modify this baseline
log. Use `2-false-success/` for new replay evidence. False success is confirmed for
the tested `zender` execution, not yet for every unmatched path.

The sections below preserve the original single-execution stale-discovery test.

## 1. Prepare the dev containers

- Deploy PR #405's code to both the dev API and ingestion containers.
- Confirm both containers can read the archive at `/OLD_PERF`.
- Open a shell in the dev ingestion container. Use its configured Python and API credentials.
- Verify the configured API destination is dev. Back up dev before apply.
- Do not use the host-side Make launcher or `$HOME/.config/simboard/env.dev.sh` here.

```bash
cd /app
```

## 2. Select one execution

Use the composed case: the baseline case's rejection was already deleted during diagnosis.
This path appeared in the source-directory backfill log.

```bash
export MACHINE_NAME=perlmutter
export SCAN_MODE=archive
export OLD_PERF_ARCHIVE_ROOT=/OLD_PERF
export OLD_PERF_SOURCE_ROOT=/global/cfs/cdirs/e3sm/OLD_PERF
export ARCHIVE_YEAR_START=2026-10
export ARCHIVE_YEAR_END=2026-10
export SIMBOARD_INGESTION_LOG_LEVEL=DEBUG
read -r -s -p 'Dev SimBoard API token: ' SIMBOARD_API_TOKEN
printf '\n'
export SIMBOARD_API_TOKEN

test -n "$SIMBOARD_API_TOKEN" && printf 'API token is set.\n'

case_name='E1.composed.pm-gpu.r05'
execution_id='59694792.261011-211434'
export EXECUTION_DIR="/OLD_PERF/2026-10/performance_archive_2026_10_12_10_02_55/COMPLETED/mahf708/$case_name/$execution_id"

ls -ld "$EXECUTION_DIR"
```

Discovery and API submission use `/OLD_PERF`; recorded source mappings use the
absolute host root from `OLD_PERF_SOURCE_ROOT`.

### Historical result (Perlmutter host)

Directory exists. Operator observed:

```text
drwxrwsr-x 4 mahf708 e3sm 16384 Oct 12 10:03 /global/cfs/cdirs/e3sm/OLD_PERF/2026-10/performance_archive_2026_10_12_10_02_55/COMPLETED/mahf708/E1.composed.pm-gpu.r05/59694792.261011-211434
```

This confirms host directory existence, not container visibility. Repeat the
listing above inside Spin before continuing; its result has not been supplied.

## 3. Confirm the cached rejection

Run SQL against **dev database**. Save the row ID for comparison after apply.

```sql
SELECT
    d.id,
    m.name AS machine,
    d.case_identity,
    d.execution_id,
    d.outcome
FROM execution_discovery_results AS d
JOIN machines AS m ON m.id = d.machine_id
WHERE m.name = 'perlmutter'
  AND d.case_identity = 'mahf708/E1.composed.pm-gpu.r05'
  AND d.execution_id = '59694792.261011-211434';
```

Expected: `rejected_incomplete` or `rejected_invalid`. Leave the row intact.
For a fresh regression test, choose another rejected execution if already accepted
or ingested. To resume after step 6 attempt 2 below, `accepted` is expected and
does not mean ingestion succeeded; keep the row and continue.

### Historical result

Dev SQL confirmed the cached rejection. Preserve this row for the recovery test:

| Field            | Value                                  |
| ---------------- | -------------------------------------- |
| Discovery row ID | `742f58eb-2b3d-46c3-8b9e-e9510d7ddb50` |
| Machine          | `perlmutter`                           |
| Case identity    | `mahf708/E1.composed.pm-gpu.r05`       |
| Execution ID     | `59694792.261011-211434`               |
| Outcome          | `rejected_incomplete`                  |

After apply, SQL confirmed `accepted` with the same discovery row ID:
`742f58eb-2b3d-46c3-8b9e-e9510d7ddb50`. The cached rejection was updated in place.

## 4. Dry run with remote state

```bash
DRY_RUN=true DRY_RUN_USE_REMOTE_STATE=true \
python -m app.scripts.ingestion.nersc_archive_ingestor
```

Expected: **selected 1; incomplete, invalid, and unreadable 0**.
The cached rejection must not prevent fresh validation.
If resuming after successful discovery persistence, the stored `accepted` result
may bypass validation; step 5 still performs fresh offline validation.

### Historical result (Perlmutter host)

Passed with remote state enabled on October 20, 2026.

| Run ID                                 | Selected | Incomplete | Invalid | Unreadable | Exit code | Duration (seconds) |
| -------------------------------------- | -------: | ---------: | ------: | ---------: | --------: | -----------------: |
| `5c3cb450-9a43-41d5-b937-c560ce6aa2f4` |        1 |          0 |       0 |          0 |         0 |              4.102 |
| `b9fc26fd-7639-4c7a-b877-f40274f8eaf7` |        1 |          0 |       0 |          0 |         0 |               3.45 |

Both runs visited one case directory and selected `59694792.261011-211434`
with reason `new_execution`. Ingestion was not attempted (`dry_run=true`).

## 5. Compare without remote state

```bash
DRY_RUN=true DRY_RUN_USE_REMOTE_STATE=false \
python -m app.scripts.ingestion.nersc_archive_ingestor
```

Expected: the same selection and validation results.
Rerun step 3 SQL: the stored outcome must remain unchanged because dry runs perform no writes.
If fresh validation fails, investigate the files; do not clear state to force acceptance.

### Historical result (Perlmutter host)

Offline comparison passed on October 20, 2026.

| Run ID                                 | Selected | Incomplete | Invalid | Unreadable | Exit code | Duration (seconds) |
| -------------------------------------- | -------: | ---------: | ------: | ---------: | --------: | -----------------: |
| `54f1273a-2b12-4a63-92bd-d83d8ab9a979` |        1 |          0 |       0 |          0 |         0 |              0.009 |

Log confirmed `Remote state: disabled (offline)`. Selection and validation counts
matched step 4. Ingestion was not attempted (`dry_run=true`).

The post-dry-run SQL result has not been supplied; unchanged persisted rejection
state at that intermediate point remains unverified. Later apply, SQL verification,
and duplicate-protection checks passed.

## 6. Apply to dev and verify

**This writes to dev. Proceed only after both dry runs pass and the PR API is deployed.**

```bash
DRY_RUN=false \
python -m app.scripts.ingestion.nersc_archive_ingestor
```

- Require successful ingestion with no per-execution errors, not just exit code 0.
- Rerun step 3 SQL: expect `accepted` with the same discovery row ID.
- Verify the execution and absolute archive mapping:

```sql
SELECT
    e.id,
    e.execution_id,
    sd.kind,
    sd.path
FROM executions AS e
JOIN cases AS c ON c.id = e.case_id
JOIN machines AS m ON m.id = c.machine_id
LEFT JOIN source_directories AS sd ON sd.execution_id = e.id
WHERE m.name = 'perlmutter'
  AND c.hpc_username = 'mahf708'
  AND c.name = 'E1.composed.pm-gpu.r05'
  AND e.execution_id = '59694792.261011-211434';
```

Expected: an execution record with an `archive` mapping under `/global/cfs/cdirs/e3sm/OLD_PERF/`.

### Historical result (Perlmutter host)

**Attempt 1: blocked by old API behavior** on October 20, 2026.

- Run ID: `48c67538-cc64-411b-a25a-527e99109958`.
- Discovery selected 1 execution; incomplete, invalid, and unreadable counts were 0.
- Discovery-result persistence returned HTTP 409 before ingestion submission.
- Exit code: `1`; duration: `3.597` seconds; submission was not attempted.

```text
Discovery result conflicts with immutable stored outcome for case_identity='mahf708/E1.composed.pm-gpu.r05', execution_id='59694792.261011-211434'.
```

**Attempt 2: persistence passed; ingestion blocked by API filesystem access.**

- Run ID: `d1ca7acc-cd4c-4d5e-aefe-ad72ef8c375f`.
- Discovery selected 1 execution with no validation failures.
- The runner passed discovery-result persistence and attempted ingestion.
- API returned HTTP 400: the submitted case path does not exist in its filesystem.
- Exit code: `1`; duration: `4.042` seconds; selected case outcome: failed.

```text
Archive path '/global/cfs/cdirs/e3sm/OLD_PERF/2026-10/performance_archive_2026_10_12_10_02_55/COMPLETED/mahf708/E1.composed.pm-gpu.r05' does not exist.
```

The host attempts encountered incompatible API behavior, then a host/container
path mismatch. The Spin retry below resolved both blockers.

### Result (NERSC Spin container)

**Attempt 3: ingestion succeeded** on October 20, 2026, using `/OLD_PERF`.

| Field                               | Result                                               |
| ----------------------------------- | ---------------------------------------------------- |
| Run ID                              | `7dceb607-f7a3-4838-a243-f3c83efe55a1`               |
| Container                           | `backend-5dc968c9c7-67nxm`, working directory `/app` |
| API                                 | `http://backend:8000`                                |
| Created / duplicates / errors       | `1 / 0 / 0`                                          |
| Selected / succeeded / failed cases | `1 / 1 / 0`                                          |
| Exit code / duration                | `0 / 4.755` seconds                                  |

The operator manually exported the API token using a hidden prompt; no token is
recorded here. The runner reused accepted discovery state
(`execution_dirs_scanned=0`, `execution_dirs_accepted=1`) and created the execution
on its first submission attempt. This run confirms ingestion, not fresh rejection
revalidation; steps 4 and 5 provide that earlier evidence.

**SQL verification passed:**

- Discovery row `742f58eb-2b3d-46c3-8b9e-e9510d7ddb50` now reports `accepted`.
- Execution record `92eca331-849e-4e4f-a8b2-20b825631eba` exists for `59694792.261011-211434`.
- Its `archive` mapping uses the absolute host path:

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2026-10/performance_archive_2026_10_12_10_02_55/COMPLETED/mahf708/E1.composed.pm-gpu.r05/59694792.261011-211434
```

## 7. Check duplicate protection

Repeat step 4. Expected: **selected 0, skipped 1**, reason `already_processed`.

```bash
DRY_RUN=true DRY_RUN_USE_REMOTE_STATE=true \
python -m app.scripts.ingestion.nersc_archive_ingestor
```

### Result (NERSC Spin container)

Passed on October 20, 2026.

| Field                             | Result                                 |
| --------------------------------- | -------------------------------------- |
| Run ID                            | `5830cb65-190d-48d0-b174-364f22c2a611` |
| Selected / skipped                | `0 / 1`                                |
| Skip reason                       | `already_processed`                    |
| Incomplete / invalid / unreadable | `0 / 0 / 0`                            |
| Exit code / duration              | `0 / 3.602` seconds                    |

No ingestion was attempted. Successful-ingestion deduplication remained active.

**Pass:** stale rejection recovers without deletion, ingestion creates the owner/mapping,
and subsequent scanning skips the successfully ingested execution.

## Limits

- Historical bulk procedures referenced `BULK_RECOVERY_CHRYSALIS.md` and
  `BULK_RECOVERY.md`; neither file is included in this evidence snapshot.
  Use the investigation guides above for the current Perlmutter checks.
- `EXECUTION_DIR` bypasses snapshot checkpoints without clearing or completing them.
- `DRY_RUN_USE_REMOTE_STATE=false` affects dry runs only; apply reads remote state.
- Accepted discovery means validation passed, not that ingestion succeeded.
- Existing execution dates are not overwritten by normal ingestion.
- For bulk recovery, select and deduplicate `COMPLETED` archive paths reported as
  `skipped_no_owner` in `backend/qa/360-backfill-metadata/source-directories-60017617.log`.
  Verify each exact machine/user/case/execution identity before applying.
