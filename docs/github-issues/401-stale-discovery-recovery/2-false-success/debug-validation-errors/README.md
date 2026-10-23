# Read-only validation diagnostics

`reproduce_validation_errors.py` checks representative executions. Use
`scan_validation_errors.py` to diagnose every failed execution in a replay log.
Neither script calls the API, accesses the database, or changes archive files.

## Scan the replay inventory

Run from the repository root on a host with archive access:

```bash
debug='docs/github-issues/401-stale-discovery-recovery/2-false-success/debug-validation-errors'
uv run --project backend python "$debug/scan_validation_errors.py"
```

The default input is `../2-replay-results/replay-final.jsonl`, relative to the script.
Pass another replay JSONL as the positional argument. Use `--limit 10` for a sample.
The script deduplicates paths using the latest completed timestamp before selecting
failed executions with `ValidationError`. Equal timestamps use the last record.
It rejects malformed JSONL and mixed run IDs. A partial replay log covers only its
completed requests, not the full unresolved inventory.
Inputs must come from single-execution replay requests. Errors naming a different
execution directory are rejected rather than attributed to the requested path.

For container archive mounts:

```bash
uv run --project backend python "$debug/scan_validation_errors.py" --archive-root /OLD_PERF
```

`--source-root` sets the path prefix recorded in the replay log. `--archive-root`
sets the local mount replacing that prefix. Both default to the host archive root.
Paths outside the source root, including parent traversal, are rejected.

## Saved evidence

Each run creates new files beside the script without overwriting earlier runs:

- `validation-scan-<UTC timestamp>.jsonl`: one record per execution, including
  original replay errors, source paths, parsed source metadata, selected XML
  entries, bounded `create_newcase` lines, normalized inputs, and field errors.
- `validation-scan-<UTC timestamp>-groups.json`: execution totals, field-error
  totals, original replay groups, source issues, and groups by field, code, and
  observed cause. Groups include example paths and counts of additional errors
  absent from the original field/code pairs.

All eight scalar pre-case checks run independently: execution ID, compset,
compset alias, grid name, grid resolution, initialization type, simulation start
date, and optional repository URL. Production parsers and normalization supply
the values. The coupler clock overrides XML dates, matching ingestion precedence.
Each relevant file parser runs once per execution.
Parsers may internally reread their source files. Diagnostics also preflight files
to detect read failures that production parsers suppress.

Missing required files, ambiguous matches, unreadable files, and invalid XML block
dependent field checks. They do not become misleading scalar `None` failures.
Dates follow production fallback: an unreadable coupler log still allows the XML
date check, and a usable coupler date does not depend on readable XML. Source
issues remain in the report even when a fallback permits validation.
Missing optional repository metadata skips URL validation, matching ingestion.
Parsed `None` alone does not prove missing source data. Cause labels describe
observations, not definitive upstream explanations. Inspect saved source evidence.

The summary counts distinct executions separately from field errors. One execution
can have multiple errors. `matching_original_errors` compares field/code pairs;
it does not prove that the source value or upstream cause matches the old replay.
Checks use the current checkout and archive contents, not the historical deployment.
This scan does not perform full archive qualification, full schema validation,
case identity resolution, or database checks.

Exit `0` means all selected executions were checked, even if validation failed.
Exit `1` means source issues or blocked fields remain. Exit `2` means invalid input
or output failure. An interrupted scan exits `130`; its detail file may be partial
and has no complete summary. Existing evidence remains unchanged.

## Offline checks

```bash
uv run --project backend pytest -q -o addopts='' "$debug/test_scan_validation_errors.py"
uv run --project backend python -m doctest "$debug/reproduce_validation_errors.py"
```
