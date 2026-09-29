# Issue #303 Implementation Plan — Branch `devops/303-diag-cron`

## Problem

[Issue #303](https://github.com/E3SM-Project/simboard/issues/303) requests scheduled diagnostics linking alongside site ingestion. Its prerequisites are satisfied: #269 is closed, and #169 and #281 are merged.

The current crontab schedules only performance ingestion. The diagnostics scanner already exists, but its LCRC wrapper lacks protected environment-file loading, scheduler locking, and run-scoped logging. Only Chrysalis currently has a checked-in ingestion site config; the diagnostics registry supports Chrysalis and Perlmutter.

## Scope

1. **Add a scheduler-ready diagnostics launcher.**
   - New file: `backend/app/scripts/ingestion/sites/diagnostics/site_diagnostics_launcher.sh`.
   - Use the standard `SIMBOARD_ROOT` layout and backend virtual environment.
   - Require an explicit `MACHINE_NAME`; validate supported machines before execution.
   - Load `SIMBOARD_ENV_FILE` for live scans, sharing the existing API URL/token files.
   - Default to dry-run, use machine/environment-specific locks and protected run logs, and propagate scanner failures.
   - Keep this separate from `site_ingestion_launcher.sh`: diagnostics discovery is not a performance staging/archive scan.

2. **Extend the cron template without replacing ingestion jobs.**
   - Update `backend/app/scripts/ingestion/sites/templates/crontab.example` with separate diagnostics entries for development and production APIs.
   - Specify the machine and environment file explicitly; stagger diagnostics from ingestion.
   - Preserve dry-run defaults and document how operators enable each live job independently.

3. **Document deployment and migration.**
   - Update:
     - `backend/app/scripts/ingestion/sites/README.md`
     - `backend/app/scripts/README.md`
     - `docs/operations/setup-ingestion-operations.md`
     - `docs/operations/test-ingestion-operations.md`
   - Explain configuration, logs, lock contention, service-account requirements, and site-specific rollout.
   - Existing installed crontabs require manual updates: `operations-init-cron` deliberately refuses to overwrite them.

4. **Add deterministic launcher tests.**
   - New file: `backend/tests/features/ingestion/test_site_diagnostics_launcher.py`.
   - Cover module invocation, machine selection, credential-free dry runs, live environment loading, missing configuration/runtime, locking, environment isolation, log permissions/token redaction, and exit-code propagation.
   - Check that cron entries retain ingestion jobs and select the correct diagnostics machine/environment.

## Constraints and non-goals

- Preserve scanner discovery, provenance validation, state reconciliation, and API behavior; no schema, frontend, or dependency changes.
- Keep archive roots/public URLs in `diagnostics_archives.py`, not scheduler overrides.
- Do not couple scanner availability or failure to performance ingestion.
- Exclude v3 backfill automation and NERSC Spin workload changes.
- **Non-blocking assumption:** initially support the registered machines, with Chrysalis as the first rollout target.
- **Risks:** diagnostics may precede Case ingestion and need a later retry; full archive scans may exceed their scheduling interval; service-account permissions, archive access, and network reachability require host validation. Scanner dry runs do not contact the API, so successful discovery alone does not establish live readiness.

## Open questions

- **Which hosts are included in “each site,” and who owns their installed crontabs?** Site operators/issue owner must answer. Blocks deployment beyond confirmed hosts, not repository implementation.
- **What cadence and API environments should run live at each site?** Issue owner and site operators must answer. Blocks final production scheduling; implementation can provide clearly labeled example schedules.

## Acceptance criteria

- Scheduled diagnostics invoke `app.scripts.ingestion.diagnostics_link_scanner` using the intended machine and API environment.
- Default dry runs require no token and make no API requests.
- Live runs reject missing credentials before scanner execution.
- Same-machine/environment runs cannot overlap; different API environments have independent locks.
- Logs are protected, omit tokens, and expose scanner completion/failure.
- Existing performance ingestion schedules and behavior remain unchanged.
- Operators have documented dry-run, live verification, installation, and rollback steps.

## Validation

After implementation:

- Run `bash -n` on the new launcher.
- Run `make backend-test`, including the new launcher tests and existing scanner/ingestion regression tests.
- Run `make pre-commit-run` from the repository root.
- On each target host, operators review dry-run discovery, then perform a controlled live scan against an already-ingested Case, verify its diagnostic link and scanner state, and repeat to confirm unchanged-state handling before installing live cron entries.
