# Issue 361: Prerequisite Discovery Plan

## Problem

[#361](https://github.com/E3SM-Project/simboard/issues/361) scopes
[#206](https://github.com/E3SM-Project/simboard/issues/206) to EAMxx: discover
which variables are configured for output and how often, then enable useful
case/execution display and filtering.

The proposed `atm_in` settings (`finclN`, `fexclN`, `nhtfrq`, `mfilt`) come from
an explicitly unverified EAM-oriented analysis in #206. Current upstream EAMxx
documentation describes YAML output streams instead. Actual archived execution
files must establish the source contract before implementation planning.

## Scope

Complete the [prerequisite checklist](prerequisites.md) through sample collection,
source analysis, manually annotated metadata, and storage/UI decisions. Produce
evidence and agreed requirements, not application changes.

### 1. Collect and inventory execution snapshots

Owner: developer with LCRC access, assisted by the case owners as needed.

- Locate the listed cases in the configured Chrysalis performance archive.
  Consult `docs/architecture/metadata-ingestion.md` for archive layout; do not
  infer a filesystem path solely from a SimBoard URL.
- Copy complete execution-specific `CaseDocs` and relevant identity/provenance
  files into a separate home-directory workspace, preserving archive filenames
  and compression. Do not modify the source archive.
- Record machine, HPC username, case name, execution ID/LID, archive snapshot,
  original path, local path, and model revision when available.
- Inventory files before narrowing the parser inputs. Inspect several executions
  of a case where available to detect configuration changes.
- Keep raw snapshots outside Git. Record whether sanitized excerpts can become
  future test fixtures, with permission from the data owners.

Deliverable: sample manifest and file inventories, including any access gaps.

### 2. Establish the source and settings contract

Owner: developer; EAMxx domain expert verifies ambiguous semantics.

- Inspect `atm_in` if present and determine its role. Look for
  `eamxx_input.yaml`, `namelist_eamxx.xml`, and output-stream YAML files without
  assuming these names are present in every archived model version.
- Trace the active `output_yaml_files` configuration to the archived stream
  files. Distinguish active streams from unrelated YAML files.
- Determine whether archived values are resolved and whether referenced files
  are present. Record unavailable or ambiguous references rather than guessing.
- Verify settings against the model revision for each sample. Upstream EAMxx
  candidates are `fields.<grid>.field_names`, `output_control.frequency`,
  `output_control.frequency_units`, `averaging_type`, and `filename_prefix`.
- Treat `max_snapshots_per_file` and `file_max_storage_type` as file packaging,
  not cadence. Do not transfer EAM's signed `nhtfrq` interpretation to YAML.
- Check diagnostics, aliases, restart streams, and automatically included grid
  fields, and document what the initial feature will include or exclude.

Deliverable: verified source-file map and settings dictionary with examples,
revision-specific evidence, defaults, and unresolved cases.

### 3. Define expected metadata

Owner: developer, reviewed by the requester/EAMxx domain expert.

- Define records conceptually as execution → stream → fields grouped by grid,
  with frequency value/unit and averaging type attached to the stream.
- Preserve requested field spelling/case, source provenance, and raw cadence.
  Specify readable labels without approximating calendar months or converting
  steps to elapsed time without known timestep information.
- Decide whether names refer to configuration requests or final written names;
  aliases and diagnostic fields must not silently change that meaning.
- Manually annotate expected records for each sample. Include the same field in
  multiple streams, distinct cadences, and differing executions where available.
- Define separate states for known empty configuration, unavailable source,
  unsupported configuration, and extraction failure.

Deliverable: metadata contract and annotated examples suitable for future tests.

### 4. Decide storage and query semantics

Owner: developer proposes; SimBoard maintainers/requester agree.

- Use execution ownership as the starting recommendation: configuration is an
  execution snapshot, not necessarily shared case metadata.
- Compare structured JSONB with relational stream/field records using real
  sample sizes and required filtering queries. `Execution.extra` exists but is
  not already an output-metadata contract.
- Agree on case aggregation: any execution, latest execution, or every execution.
  Any-execution matching is a proposal, not an accepted requirement.
- Specify example queries for variable-only and variable-plus-cadence searches.
  Combined field/cadence/averaging predicates must match the same stream within
  the same execution, not unrelated records.
- Determine which fields require indexed/filterable storage versus display only.

Deliverable: storage recommendation with tradeoffs and agreed query examples;
no migration implementation at this stage.

### 5. Agree on UI behavior

Owner: developer drafts; requester/SimBoard team approves scope.

- Sketch an execution-detail section grouped by output stream, showing requested
  fields, grid, cadence, averaging type, and metadata availability.
- Sketch a clearly labeled case summary that follows the agreed aggregation
  rule and points users to matching executions.
- Specify catalog filtering and whether cadence/averaging filters belong in the
  initial scope. Detail-page text search alone does not provide cross-case
  discovery.
- Review examples with multiple streams and differing execution configurations
  so the UI does not imply every variable applies to every execution.

Deliverable: lightweight mockups and agreed display/filter behavior.

### 6. Verify collection coverage and historical handling

Owner: developer and ingestion maintainers.

- Trace LCRC remote-upload packaging and NERSC ingestion to verify preservation
  of all required files, including archived/compressed naming variants.
- If output YAML files are absent, identify whether the gap is in model
  archival, performance collection, submission packaging, or backend parsing.
- Decide how optional missing/malformed output metadata affects ingestion.
- Decide whether existing executions need enrichment. Known execution IDs are
  skipped by current collection, so parser changes alone are not a backfill.
- Record backfill requirements, permissions, and operational constraints without
  running ingestion or changing stored state during discovery.

Deliverable: collection-coverage matrix and explicit failure/backfill decisions.

## Constraints and non-goals

- No parser, database, API, frontend, or ingestion-runner implementation.
- No migrations, production ingestion, or historical backfill execution.
- EAMxx only; other model components remain outside this discovery scope.
- Configuration describes requested output, not proof of written or accessible
  NetCDF data. NetCDF inspection/output validation is outside scope.
- Do not mark prerequisites complete based only on current upstream documentation;
  sample-specific verification is required.

Non-blocking working assumptions, pending confirmation:

- Execution snapshots own authoritative metadata; case summaries are derived.
- Missing optional output metadata should not reject otherwise valid executions.
- Raw archive samples stay outside Git; only approved sanitized fixtures may be
  committed later.

## Open questions

| Question | Answer owner | What it blocks |
| --- | --- | --- |
| Which archived files exist for the listed executions, and can they be copied? | Developer with LCRC access / case owners | Source contract and sample analysis |
| Do variable names mean requested fields, written names, or both? | Requester / EAMxx domain expert | Metadata contract |
| Are restart streams and automatically included grid fields in scope? | Requester / EAMxx domain expert | Final extraction scope |
| Does case matching mean any, latest, or all executions? | Requester / SimBoard team | Case queries and UI semantics |
| Are cadence and averaging filters required initially? | Requester / SimBoard team | Storage evaluation and UI scope |
| Must existing executions be enriched? | Ingestion maintainers / requester | Backfill scope |

These questions do not block collecting samples or documenting findings, but
must be resolved before the corresponding feature implementation is planned.

## Acceptance criteria

- Each starting case has inventoried execution samples, or an explicit unresolved
  access/data gap; gaps prevent declaring source discovery complete.
- Active streams can be traced to archived configuration, with missing references
  documented and no unsupported claim that `atm_in` alone is sufficient.
- Settings and frequency semantics have sample/revision-specific evidence.
- Annotated expected metadata covers distinct streams/cadences, repeated fields,
  execution differences, and missing data, using additional samples or clearly
  labeled synthetic examples if necessary.
- Requester/maintainer decisions specify names, case aggregation, filtering,
  failure behavior, historical coverage, and initial UI scope.
- Storage/query and UI recommendations are documented with examples and tradeoffs.
- Required source-file coverage is verified across LCRC and NERSC ingestion paths.
- The checklist is updated only when its supporting evidence is available.

## Validation

- Compare copied sample manifests/file inventories to original archive snapshots;
  verify copied file checksums where access permits.
- Manually trace active stream references and check every annotated variable,
  grid, cadence, and averaging value against its source file.
- Cross-check defaults and ambiguous settings against model-revision source or
  documentation; obtain EAMxx expert confirmation where needed.
- Walk through query/UI examples with the requester, including a negative example
  where a field and desired cadence occur in different streams or executions.
- Review actual packaging/discovery code and sample payload inventories for both
  ingestion paths. Record untested operational paths rather than claiming coverage.
- Validate documentation with `git diff --check` and `make pre-commit-run` from
  the repository root. Application tests are not required for documentation-only
  work; later backend implementation must run `make backend-test`.

## Starting evidence and references

Status: discovery has not been executed; archive samples have not been copied.

- [EAMxx model configuration/output documentation](https://github.com/E3SM-Project/E3SM/blob/master/components/eamxx/docs/user/model_configuration.md#model-output)
- [EAMxx buildnml archival entry point](https://github.com/E3SM-Project/E3SM/blob/master/components/eamxx/cime_config/buildnml)
- `docs/architecture/metadata-ingestion.md`: execution/archive ownership and layout.
- `backend/app/features/ingestion/parsers/parser.py`: explicit source-file parsing.
- `backend/app/features/catalog/models.py`: Case/Execution ownership and JSONB.
- `backend/app/features/catalog/schemas.py` and `api.py`: response/filter contracts.
- `backend/app/scripts/ingestion/`: collection, packaging, and known-ID handling.
- `frontend/src/features/catalog/`: case/execution presentation and filtering.

Upstream `master` references provide discovery leads, not proof of the settings
in archived executions. Record revision-specific references during analysis.
