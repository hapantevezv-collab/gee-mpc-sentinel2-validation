# Part of gee-mpc-sentinel2-validation (https://doi.org/10.5281/zenodo.23241823)
# Author: Heiber Alexander Pantevez Villamil (hapantevezv@unal.edu.co, ORCID 0000-0003-1797-0057), Universidad Nacional de Colombia
# Licence: MIT (see LICENSE)
"""
gee_mpc_s2val.verify (command: gee-mpc-verify-demo)
========================================

Compares a new run of the three tools on the public demonstration AOI with the
reference outputs in data/acceptance/demo/ (the same files as folder
05_demonstration/ of the data archive on Zenodo). CSV files are compared column by
column (numbers with a relative tolerance of 1e-9), JSON files key by key. Fields that
depend on the run time or on local paths are ignored.

Usage
-----
    gee-mpc-verify-demo --ref data/acceptance/demo \\
        --reconciliation demo_reconciliation --e2 demo_e2 --impact demo_impact
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import pandas as pd

IGNORE_KEYS = {"created_utc", "aoi", "reconciliation"}      # run time and local paths


def same_json(x, y) -> bool:
    if isinstance(x, dict) and isinstance(y, dict):
        keys = (set(x) | set(y)) - IGNORE_KEYS
        return all(k in x and k in y and same_json(x[k], y[k]) for k in keys)
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(same_json(u, v) for u, v in zip(x, y))
    if isinstance(x, float) or isinstance(y, float):
        if x is None or y is None:
            return x is None and y is None
        return math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12)
    return x == y


def same_csv(ref: Path, new: Path) -> bool:
    r, n = pd.read_csv(ref), pd.read_csv(new)
    if list(r.columns) != list(n.columns) or r.shape != n.shape:
        return False
    for c in r.columns:
        numeric = (pd.api.types.is_numeric_dtype(r[c]) and pd.api.types.is_numeric_dtype(n[c])
                   and not pd.api.types.is_bool_dtype(r[c]))
        if numeric:
            d = (r[c] - n[c]).abs()
            if not bool(((d <= 1e-9 + 1e-9 * r[c].abs()) | (r[c].isna() & n[c].isna())).all()):
                return False
        elif not bool((r[c].astype(object).where(r[c].notna(), "").astype(str)
                       == n[c].astype(object).where(n[c].notna(), "").astype(str)).all()):
            return False
    return True


def compare(ref: Path, runs: dict[str, Path]) -> list[tuple[str, str]]:
    """Returns (status, relative path) for every reference CSV/JSON file."""
    out = []
    for sub, new_dir in runs.items():
        ref_dir = ref / sub
        for f in sorted(ref_dir.rglob("*")):
            if f.is_dir() or f.suffix not in (".csv", ".json"):
                continue
            rel = f.relative_to(ref_dir)
            g = Path(new_dir) / rel
            if not g.exists():
                out.append(("MISSING", f"{sub}/{rel}"))
                continue
            ok = same_csv(f, g) if f.suffix == ".csv" else same_json(
                json.loads(f.read_text(encoding="utf-8")), json.loads(g.read_text(encoding="utf-8")))
            out.append(("OK" if ok else "DIFF", f"{sub}/{rel}"))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Compare a demo-AOI run with the reference outputs.")
    ap.add_argument("--ref", type=Path, default=Path("data/acceptance/demo"))
    ap.add_argument("--reconciliation", type=Path, required=True)
    ap.add_argument("--e2", type=Path, required=True)
    ap.add_argument("--impact", type=Path, required=True)
    a = ap.parse_args(argv)
    res = compare(a.ref, {"reconciliation": a.reconciliation, "e2": a.e2, "impact": a.impact})
    for status, rel in res:
        print(f"{status:9s} {rel}")
    bad = sum(s != "OK" for s, _ in res)
    print("-" * 60)
    print("RESULT: identical to the reference outputs" if bad == 0
          else f"RESULT: {bad} file(s) differ or are missing")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
