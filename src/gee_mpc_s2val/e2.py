# Part of gee-mpc-sentinel2-validation (https://doi.org/10.5281/zenodo.23241823)
# Author: Heiber Alexander Pantevez Villamil (hapantevezv@unal.edu.co, ORCID 0000-0003-1797-0057), Universidad Nacional de Colombia
# Licence: MIT (see LICENSE)
"""
gee_mpc_s2val.e2 (command: gee-mpc-e2)
========================================

Estimates how often GEE and MPC serve different L2A generations of the same
Sentinel-2 acquisition (E2 cases), where they concentrate and, optionally, how
much the cloud mask (SCL) changes between the two generations.

Why it exists
-------------
Pairing scenes by date or datatake does not guarantee that both catalogues
hold the same product. ESA reprocesses acquisitions (new baselines,
Collection-1) and each catalogue may keep a different generation. In the pilot
case, one of 11 acquisitions was E2 and the two generations disagreed on the
validity of hundreds of farm pixels; all the disagreement came from the SCL,
not from the masks of the spectral bands.

Input
-----
scene_reconciliation.csv written by gee-mpc-reconcile.

What it does
------------
1. Metadata only (always): among BOTH acquisitions, computes the E2 share and
   stratifies it by month, year, platform, tile, baseline pair and difference type:
     SAME_BASELINE_OTHER_GENERATION  (reprocessed with the same baseline)
     DIFFERENT_BASELINE              (e.g. 04.00 versus 05.00)
2. With --measure-scl (optional): for each E2 pair, downloads the SCL from both
   catalogues on the native 20 m grid (no resampling) over the AOI and
   measures class agreement and validity Jaccard.

Usage
-----
    gee-mpc-e2 --reconciliation reconciliation/scene_reconciliation.csv \\
        --out e2

    gee-mpc-e2 --reconciliation reconciliation/scene_reconciliation.csv \\
        --measure-scl --aoi aoi.geojson --gee-project MY_PROJECT --out e2

Outputs (in --out)
------------------
    e2_pairs.csv                 detail of each E2 record
    e2_by_<stratum>.csv          shares by month, year, platform, tile,
                                 baseline pair and difference type
    e2_scl.csv                   (with --measure-scl) SCL agreement per pair
    e2_summary.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import pandas as pd

VALID_SCL_DEFAULT = "2,4,5,6,7"


# ------------------------------------------------------- part 1: metadata

def prepare(path: Path) -> pd.DataFrame:
    t = pd.read_csv(path)
    for col in ("sensing_utc", "generation_gee", "generation_mpc"):
        # Formats differ by catalogue (ms, ISO with or without fraction): normalised to UTC.
        t[col] = pd.to_datetime(t[col], utc=True, errors="coerce", format="mixed")
    both = t[t["state"] == "BOTH"].copy()
    if both.empty:
        sys.exit("No acquisition is present in both catalogues: E2 cannot be estimated.")
    both["is_e2"] = both["identity"] == "E2"
    both["baseline_pair"] = (both["baseline_gee"].map(lambda v: f"{v:05.2f}" if pd.notna(v) else "?")
                             + " → " +
                             both["baseline_mpc"].map(lambda v: f"{v:05.2f}" if pd.notna(v) else "?"))
    both["difference_type"] = np.where(
        ~both["is_e2"], "IDENTICAL",
        np.where(both["baseline_gee"] == both["baseline_mpc"],
                 "SAME_BASELINE_OTHER_GENERATION", "DIFFERENT_BASELINE"))
    both["generation_lag_h"] = (
        (both["generation_mpc"] - both["generation_gee"]).dt.total_seconds() / 3600)
    return both


def stratify(both: pd.DataFrame, by: str) -> pd.DataFrame:
    g = both.groupby(by).agg(acquisitions=("key", "count"), e2=("is_e2", "sum"))
    g["fraction_e2"] = g["e2"] / g["acquisitions"]
    return g.reset_index().sort_values(by)


# --------------------------------------------------- part 2: SCL per pair

def measure_scl(pairs: pd.DataFrame, aoi_path: Path, gee_project: str,
                valid: set[int], limit: int | None) -> pd.DataFrame:
    """Compares the SCL of both generations on the native 20 m grid of the MPC item."""
    import ee
    import geopandas as gpd
    import planetary_computer
    from pystac_client import Client
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window
    import requests
    from shapely.geometry import mapping

    ee.Initialize(project=gee_project)
    client = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    aoi = gpd.read_file(aoi_path)
    rows = []
    selection = pairs if limit is None else pairs.head(limit)
    for i, pair in enumerate(selection.itertuples(index=False), start=1):
        asset = str(pair.ids_gee).split("|")[0]
        item_id = str(pair.ids_mpc).split("|")[0]
        item = next(client.search(collections=["sentinel-2-l2a"], ids=[item_id]).items())
        href = planetary_computer.sign(item).assets["SCL"].href
        with rasterio.open(href) as src:
            geom = aoi.to_crs(src.crs).geometry.union_all()
            minx, miny, maxx, maxy = geom.buffer(40).bounds
            T = src.transform
            col0 = int(np.floor((minx - T.c) / T.a))
            col1 = int(np.ceil((maxx - T.c) / T.a))
            row0 = int(np.floor((T.f - maxy) / -T.e))
            row1 = int(np.ceil((T.f - miny) / -T.e))
            window = Window(col0, row0, col1 - col0, row1 - row0)
            scl_mpc = src.read(1, window=window)
            transform = src.window_transform(window)
            epsg = src.crs.to_epsg()
            crs_ee = f"EPSG:{epsg}" if epsg else src.crs.to_wkt()
        height, width = scl_mpc.shape
        inside = geometry_mask([mapping(geom)], out_shape=(height, width),
                               transform=transform, invert=True)

        # GEE SCL on the same native 20 m lattice (no resampling). A region with a
        # 2-pixel margin is requested and the exact window is then cropped locally,
        # because GEE may shift the edge of the requested region by one or two pixels.
        margin = 40
        region = ee.Geometry.Rectangle(
            [transform.c - margin, transform.f - 20 * height - margin,
             transform.c + 20 * width + margin, transform.f + margin],
            proj=ee.Projection(crs_ee), geodesic=False)
        url = ee.Image(asset).select("SCL").unmask(0).toUint8().getDownloadURL({
            "region": region, "crs": crs_ee,
            "crs_transform": [20, 0, transform.c, 0, -20, transform.f], "format": "GEO_TIFF"})
        with tempfile.NamedTemporaryFile(suffix=".tif") as tmp:
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            tmp.write(r.content)
            tmp.flush()
            with rasterio.open(tmp.name) as g:
                gt = g.transform
                dc, dr = (transform.c - gt.c) / 20, (gt.f - transform.f) / 20
                same_lattice = (abs(gt.a - 20) < 1e-6 and abs(gt.e + 20) < 1e-6
                                and abs(dc - round(dc)) < 1e-6 and abs(dr - round(dr)) < 1e-6)
                c0, r0 = int(round(dc)), int(round(dr))
                if not same_lattice or c0 < 0 or r0 < 0 or c0 + width > g.width or r0 + height > g.height:
                    raise RuntimeError(
                        f"{asset}: the GEE download is not on the native MPC lattice.\n"
                        f"  MPC: {tuple(transform)[:6]} {width}x{height}\n"
                        f"  GEE: {tuple(gt)[:6]} {g.width}x{g.height}")
                scl_gee = g.read(1)[r0:r0 + height, c0:c0 + width]

        a, b = scl_gee[inside], scl_mpc[inside]
        va, vb = np.isin(a, list(valid)), np.isin(b, list(valid))
        union = np.count_nonzero(va | vb)
        changes = pd.Series(list(zip(a[a != b], b[a != b]))).value_counts().head(3)
        rows.append({
            "key": pair.key, "sensing_utc": pair.sensing_utc, "tile": pair.tile,
            "gee_asset": asset, "mpc_item": item_id,
            "aoi_pixels_20m": int(inside.sum()),
            "scl_class_agreement": float((a == b).mean()),
            "valid_gee": int(va.sum()), "valid_mpc": int(vb.sum()),
            "valid_only_gee": int((va & ~vb).sum()), "valid_only_mpc": int((~va & vb).sum()),
            "validity_jaccard": float(np.count_nonzero(va & vb) / union) if union else None,
            "frequent_scl_transitions_gee_to_mpc": "; ".join(f"{x}->{y}:{n}" for (x, y), n in changes.items()),
        })
        print(f"  [{i}/{len(selection)}] {pair.key} | SCL agreement={rows[-1]['scl_class_agreement']:.3f} | "
              f"validity Jaccard={rows[-1]['validity_jaccard']}")
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="Frequency and effect of different L2A generations (E2).")
    ap.add_argument("--reconciliation", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("e2"))
    ap.add_argument("--measure-scl", action="store_true", help="Compare the SCL of each E2 pair (downloads).")
    ap.add_argument("--aoi", type=Path, help="Required with --measure-scl.")
    ap.add_argument("--gee-project", help="Required with --measure-scl.")
    ap.add_argument("--valid-scl", default=VALID_SCL_DEFAULT,
                    help=f"Valid SCL classes, comma-separated (default {VALID_SCL_DEFAULT}).")
    ap.add_argument("--max-pairs", type=int, help="Limit how many E2 pairs are measured.")
    a = ap.parse_args()
    if a.measure_scl and not (a.aoi and a.gee_project):
        sys.exit("--measure-scl requires --aoi and --gee-project.")
    a.out.mkdir(parents=True, exist_ok=True)

    both = prepare(a.reconciliation)
    pairs = both[both["is_e2"]].copy()
    pairs.to_csv(a.out / "e2_pairs.csv", index=False)
    for stratum in ("month", "year", "platform", "tile", "baseline_pair", "difference_type"):
        stratify(both, stratum).to_csv(a.out / f"e2_by_{stratum}.csv", index=False)

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reconciliation": str(a.reconciliation),
        "acquisitions_in_both": int(len(both)),
        "e2": int(len(pairs)),
        "fraction_e2": float(len(pairs) / len(both)),
        "e2_by_type": pairs["difference_type"].value_counts().to_dict(),
        "median_generation_lag_h": (float(pairs["generation_lag_h"].median())
                                    if len(pairs) else None),
    }
    print(f"BOTH={len(both)} | E2={len(pairs)} ({summary['fraction_e2']:.1%})")
    for kind, n in summary["e2_by_type"].items():
        print(f"  {kind}: {n}")

    if a.measure_scl and len(pairs):
        valid = {int(v) for v in a.valid_scl.split(",")}
        print(f"Measuring SCL in {len(pairs) if a.max_pairs is None else min(a.max_pairs, len(pairs))} E2 pairs ...")
        scl = measure_scl(pairs, a.aoi, a.gee_project, valid, a.max_pairs)
        scl.to_csv(a.out / "e2_scl.csv", index=False)
        summary["scl"] = {
            "pairs_measured": int(len(scl)),
            "median_scl_class_agreement": float(scl["scl_class_agreement"].median()),
            "median_validity_jaccard": float(scl["validity_jaccard"].median()),
            "valid_scl_classes": sorted(valid),
        }

    (a.out / "e2_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False,
                                                      default=str) + "\n", encoding="utf-8")
    print(f"Outputs in: {a.out.resolve()}")


if __name__ == "__main__":
    main()
