"""End-to-end run against the live catalogues (needs Earth Engine credentials).

Skipped unless the environment variable GEE_PROJECT is set. Catalogue contents change
over time, so a failure here can mean that a catalogue changed, not that the code did.
"""
import os
import subprocess
import sys

import pytest

from gee_mpc_s2val.verify import same_csv

pytestmark = pytest.mark.ee
PROJECT = os.environ.get("GEE_PROJECT")


@pytest.mark.skipif(not PROJECT, reason="set GEE_PROJECT to run tests against Earth Engine")
def test_reconcile_demo_aoi_live(demo_dir, demo_aoi, tmp_path):
    out = tmp_path / "rec"
    subprocess.run([sys.executable, "-m", "gee_mpc_s2val.reconcile", "--aoi", str(demo_aoi),
                    "--start", "2024-06-01", "--end", "2025-04-30", "--gee-project", PROJECT,
                    "--out", str(out)], check=True)
    assert same_csv(demo_dir / "reconciliation" / "scene_reconciliation.csv",
                    out / "scene_reconciliation.csv")
