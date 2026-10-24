# Verify year-zero model dates (PR #424)

`verify_year_zero.py` selects all executions with a `simulation_start_date`
`year_zero_date` diagnosis from the saved scan in `3-debug-validation-errors`.
It includes secondary date errors, not only the original first failure, and
deduplicates execution paths. Other validation groups are not replayed.

Run directly on Perlmutter from the repository root using the backend environment.
Preview makes no requests:

```bash
VERIFY=docs/github-issues/401-stale-discovery-recovery/2-false-success/4-verify-fixes
export SIMBOARD_API_BASE_URL=https://simboard-dev-api.e3sm.org/api/v1
uv run --project backend python "$VERIFY/verify_year_zero.py" --limit 1
```

Deploy PR #424 and apply its database migration before testing. Perlmutter must
have access to the original `/global/cfs/cdirs/e3sm/OLD_PERF` paths. The script
packages each selected local execution and posts it to
`/api/v1/ingestions/from-hpc-upload`; no Spin shell or API archive mount is needed.
Set `SIMBOARD_API_BASE_URL` to your target's public API URL (the URL above is an
example). Use an admin or service-account token through the
environment; do not put the token in the command or commit it.

**Apply writes ingestion data to the selected API.** First test one execution:

```bash
# Set SIMBOARD_API_TOKEN through your existing secure environment setup.
uv run --project backend python "$VERIFY/verify_year_zero.py" \
  --apply --limit 1 --log "$VERIFY/year-zero-single.jsonl"
```

Then loop over all related executions using a different, new log:

```bash
uv run --project backend python "$VERIFY/verify_year_zero.py" \
  --apply --log "$VERIFY/year-zero-all.jsonl"
```

The script uses the existing sequential replay client. Each request targets one
execution archive with `processed_execution_ids`, not the entire case. It logs request
starts, full responses, and a final summary. No retries or direct discovery-state
changes occur. Authentication, transport, or ambiguous responses stop the run.
Use `--scan PATH` to select another saved scan, or `--timeout` and `--delay` to
adjust request pacing. Keep the sibling replay script and scan available in the
checkout. Temporary upload archives are removed after each request.

Exit 0 means every selected request reported creation or a duplicate. HTTP 200
alone does not count as success. Exit 1 means failure, an unconfirmed outcome,
or incomplete replay; CLI/input errors exit 2. A duplicate does not prove the
date was reparsed. Inspect `request_finished.response_body` for remaining errors:
another validation group may now block an execution after the date fix.
This checks ingestion outcomes, not persisted date round-trip values.

## Verify component-set validation (PR #428)

`verify_compset.py` uses the same Perlmutter upload flow and options. It selects
all executions with invalid component-set fields in the saved scan, including
secondary errors, and deduplicates paths. It recognizes historical `compset`
errors and the renamed `compset_long_name` field. It does not select unrelated
`compset_alias` errors.

Deploy PR #428 and its database migration before applying. With the API URL and
admin/service-account token already set, run from the repository root:

```bash
VERIFY=docs/github-issues/401-stale-discovery-recovery/2-false-success/4-verify-fixes

# Preview all matching executions; no requests.
uv run --project backend python "$VERIFY/verify_compset.py"

# Upload all matching executions; writes ingestion data.
uv run --project backend python "$VERIFY/verify_compset.py" \
  --apply --log "$VERIFY/compset-all.jsonl"
```

Omit `--limit` to loop over every matching execution. Each response remains in
the log, including any other validation error exposed after the component-set
fix. Creation confirms ingestion succeeds; duplicates do not prove metadata was
reparsed. This script does not repair metadata on existing executions or check
persisted `compset_long_name` values.
