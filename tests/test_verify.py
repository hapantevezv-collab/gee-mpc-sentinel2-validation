"""The demo verifier must flag a changed value and a missing file."""
import shutil

import pandas as pd

from gee_mpc_s2val.verify import compare


def test_verifier_detects_changes(demo_dir, tmp_path):
    runs = {}
    for sub in ("reconciliation", "e2", "impact"):
        shutil.copytree(demo_dir / sub, tmp_path / sub)
        runs[sub] = tmp_path / sub
    assert all(s == "OK" for s, _ in compare(demo_dir, runs))

    m = pd.read_csv(tmp_path / "impact" / "monthly_metrics.csv")
    m.loc[0, "mae"] += 1e-4
    m.to_csv(tmp_path / "impact" / "monthly_metrics.csv", index=False)
    (tmp_path / "e2" / "e2_scl.csv").unlink()
    status = dict((rel, s) for s, rel in compare(demo_dir, runs))
    assert status["impact/monthly_metrics.csv"] == "DIFF"
    assert status["e2/e2_scl.csv"] == "MISSING"
