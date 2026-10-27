# Ambiguous run-script inspection

**All 86 execution directories contain multiple matching provenance scripts: 2–23 per directory.** The warnings are reproducible, not just duplicate gzip/plain copies of one script name.

- **Checked:** October 26, 2026, using `inspect_run_scripts.py` against Perlmutter paths.
- **Source run:** `2a83de38-96f9-4076-8d99-c177fd507f76`; 172 warnings represent 86 distinct paths.
- **Scope:** all paths belong to `njeffery`, across 16 case names. No inspection errors occurred.
- **Counting:** matches SimBoard's provenance filename rules using `CASE` from `env_case.xml`. Physical matching-file counts equal unique provenance-name counts for every inspected path.

| Matching scripts per directory | Execution directories |
|---:|---:|
| 2 | 23 |
| 3 | 16 |
| 4 | 5 |
| 5 | 1 |
| 6 | 12 |
| 7 | 2 |
| 11 | 4 |
| 13 | 3 |
| 16 | 1 |
| 18 | 4 |
| 19 | 11 |
| 23 | 4 |
| **Total** | **86** |

## Example: three matching scripts

```text
/global/cfs/cdirs/e3sm/OLD_PERF/2025-03/performance_archive_2025_03_21_08_00_29/COMPLETED/njeffery/20250319.v3.LR.CBGC.FrazilEcosys.noSpinu.Icepack1.5.0.pm-cpu/37013148.250320-123519
```

Files inside `CaseDocs.37013148.250320-123519/`:

```text
run.20250319.v3.LR.CBGC.FrazilEcosys.noSpinu.Icepack1.5.0.pm-cpu.sh.20250319-111614.37013148.250320-123519.gz
run.20250319.v3.LR.CBGC.FrazilEcosys.noSpinu.Icepack1.5.0.pm-cpu.sh.20250319-112114.37013148.250320-123519.gz
run.20250319.v3.LR.CBGC.FrazilEcosys.noSpinu.Icepack1.5.0.pm-cpu.sh.20250319-113750.37013148.250320-123519.gz
```

**Impact:** SimBoard omits the ambiguous run-script artifact rather than guessing. This warning does not fail execution ingestion.

**Next step:** establish which script belongs to each execution before changing selection behavior. This inspection did not compare script contents or establish why multiple versions were archived. Archive files and ingestion state were unchanged.
