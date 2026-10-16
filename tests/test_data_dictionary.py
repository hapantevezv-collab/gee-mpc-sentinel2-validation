"""Every column of the reference outputs is described in docs/data_dictionary.csv."""
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "acceptance" / "demo"
INHERITS = {"e2_pairs.csv": "scene_reconciliation.csv"}


def documented() -> dict[str, set[str]]:
    d = pd.read_csv(ROOT / "docs" / "data_dictionary.csv")
    out: dict[str, set[str]] = {}
    for table, column in zip(d["table"], d["column"]):
        names = {c.strip() for c in re.split(r"[,|]", column) if c.strip()}
        for t in (x.strip() for x in table.split(",")):
            out.setdefault(t, set()).update(names)
    return out


def test_dictionary_covers_reference_csvs():
    doc = documented()
    missing = []
    for f in sorted(DEMO.rglob("*.csv")):
        cols = set(pd.read_csv(f, nrows=0).columns)
        known = doc.get(f.name, set()) | doc.get(INHERITS.get(f.name, ""), set())
        missing += [f"{f.name}:{c}" for c in sorted(cols - known)]
    assert not missing, f"Columns without a description: {missing}"
