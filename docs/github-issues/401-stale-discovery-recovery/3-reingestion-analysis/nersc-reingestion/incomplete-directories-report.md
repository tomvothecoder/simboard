# Direct inspection of incomplete execution directories

**Inspected 1,883 distinct execution paths from the DEBUG log.**

- **Inspection started (UTC):** `2026-10-26T20:44:17+00:00`.
- **Source run:** `1f156802-916e-44ce-93c7-1a66e98185bd`.
- **Method:** read-only filesystem checks using `check_incomplete_directories.py`.

| Current finding | Paths |
|---|---:|
| `incomplete` | 1,503 |
| `empty` | 380 |

**Missing-artifact comparison:** 1,883 match the log; 0 differ; 0 could not be checked.

## Owner breakdown

| Owner | Current finding | Paths |
|---|---|---:|
| `zhan391` | `incomplete` | 524 |
| `azamat` | `empty` | 380 |
| `azamat` | `incomplete` | 336 |
| `beydoun` | `incomplete` | 200 |
| `feng809` | `incomplete` | 147 |
| `jmuelmen` | `incomplete` | 140 |
| Others | Combined | 156 |

## Example paths

**ndk: `incomplete`, 5 entries; log line 344.**

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-01/performance_archive_2025_01_04_07_01_01/COMPLETED/ndk/gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001156/34545774.250103-122939
```

**wangchen: `incomplete`, 25 entries; log line 9929.**

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-03/performance_archive_2025_03_28_14_14_59/COMPLETED/wangchen/uELM_AKSP_SS_300/37211869.250327-211940
```

**azamat: `incomplete`, 2 entries; log line 15987.**

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-09/performance_archive_2025_09_05_08_00_43/COMPLETED/azamat/SMS.ne30pg2_EC30to60E2r2.WCYCLXX2010.pm-gpu_gnugpu.a1/42473005.250904-163426
```

**azamat: `empty`, 0 entries; log line 30720.**

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2026-07/performance_archive_2026_07_15_10_55_30/COMPLETED/azamat/SMS.ne30pg2_EC30to60E2r2.WCYCLXX2010.pm-gpu_gnugpu.a1/42510405.250905-114948
```

**Limits:** `empty` means zero directory entries, including hidden entries. A directory containing an empty subdirectory is not empty. Checks cover required filename matches and readable nonempty files, not gzip integrity or metadata values. Why artifacts are missing remains unconfirmed.

**Next step:** inspect collection/cleanup history and locate complete copies. No archive files, database records, or ingestion state were changed. These paths overlap source-directory tracking gaps; do not add those counts.
