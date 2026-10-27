# Source-directory validation results

Checked on **2026-10-26 UTC** using `validate_source_directories.py`, with default log and Perlmutter archive root. Source ingestion run: `2a83de38-96f9-4076-8d99-c177fd507f76`.

**All 381 paths were inspected: 380 are completely empty; one contains files but lacks required artifacts.**

| Owner | Paths | Execution IDs | Finding |
|---|---:|---:|---|
| `azamat` | 380 | 5 | Every directory has zero entries, including no hidden entries or subdirectories. Each execution ID appears in 76 snapshots. |
| `wangchen` | 1 | 1 | Directory has 25 entries, but lacks required `env_case.xml`, `env_build.xml`, `README.case`, and `CaseStatus` filename matches. |

No missing execution directories, access errors, duplicate required-file matches, or unreadable/zero-byte matching files were reported. No path passed all required-file checks. Exit code **1** indicates findings, not a script crash.

## Representative paths

Empty (`azamat`):

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2026-10/performance_archive_2026_10_10_10_02_38/COMPLETED/azamat/SMS.ne30pg2_EC30to60E2r2.WCYCLXX2010.pm-gpu_gnugpu.a1/42510405.250905-114948
```

Nonempty but incomplete (`wangchen`):

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-03/performance_archive_2025_03_28_14_14_59/COMPLETED/wangchen/uELM_AKSP_SS_300/37211869.250327-211940
```

## Next steps

- [ ] Determine why empty execution directories recur across archive snapshots; inspect PACE collection/cleanup history.
- [ ] Locate complete copies or restore missing artifacts where available.

These current filesystem findings explain the missing-file tracking errors, but do not establish when or why files disappeared. Checks were read-only and did not parse metadata contents or change ingestion state. Counts overlap the incomplete-directory population; do not add them to that total.
