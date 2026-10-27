# Incomplete execution discovery

**Recovered all 1,883 incomplete execution paths**, matching per-case and run-summary totals.

- **Run:** `1f156802-916e-44ce-93c7-1a66e98185bd`; offline dry run with DEBUG logging.
- **Source:** `nersc-archive-ingestor-1793036867985-zfdtd_nersc-archive-ingestor.log`.
- **Coverage:** 1,254 case directories; 990 with no selected executions and 264 with selected siblings. No uploads occurred.
- **Error codes (paths affected):** `missing_required_file`: 1,883.

## Missing artifacts

| Required filename pattern | Paths missing it |
|---|---:|
| `CaseStatus..*.gz` | 1,883 |
| `README.case..*.gz` | 1,883 |
| `env_build.xml..*.gz` | 1,883 |
| `env_case.xml..*.gz` | 1,883 |
| `GIT_DESCRIBE..*.gz` | 1,882 |
| `cpl.log.<execution_id>[.gz]` | 1,882 |
| `e3sm_timing..*..*` | 1,882 |
| `env_run.xml..*` | 716 |

**Missing-artifact combinations:**
- **1,166 paths:** 7 required artifact types missing.
- **716 paths:** 8 required artifact types missing.
- **1 path:** 4 required artifact types missing.

## Largest owner groups

| Owner | Paths |
|---|---:|
| `azamat` | 716 |
| `zhan391` | 524 |
| `beydoun` | 200 |
| `feng809` | 147 |
| `jmuelmen` | 140 |
| Others | 156 |

## Example Perlmutter paths

**ndk — 7 missing artifact types; log line 344:**

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-01/performance_archive_2025_01_04_07_01_01/COMPLETED/ndk/gt.ne30pg2_ne30pg2.F2010-SCREAMv1.c02-dec20.5d.n0001t4x111XX1.nocosp.do.sk.nid001156/34545774.250103-122939
```

**azamat — 8 missing artifact types; log line 15987:**

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-09/performance_archive_2025_09_05_08_00_43/COMPLETED/azamat/SMS.ne30pg2_EC30to60E2r2.WCYCLXX2010.pm-gpu_gnugpu.a1/42473005.250904-163426
```

**wangchen — 4 missing artifact types; log line 9929:**

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-03/performance_archive_2025_03_28_14_14_59/COMPLETED/wangchen/uELM_AKSP_SS_300/37211869.250327-211940
```

**Interpretation:** these are discovery exclusions, not failed uploads. Missing patterns do not prove directories are empty. This parser did not inspect archive contents or determine why metadata is missing.

**Next step:** inspect example directories and compare archived copies before choosing recovery or parser fixes. Do not add overlapping source-directory tracking gaps to this total.
