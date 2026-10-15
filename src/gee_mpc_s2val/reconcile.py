# Part of gee-mpc-sentinel2-validation (https://doi.org/10.5281/zenodo.23241823)
# Author: Heiber Alexander Pantevez Villamil (hapantevezv@unal.edu.co, ORCID 0000-0003-1797-0057), Universidad Nacional de Colombia
# Licence: MIT (see LICENSE)
"""
gee_mpc_s2val.reconcile (command: gee-mpc-reconcile)
========================================

Reconciles the Sentinel-2 L2A catalogues of Google Earth Engine (GEE) and
Microsoft Planetary Computer (MPC) over an area of interest (AOI) and a period.

Why it exists
-------------
Before GEE and MPC are combined in one series, one must know whether both
catalogues hold the same acquisitions and the same products. In the pilot case
that motivated this code, GEE held Sentinel-2C acquisitions that MPC did not,
and pairing by identifiers dropped them silently. The result was an NDVI
difference that looked like a platform effect and actually came from the
scene universe.

What it does
------------
1. Lists in GEE (COPERNICUS/S2_SR_HARMONIZED) and in MPC (sentinel-2-l2a) every
   scene whose footprint intersects the AOI in the period.
2. Matches both lists by acquisition = datatake (without baseline suffix)
   + MGRS tile. Never by string matching of identifiers.
3. Labels each acquisition:
     BOTH       present in both catalogues
     GEE_ONLY   only in GEE
     MPC_ONLY   only in MPC
   and, for BOTH, the product identity:
     E1         same product_id (same L2A generation)
     E2         same acquisition, different L2A generation
4. Summarises by month, year, platform (S2A/S2B/S2C) and tile.

No scene is dropped silently: everything found in a catalogue stays in the
reconciliation table with its state.

Usage
-----
    gee-mpc-reconcile --aoi aoi.geojson --start 2024-01-01 \\
        --end 2025-06-30 --gee-project MY_PROJECT --out reconciliation

Outputs (in --out)
------------------
    scenes_gee.csv               raw GEE listing
    scenes_mpc.csv               raw MPC listing
    scene_reconciliation.csv     one row per acquisition (input of
                                 gee-mpc-e2 and gee-mpc-impact)
    summary_by_month.csv, summary_by_year.csv,
    summary_by_platform.csv, summary_by_tile.csv
    summary.json                 parameters, counts and versions

Requirements: earthengine-api, pystac-client, geopandas, shapely, pandas.
GEE authentication beforehand: `earthengine authenticate`.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys

import ee
import geopandas as gpd
import pandas as pd
from pystac_client import Client
import shapely
from shapely.geometry import mapping, shape

GEE_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
MPC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
MPC_COLLECTION = "sentinel-2-l2a"

GEE_PROPS = [
    "PRODUCT_ID", "DATATAKE_IDENTIFIER", "MGRS_TILE", "SPACECRAFT_NAME",
    "SENSING_ORBIT_NUMBER", "PROCESSING_BASELINE", "GENERATION_TIME",
    "CLOUDY_PIXEL_PERCENTAGE",
]


# ---------------------------------------------------------------- utilities

def read_aoi(path: Path) -> shapely.Geometry:
    """Reads the AOI (GeoJSON, shapefile, GPKG) as one 2D geometry in EPSG:4326."""
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"{path}: the AOI has no geometries.")
    if gdf.crs is None:
        raise ValueError(f"{path}: the AOI declares no coordinate reference system.")
    geom = gdf.to_crs(4326).geometry.union_all()
    geom = shapely.force_2d(shapely.make_valid(geom))
    if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"{path}: a polygon was expected; got {geom.geom_type}.")
    return geom


def aoi_to_ee(geom: shapely.Geometry) -> ee.Geometry:
    """Clean GeoJSON (lists, 2D) for Earth Engine."""
    return ee.Geometry(json.loads(json.dumps(mapping(geom))))


def platform(value: str | None) -> str | None:
    """'Sentinel-2A' / 'sentinel-2c' / 'S2B' -> 'S2A' / 'S2C' / 'S2B'."""
    if not value:
        return None
    m = re.search(r"2\s*([ABCD])", str(value).upper())
    return f"S2{m.group(1)}" if m else str(value)


def datatake_core(value: str | None) -> str | None:
    """'GS2B_20240601T152659_037803_N05.10' -> 'GS2B_20240601T152659_037803'.

    The _Nxx.xx suffix is the processing baseline: it is removed so that two
    L2A generations of the same acquisition share a key.
    """
    if not value:
        return None
    return re.sub(r"_N\d{2}\.\d{2}$", "", str(value).strip())


def tile(value: str | None) -> str | None:
    return str(value).upper().removeprefix("T") if value else None


def product(value: str | None) -> str | None:
    return str(value).removesuffix(".SAFE") if value else None


def baseline(value) -> float | None:
    try:
        return float(str(value).replace("N", ""))
    except (TypeError, ValueError):
        return None


# -------------------------------------------------------------- GEE catalogue

def list_gee(aoi: ee.Geometry, start: date, end: date) -> pd.DataFrame:
    end_excl = (end + timedelta(days=1)).isoformat()
    col = (ee.ImageCollection(GEE_COLLECTION)
           .filterBounds(aoi).filterDate(start.isoformat(), end_excl))
    aoi_area = aoi.area(10)

    def to_feature(img):
        coverage = img.geometry().intersection(aoi, ee.ErrorMargin(10)).area(10).divide(aoi_area)
        return ee.Feature(None, img.toDictionary().select(GEE_PROPS, True)
                          .set("asset_id", ee.String(GEE_COLLECTION + "/").cat(img.get("system:index")))
                          .set("time_start", img.get("system:time_start"))
                          .set("aoi_coverage", coverage))

    fc = ee.FeatureCollection(col.map(to_feature))
    n = int(col.size().getInfo())
    rows = []
    for offset in range(0, n, 500):
        for f in fc.toList(500, offset).getInfo():
            rows.append(f["properties"])
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for prop in GEE_PROPS:              # properties absent from the whole batch
        if prop not in df:
            df[prop] = None
    df["sensing_utc"] = pd.to_datetime(df["time_start"], unit="ms", utc=True)
    df["platform"] = df["SPACECRAFT_NAME"].map(platform)
    df["tile"] = df["MGRS_TILE"].map(tile)
    df["datatake"] = df["DATATAKE_IDENTIFIER"].map(datatake_core)
    df["product"] = df["PRODUCT_ID"].map(product)
    df["baseline"] = df["PROCESSING_BASELINE"].map(baseline)
    df["generation"] = pd.to_datetime(pd.to_numeric(df["GENERATION_TIME"], errors="coerce"),
                                      unit="ms", utc=True, errors="coerce")
    df["cloud_cover"] = pd.to_numeric(df["CLOUDY_PIXEL_PERCENTAGE"], errors="coerce")
    return df


# -------------------------------------------------------------- MPC catalogue

def list_mpc(aoi_geom: shapely.Geometry, start: date, end: date) -> pd.DataFrame:
    client = Client.open(MPC_STAC)
    search = client.search(
        collections=[MPC_COLLECTION], intersects=mapping(aoi_geom),
        datetime=f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
    )
    rows = []
    for item in search.items():
        p = item.properties
        footprint = shape(item.geometry)
        rows.append({
            "item_id": item.id,
            "sensing_utc": item.datetime,
            "platform": platform(p.get("platform")),
            "tile": tile(p.get("s2:mgrs_tile")),
            "datatake": datatake_core(p.get("s2:datatake_id")),
            "product": product(p.get("s2:product_uri")),
            "baseline": baseline(p.get("s2:processing_baseline")),
            "generation": pd.to_datetime(p.get("s2:generation_time"), utc=True, errors="coerce"),
            "cloud_cover": p.get("eo:cloud_cover"),
            "relative_orbit": p.get("sat:relative_orbit"),
            # Ratio in degrees; enough to tell full coverage from an edge.
            "aoi_coverage": footprint.intersection(aoi_geom).area / aoi_geom.area,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["sensing_utc"] = pd.to_datetime(df["sensing_utc"], utc=True)
    return df


# ------------------------------------------------------------- reconciliation

def acquisition_key(df: pd.DataFrame) -> pd.Series:
    """datatake + tile; if the datatake is missing, platform + sensing time (s) + tile."""
    fallback = (df["platform"].fillna("S2?") + "_"
                + df["sensing_utc"].dt.strftime("%Y%m%dT%H%M%S"))
    return df["datatake"].fillna(fallback) + "|" + df["tile"].fillna("?")


def group(df: pd.DataFrame, suffix: str, id_col: str) -> pd.DataFrame:
    """One row per acquisition and catalogue; keeps every generation."""
    def join(s):
        return "|".join(sorted({str(v) for v in s.dropna()}))
    g = df.groupby("key").agg(
        sensing_utc=("sensing_utc", "min"),
        platform=("platform", "first"),
        tile=("tile", "first"),
        ids=(id_col, join),
        products=("product", join),
        n_products=("product", "nunique"),
        baseline=("baseline", "max"),
        generation=("generation", "max"),
        cloud_cover=("cloud_cover", "min"),
        aoi_coverage=("aoi_coverage", "max"),
    )
    return g.add_suffix(f"_{suffix}")


def reconcile(gee: pd.DataFrame, mpc: pd.DataFrame) -> pd.DataFrame:
    gee = gee.assign(key=acquisition_key(gee))
    mpc = mpc.assign(key=acquisition_key(mpc))
    t = group(gee, "gee", "asset_id").join(group(mpc, "mpc", "item_id"), how="outer")
    t = t.reset_index()

    in_gee = t["ids_gee"].notna() & (t["ids_gee"] != "")
    in_mpc = t["ids_mpc"].notna() & (t["ids_mpc"] != "")
    t["state"] = "BOTH"
    t.loc[in_gee & ~in_mpc, "state"] = "GEE_ONLY"
    t.loc[~in_gee & in_mpc, "state"] = "MPC_ONLY"

    def identity(row):
        if row["state"] != "BOTH":
            return None
        a = set(str(row["products_gee"]).split("|"))
        b = set(str(row["products_mpc"]).split("|"))
        return "E1" if a & b else "E2"

    t["identity"] = t.apply(identity, axis=1)
    t["multiple_generations"] = (t["n_products_gee"].fillna(0) > 1) | (t["n_products_mpc"].fillna(0) > 1)
    t["sensing_utc"] = t["sensing_utc_gee"].fillna(t["sensing_utc_mpc"])
    t["platform"] = t["platform_gee"].fillna(t["platform_mpc"])
    t["tile"] = t["tile_gee"].fillna(t["tile_mpc"])
    t["month"] = t["sensing_utc"].dt.strftime("%Y-%m")
    t["year"] = t["sensing_utc"].dt.year
    t["aoi_coverage"] = t[["aoi_coverage_gee", "aoi_coverage_mpc"]].max(axis=1)
    cols = ["key", "sensing_utc", "month", "year", "platform", "tile", "state", "identity",
            "multiple_generations", "aoi_coverage",
            "ids_gee", "ids_mpc", "products_gee", "products_mpc",
            "baseline_gee", "baseline_mpc", "generation_gee", "generation_mpc",
            "cloud_cover_gee", "cloud_cover_mpc"]
    return t[cols].sort_values(["sensing_utc", "tile"], ignore_index=True)


def summarise(t: pd.DataFrame, by: str) -> pd.DataFrame:
    r = t.pivot_table(index=by, columns="state", values="key", aggfunc="count", fill_value=0)
    for c in ("BOTH", "GEE_ONLY", "MPC_ONLY"):
        if c not in r:
            r[c] = 0
    r = r[["BOTH", "GEE_ONLY", "MPC_ONLY"]]
    r["total"] = r.sum(axis=1)
    r["fraction_single_catalogue"] = (r["GEE_ONLY"] + r["MPC_ONLY"]) / r["total"]
    e2 = t[t["identity"] == "E2"].groupby(by)["key"].count()
    r["E2"] = e2.reindex(r.index).fillna(0).astype(int)
    return r.reset_index()


# ----------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="Reconcile the Sentinel-2 L2A catalogues of GEE and MPC over an AOI and a period.")
    ap.add_argument("--aoi", type=Path, required=True, help="AOI as GeoJSON, shapefile or GPKG.")
    ap.add_argument("--start", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", type=date.fromisoformat, required=True, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--gee-project", required=True, help="Google Cloud project for Earth Engine.")
    ap.add_argument("--min-coverage", type=float, default=0.0,
                    help="Ignore acquisitions covering less than this fraction of the AOI (0–1). "
                         "Default 0: everything is reported.")
    ap.add_argument("--out", type=Path, default=Path("reconciliation"))
    a = ap.parse_args()
    if a.end < a.start:
        sys.exit("--end must not be earlier than --start.")
    a.out.mkdir(parents=True, exist_ok=True)

    ee.Initialize(project=a.gee_project)
    aoi = read_aoi(a.aoi)

    print(f"Listing GEE ({GEE_COLLECTION}) ...")
    gee = list_gee(aoi_to_ee(aoi), a.start, a.end)
    print(f"  {len(gee)} images")
    print(f"Listing MPC ({MPC_COLLECTION}) ...")
    mpc = list_mpc(aoi, a.start, a.end)
    print(f"  {len(mpc)} items")
    if gee.empty and mpc.empty:
        sys.exit("Neither catalogue returned scenes for that AOI and period.")

    gee.to_csv(a.out / "scenes_gee.csv", index=False)
    mpc.to_csv(a.out / "scenes_mpc.csv", index=False)

    t = reconcile(gee, mpc)
    t = t[t["aoi_coverage"].fillna(0) >= a.min_coverage]
    t.to_csv(a.out / "scene_reconciliation.csv", index=False)
    summarise(t, "month").to_csv(a.out / "summary_by_month.csv", index=False)
    summarise(t, "year").to_csv(a.out / "summary_by_year.csv", index=False)
    summarise(t, "platform").to_csv(a.out / "summary_by_platform.csv", index=False)
    summarise(t, "tile").to_csv(a.out / "summary_by_tile.csv", index=False)

    counts = t["state"].value_counts().to_dict()
    both = t[t["state"] == "BOTH"]
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "aoi": str(a.aoi), "start": a.start.isoformat(), "end": a.end.isoformat(),
        "gee_collection": GEE_COLLECTION, "mpc_collection": MPC_COLLECTION,
        "matching_key": "datatake without baseline suffix + MGRS tile",
        "min_aoi_coverage": a.min_coverage,
        "acquisitions": int(len(t)), "by_state": {k: int(v) for k, v in counts.items()},
        "fraction_single_catalogue": float((t["state"] != "BOTH").mean()),
        "E1": int((both["identity"] == "E1").sum()),
        "E2": int((both["identity"] == "E2").sum()),
        "fraction_E2_of_BOTH": float((both["identity"] == "E2").mean()) if len(both) else None,
        "versions": {"earthengine-api": ee.__version__, "pandas": pd.__version__,
                     "shapely": shapely.__version__},
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")

    print("-" * 90)
    print(f"Acquisitions: {len(t)} | " + " | ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"In a single catalogue: {summary['fraction_single_catalogue']:.1%} | "
          f"E2 of BOTH: {summary['E2']}/{len(both)}")
    single = t[t["state"] != "BOTH"]
    for f in single.head(30).itertuples(index=False):
        print(f"  {f.state:9s} {f.sensing_utc:%Y-%m-%d %H:%M:%S} {f.platform} T{f.tile} "
              f"coverage={f.aoi_coverage:.2f}")
    if len(single) > 30:
        print(f"  ... and {len(single) - 30} more in scene_reconciliation.csv")
    print(f"Outputs in: {a.out.resolve()}")


if __name__ == "__main__":
    main()
