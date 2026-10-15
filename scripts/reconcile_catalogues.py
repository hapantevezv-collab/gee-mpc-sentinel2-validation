#!/usr/bin/env python3
"""Compatibility wrapper for the v1.0.0 command: python scripts/reconcile_catalogues.py ...
Equivalent to the installed command gee-mpc-reconcile (see README)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from gee_mpc_s2val.reconcile import main  # noqa: E402

if __name__ == "__main__":
    main()
