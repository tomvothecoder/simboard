"""Replay all saved compset validation failures from Perlmutter to verify PR #428.

Matches historical "compset" and current "compset_long_name" field errors,
including secondary errors. Uses the same upload, preview, and logging options
as verify_year_zero.py. No requests occur without --apply.

Run from the repository root:

    uv run --project backend python docs/github-issues/401-stale-discovery-recovery/2-false-success/4-verify-fixes/verify_compset.py --apply --log compset-all.jsonl
"""

from __future__ import annotations

from verify_year_zero import main as _verify_group


def main(argv: list[str] | None = None) -> int:
    return _verify_group(argv, group="compset_long_name")


if __name__ == "__main__":
    raise SystemExit(main())
