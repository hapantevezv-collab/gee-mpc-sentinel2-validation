#!/usr/bin/env python3
"""Compatibility wrapper for the v1.0.0 command: python scripts/e2_frequency.py ...
Equivalent to the installed command gee-mpc-e2 (see README)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from gee_mpc_s2val.e2 import main  # noqa: E402

if __name__ == "__main__":
    main()
