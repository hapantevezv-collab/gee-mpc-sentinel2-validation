"""E2 stratification from a reconciliation table."""
import pandas as pd

from gee_mpc_s2val.e2 import prepare, stratify


def test_difference_types(tmp_path):
    t = pd.DataFrame({
        "key": ["a", "b", "c", "d"], "state": ["BOTH", "BOTH", "BOTH", "GEE_ONLY"],
        "identity": ["E1", "E2", "E2", None],
        "sensing_utc": ["2024-06-01T15:30:00Z"] * 4, "month": ["2024-06"] * 4,
        "baseline_gee": [5.10, 5.10, 4.00, 5.11], "baseline_mpc": [5.10, 5.10, 5.00, None],
        "generation_gee": ["2024-06-01T20:00:00Z"] * 4, "generation_mpc": ["2024-06-02T20:00:00Z"] * 4,
    })
    p = tmp_path / "r.csv"
    t.to_csv(p, index=False)
    both = prepare(p)
    assert len(both) == 3                                   # GEE_ONLY excluded
    assert list(both["difference_type"]) == ["IDENTICAL", "SAME_BASELINE_OTHER_GENERATION", "DIFFERENT_BASELINE"]
    assert list(both["baseline_pair"])[2] == "04.00 → 05.00"
    assert both["generation_lag_h"].iloc[1] == 24.0
    s = stratify(both, "month").iloc[0]
    assert (s["acquisitions"], s["e2"]) == (3, 2)
