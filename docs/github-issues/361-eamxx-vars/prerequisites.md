# Issue 361: EAMxx Variable Metadata Prerequisites

Simplified replacement for the prerequisites in
[#361](https://github.com/E3SM-Project/simboard/issues/361). These tasks prepare
an implementation plan; they do not implement the feature. All remain open.

- [ ] Copy example EAMxx execution snapshots from the LCRC performance archive
      into a local home-directory workspace. Keep complete `CaseDocs` and record
      each case, execution ID, model revision, and original archive path.
- [ ] Identify the archived files that define active EAMxx output streams.
      Inspect `atm_in` if present, but also inspect EAMxx configuration and
      referenced output YAML files; do not assume EAM namelist settings apply.
- [ ] Verify the settings for requested fields, output frequency and units,
      averaging type, and stream/grid identity. Distinguish output cadence from
      file packaging.
- [ ] Define the metadata to extract and manually annotate expected results for
      the samples. Include multiple streams and missing/unresolved metadata.
- [ ] Agree on execution-level storage, case-level summaries, and variable
      filtering semantics. Compare storage options against those queries.
- [ ] Agree on case/execution UI presentation and initial filtering scope.
- [ ] Verify that collection preserves the required files, and decide how to
      handle missing metadata and previously ingested executions.

## Starting Cases

Use the cases listed in the issue to locate execution snapshots:

- [Kai Zhang: def_nmono3](https://simboard-dev.e3sm.org/cases/chrysalis/ac.kai.zhang/F2010-EAMxx-MAM4xx_ne30pg2_ne30pg2_L72_20260911_c590707_def_nmono3)
- [Oscar Diaz: mamxx_susannah](https://simboard-dev.e3sm.org/cases/chrysalis/ac.odiazib/F2010-EAMxx-MAM4xx_ne30pg2_ne30pg2_L72_mamxx_susannah)
- [Oscar Diaz: master](https://simboard-dev.e3sm.org/cases/chrysalis/ac.odiazib/F2010-EAMxx-MAM4xx_ne30pg2_ne30pg2_L72_master)

Add contrasting executions if these examples do not cover different output
streams, frequencies, or configuration changes.

See [the prerequisite discovery plan](plan.md) for steps and completion evidence.
