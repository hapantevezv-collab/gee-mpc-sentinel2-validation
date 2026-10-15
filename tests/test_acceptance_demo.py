"""Acceptance on the public demonstration AOI, offline.

The reference outputs in data/acceptance/demo/ come from a full run on 2026-10-08
(the same files as folder 05_demonstration/ of the Zenodo data archive). These tests
recompute everything that does not need network access from the published scene lists
and check the reference values and their SHA-256 hashes.
"""
import hashlib
import json

import pandas as pd

from gee_mpc_s2val.e2 import prepare, stratify
from gee_mpc_s2val.reconcile import reconcile, summarise
from gee_mpc_s2val.verify import same_csv


def load_scenes(path):
    df = pd.read_csv(path)
    df["sensing_utc"] = pd.to_datetime(df["sensing_utc"], utc=True, format="mixed")
    df["generation"] = pd.to_datetime(df["generation"], utc=True, format="mixed")
    return df


def test_sha256_of_reference_outputs(demo_dir):
    lines = (demo_dir / "SHA256SUMS.txt").read_text().splitlines()
    assert len(lines) > 30
    for line in lines:
        digest, rel = line.split(maxsplit=1)
        assert hashlib.sha256((demo_dir / rel).read_bytes()).hexdigest() == digest, rel


def test_reconciliation_is_reproduced_from_scene_lists(demo_dir, tmp_path):
    r = demo_dir / "reconciliation"
    t = reconcile(load_scenes(r / "scenes_gee.csv"), load_scenes(r / "scenes_mpc.csv"))
    t.to_csv(tmp_path / "scene_reconciliation.csv", index=False)
    assert same_csv(r / "scene_reconciliation.csv", tmp_path / "scene_reconciliation.csv")
    for by in ("month", "year", "platform", "tile"):
        summarise(t, by).to_csv(tmp_path / f"summary_by_{by}.csv", index=False)
        assert same_csv(r / f"summary_by_{by}.csv", tmp_path / f"summary_by_{by}.csv"), by


def test_acceptance_values(demo_dir):
    exp = json.loads((demo_dir / "acceptance_demo.json").read_text())
    t = pd.read_csv(demo_dir / "reconciliation" / "scene_reconciliation.csv")
    counts = t["state"].value_counts().to_dict()
    rec = exp["reconciliation"]
    assert len(t) == rec["acquisitions"] == 146
    assert counts.get("BOTH", 0) == rec["BOTH"] == 136
    assert counts.get("GEE_ONLY", 0) == rec["GEE_ONLY"] == 10
    assert counts.get("MPC_ONLY", 0) == rec["MPC_ONLY"] == 0
    assert (t["identity"] == "E2").sum() == rec["E2"] == 22

    m = pd.read_csv(demo_dir / "impact" / "monthly_metrics.csv")
    v = m[(m.a == "GEE") & (m.b == "COMMON") & (m["index"] == "NDVI")].set_index("month")
    for row in exp["monthly_ndvi_gee_minus_common"]:
        got = v.loc[row["month"]]
        assert round(got["bias_a_minus_b"], 4) == row["bias"]
        assert round(got["mae"], 4) == row["mae"]
        assert (got["scenes_b"], got["scenes_a"]) == (row["records_common"], row["records_gee"])


def test_e2_strata_are_reproduced(demo_dir, tmp_path):
    both = prepare(demo_dir / "reconciliation" / "scene_reconciliation.csv")
    for by in ("month", "year", "platform", "tile", "baseline_pair", "difference_type"):
        stratify(both, by).to_csv(tmp_path / f"e2_by_{by}.csv", index=False)
        assert same_csv(demo_dir / "e2" / f"e2_by_{by}.csv", tmp_path / f"e2_by_{by}.csv"), by
    both[both["is_e2"]].to_csv(tmp_path / "e2_pairs.csv", index=False)
    ref = pd.read_csv(demo_dir / "e2" / "e2_pairs.csv")
    assert list(pd.read_csv(tmp_path / "e2_pairs.csv")["key"]) == list(ref["key"])
