# Part of gee-mpc-sentinel2-validation (https://doi.org/10.5281/zenodo.23241823)
# Author: Heiber Alexander Pantevez Villamil (hapantevezv@unal.edu.co, ORCID 0000-0003-1797-0057), Universidad Nacional de Colombia
# Licence: MIT (see LICENSE)
"""
gee_mpc_s2val.impact (command: gee-mpc-impact)
========================================

Measures how much the monthly medians and annual composites of NDVI, EVI and
NDWI change when the scene universe is GEE's, MPC's or the one common to both.
Everything is computed with a single local engine, so that the only
difference between results is which scenes enter.

Why it exists
-------------
The pilot case showed that, with the same scenes, GEE and MPC produce the
same indices pixel by pixel (equivalent product, processing chain and median).
The difference appeared when the GEE product included scenes that MPC did not
hold. This script quantifies that effect for any AOI and period, before
deciding how to combine the platforms.

Design
------
* Scene universes, from scene_reconciliation.csv:
      COMMON = BOTH acquisitions
      GEE    = BOTH + GEE_ONLY
      MPC    = BOTH + MPC_ONLY
* Each scene is read from the catalogue where it exists; BOTH scenes from
  --common-source. This is valid because, for the same product, GEE and MPC
  deliver equivalent values after harmonisation (verified in the pilot). If a
  BOTH acquisition is E2, the --common-source generation is used and this is
  reported in scenes_used.csv.
* Explicit radiometry: reflectance = max(DN + BOA_ADD_OFFSET, 0) / 10000.
  In GEE (S2_SR_HARMONIZED) the offset is already applied; in MPC it is read
  from the product XML (baseline >= 04.00).
* Fixed grid (--crs, --resolution) aligned to multiples of the resolution,
  nearest neighbour, AOI membership by pixel centre.
* Joint validity: SCL in --valid-scl and native data in B02, B03, B04, B08.
  GEE validity is downloaded as its own band: a harmonised DN = 0 is a real
  value and is never used as a "no data" flag.
* 3x3 mean of reflectance over valid neighbours before the indices
  (disable with --no-3x3). Per-pixel monthly median. Annual composite as a
  multivariate medoid of the months (--min-months, --min-quarters).
* Every output GeoTIFF carries an OBS_COUNT band and a JSON with the list of
  scenes that produced it (provenance inside the product).

Usage
-----
    gee-mpc-impact --reconciliation reconciliation/scene_reconciliation.csv \\
        --aoi aoi.geojson --gee-project MY_PROJECT --out impact

Useful options: --crs EPSG:9377 (default: UTM zone of the AOI), --months 2024-12,2025-01,
--common-source gee, --only-months-with-difference (process only months with scenes
in a single catalogue), --max-cloud 20.

Outputs (in --out)
------------------
    scenes_used.csv              scene, catalogue read, universes it belongs to
    monthly_metrics.csv          differences between universes by month and index
    annual_metrics.csv           the same for annual composites (if enough months)
    monthly/<YYYY-MM>_<UNIVERSE>.tif (+ .json)   NDVI, EVI, NDWI, OBS_COUNT
    summary.json
    cache/                       downloaded scenes (reused)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import warnings
import xml.etree.ElementTree as ET

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
from pyproj import CRS
from pystac_client import Client
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
import requests
import shapely
from shapely.geometry import mapping

from .radiometry import NODATA_OUT, gee_reflectance, gee_valid, mpc_reflectance, mpc_valid, to_output

MPC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
MPC_BANDS = ("B02", "B03", "B04", "B08")
GEE_BANDS = ("B2", "B3", "B4", "B8")
INDICES = ("NDVI", "EVI", "NDWI")
NODATA = NODATA_OUT
MEDOID_SCALES = np.array([1.2, 1.2, 2.0])   # scale of NDVI, EVI, NDWI
BAND_ID = {"B02": 1, "B03": 2, "B04": 3, "B08": 7}  # band_id in the product XML


# ----------------------------------------------------------------------- grid

def auto_utm_crs(geom_4326: shapely.Geometry) -> str:
    c = geom_4326.centroid
    zone = int((c.x + 180) // 6) + 1
    return f"EPSG:{(32600 if c.y >= 0 else 32700) + zone}"


def build_grid(aoi_path: Path, crs: str, res: float):
    gdf = gpd.read_file(aoi_path)
    geom4326 = shapely.force_2d(gdf.to_crs(4326).geometry.union_all())
    if crs == "auto":
        crs = auto_utm_crs(geom4326)
    geom = shapely.force_2d(gdf.to_crs(crs).geometry.union_all())
    minx, miny, maxx, maxy = geom.bounds
    # Aligned to multiples of the resolution, with a one-pixel halo for the 3x3.
    left = math.floor(minx / res) * res - res
    top = math.ceil(maxy / res) * res + res
    right = math.ceil(maxx / res) * res + res
    bottom = math.floor(miny / res) * res - res
    width, height = int(round((right - left) / res)), int(round((top - bottom) / res))
    transform = Affine(res, 0, left, 0, -res, top)
    inside = geometry_mask([mapping(geom)], out_shape=(height, width), transform=transform, invert=True)
    return crs, transform, width, height, inside


# ------------------------------------------------------------- scene reading

def read_gee(asset: str, crs: str, transform: Affine, width: int, height: int, cache: Path):
    """Downloads B2, B3, B4, B8, SCL and the native spectral mask on the exact grid."""
    target = cache / (asset.replace("/", "__") + ".tif")
    if not target.exists():
        wkt = CRS.from_user_input(crs).to_wkt(version="WKT1_GDAL")
        img = ee.Image(asset)
        spectral = img.select(list(GEE_BANDS))
        mask = spectral.mask().reduce(ee.Reducer.min()).gt(0).rename("MASK")
        out = spectral.addBands(img.select("SCL")).unmask(0).addBands(mask.unmask(0)).toUint16()
        res = transform.a
        region = ee.Geometry.Rectangle(
            [transform.c, transform.f - res * height, transform.c + res * width, transform.f],
            proj=ee.Projection(wkt), geodesic=False)
        url = out.getDownloadURL({"region": region, "crs": wkt, "format": "GEO_TIFF",
                                  "crs_transform": [res, 0, transform.c, 0, -res, transform.f]})
        r = requests.get(url, timeout=600)
        r.raise_for_status()
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(target)
    with rasterio.open(target) as src:
        if (src.width, src.height) != (width, height) or not src.transform.almost_equals(transform):
            raise RuntimeError(f"{asset}: the downloaded grid does not match the working grid.")
        data = src.read()
    return gee_reflectance(data[:4]), gee_valid(data[5]), data[4]   # DN already harmonised by GEE


def mpc_radiometry(item) -> dict:
    """BOA offsets from the product XML (baseline >= 04.00); 0 before."""
    pb = float(str(item.properties.get("s2:processing_baseline", "0")).replace("N", ""))
    if pb < 4.0:
        return {"baseline": pb, "qv": 10000.0, "offsets": {b: 0.0 for b in MPC_BANDS}}
    signed = planetary_computer.sign(item.clone())
    href = signed.assets["product-metadata"].href
    root = ET.fromstring(requests.get(href, timeout=120).content)
    qv, by_id, without_id = None, {}, []
    for el in root.iter():
        name, text = el.tag.rsplit("}", 1)[-1], (el.text or "").strip()
        if not text:
            continue
        if name == "BOA_QUANTIFICATION_VALUE":
            qv = float(text)
        elif name == "BOA_ADD_OFFSET":
            bid = el.attrib.get("band_id") or el.attrib.get("bandId")
            if bid is not None:
                by_id[int(bid)] = float(text)
            else:
                without_id.append(float(text))
    offsets = {b: by_id.get(BAND_ID[b], without_id[0] if without_id else None) for b in MPC_BANDS}
    if qv is None or any(v is None for v in offsets.values()):
        raise RuntimeError(f"{item.id}: the radiometry could not be read from the XML.")
    return {"baseline": pb, "qv": qv, "offsets": offsets}


def read_mpc(item_id: str, crs: str, transform: Affine, width: int, height: int,
             client: Client, cache: Path):
    target = cache / f"{item_id}.npz"
    if target.exists():
        z = np.load(target)
        return z["reflectance"], z["valid"], z["scl"]
    item = next(client.search(collections=["sentinel-2-l2a"], ids=[item_id]).items())
    rad = mpc_radiometry(item)
    signed = planetary_computer.sign(item.clone())

    def read(band):
        with rasterio.open(signed.assets[band].href) as src:
            with WarpedVRT(src, crs=crs, transform=transform, width=width, height=height,
                           resampling=Resampling.nearest, src_nodata=src.nodata, nodata=0) as vrt:
                arr = vrt.read(1, masked=True)
        values = np.asarray(arr.filled(0))
        return values, mpc_valid(values, np.ma.getmaskarray(arr))   # in MPC, DN 0 = no data

    refl, valids = [], []
    for b in MPC_BANDS:
        dn, v = read(b)
        refl.append(mpc_reflectance(dn, rad["offsets"][b], rad["qv"]))
        valids.append(v)
    scl, _ = read("SCL")
    reflectance, valid = np.stack(refl), np.logical_and.reduce(valids)
    np.savez_compressed(target, reflectance=reflectance, valid=valid, scl=scl)
    return reflectance, valid, scl


# ----------------------------------------------------------- processing chain

def sum_3x3(a: np.ndarray) -> np.ndarray:
    p = np.pad(a, 1)
    return sum(p[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3))


def scene_indices(reflectance, spectral_valid, scl, valid_classes, use_3x3: bool):
    valid = spectral_valid & np.isin(scl, list(valid_classes))
    if use_3x3:
        n = sum_3x3(valid.astype(np.float64))
        r = [sum_3x3(np.where(valid, b, 0.0)) / np.maximum(n, 1.0) for b in reflectance]
    else:
        r = list(reflectance)
    blue, green, red, nir = r
    with np.errstate(divide="ignore", invalid="ignore"):
        out = {"NDVI": (nir - red) / (nir + red),
               "EVI": 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1),
               "NDWI": (green - nir) / (green + nir)}
    for k in out:
        out[k] = np.where(valid & np.isfinite(out[k]), out[k], np.nan)
    return out


def median(stack: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    s = np.stack(stack)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmedian(s, axis=0), np.isfinite(s).sum(axis=0)


def medoid(months: list[str], layers: list[np.ndarray], min_months: int, min_quarters: int):
    v = np.stack(layers)                              # (t, 3, h, w)
    ok = np.all(np.isfinite(v), axis=1)
    quarters = np.zeros(ok.shape[1:], dtype=int)
    for q in range(4):
        idx = [i for i, m in enumerate(months) if (int(m[5:7]) - 1) // 3 == q]
        if idx:
            quarters += np.any(ok[idx], axis=0)
    eligible = (ok.sum(axis=0) >= min_months) & (quarters >= min_quarters)
    scaled = v / MEDOID_SCALES[None, :, None, None]
    score = np.full(ok.shape, np.inf)
    for t in range(len(months)):
        total = np.zeros(ok.shape[1:])
        for u in range(len(months)):
            both = ok[t] & ok[u]
            d = np.sqrt(np.nansum((scaled[t] - scaled[u]) ** 2, axis=0))
            total[both] += d[both]
        score[t, ok[t]] = total[ok[t]]
    sel = np.argmin(score, axis=0)
    rows, cols = np.indices(sel.shape)
    annual = v[sel, :, rows, cols].transpose(2, 0, 1)
    annual[:, ~eligible] = np.nan
    return annual, eligible


def metrics(a: np.ndarray, b: np.ndarray, inside: np.ndarray) -> dict:
    both = inside & np.isfinite(a) & np.isfinite(b)
    d = a[both] - b[both]
    base = {"common_pixels": int(both.sum()),
            "valid_only_a": int((inside & np.isfinite(a) & ~np.isfinite(b)).sum()),
            "valid_only_b": int((inside & ~np.isfinite(a) & np.isfinite(b)).sum())}
    if d.size == 0:
        return base
    ad = np.abs(d)
    return {**base, "bias_a_minus_b": float(d.mean()), "mae": float(ad.mean()),
            "p95_abs": float(np.quantile(ad, 0.95)), "max_abs": float(ad.max()),
            "fraction_pixels_changed": float((ad > 1e-6).mean())}


def write_tif(path: Path, bands: list[np.ndarray], names: list[str], crs: str,
              transform: Affine, scenes: list[str], extra: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256("\n".join(sorted(scenes)).encode()).hexdigest()
    profile = {"driver": "GTiff", "height": bands[0].shape[0], "width": bands[0].shape[1],
               "count": len(bands), "dtype": "float32", "crs": crs, "transform": transform,
               "nodata": NODATA, "compress": "deflate"}
    with rasterio.open(path, "w", **profile) as dst:
        for i, (b, n) in enumerate(zip(bands, names), start=1):
            dst.write(to_output(b), i)
            dst.set_band_description(i, n)
        # Provenance INSIDE the file: digest and number of scenes.
        dst.update_tags(scenes_sha256=digest, n_scenes=str(len(scenes)), **{k: str(v) for k, v in extra.items()})
    path.with_suffix(".json").write_text(json.dumps(
        {"scenes": sorted(scenes), "scenes_sha256": digest, **extra}, indent=2, ensure_ascii=False),
        encoding="utf-8")


# ----------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="Effect of the scene universe (GEE, MPC, common) on composites.")
    ap.add_argument("--reconciliation", type=Path, required=True)
    ap.add_argument("--aoi", type=Path, required=True)
    ap.add_argument("--gee-project", required=True)
    ap.add_argument("--out", type=Path, default=Path("impact"))
    ap.add_argument("--crs", default="auto", help="e.g. EPSG:9377; default: UTM zone of the AOI.")
    ap.add_argument("--resolution", type=float, default=10.0)
    ap.add_argument("--common-source", choices=("mpc", "gee"), default="mpc")
    ap.add_argument("--valid-scl", default="2,4,5,6,7")
    ap.add_argument("--no-3x3", action="store_true")
    ap.add_argument("--months", help="Comma-separated YYYY-MM list; default: all.")
    ap.add_argument("--only-months-with-difference", action="store_true",
                    help="Process only months with scenes in a single catalogue.")
    ap.add_argument("--min-coverage", type=float, default=0.0)
    ap.add_argument("--max-cloud", type=float,
                    help="Exclude acquisitions with higher scene cloud cover (%%). The GEE value is used "
                         "and, if missing, the MPC value. Use it to match the filter of an existing manifest.")
    ap.add_argument("--min-months", type=int, default=8)
    ap.add_argument("--min-quarters", type=int, default=4)
    a = ap.parse_args()

    valid_classes = {int(v) for v in a.valid_scl.split(",")}
    cache = a.out / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    ee.Initialize(project=a.gee_project)
    client = Client.open(MPC_STAC)

    t = pd.read_csv(a.reconciliation, parse_dates=["sensing_utc"])
    t = t[t["aoi_coverage"].fillna(0) >= a.min_coverage]
    if a.max_cloud is not None:
        cloud = t["cloud_cover_gee"].fillna(t["cloud_cover_mpc"])
        t = t[cloud.fillna(0) <= a.max_cloud]
    if a.months:
        t = t[t["month"].isin(a.months.split(","))]
    if a.only_months_with_difference:
        t = t[t["month"].isin(t.loc[t["state"] != "BOTH", "month"].unique())]
    if t.empty:
        sys.exit("No acquisitions remain after the filters.")

    crs, transform, width, height, inside = build_grid(a.aoi, a.crs, a.resolution)
    print(f"Grid {crs} {a.resolution} m | {width}x{height} | pixels in the AOI: {int(inside.sum())}")

    universes = {"COMMON": {"BOTH"}, "GEE": {"BOTH", "GEE_ONLY"}, "MPC": {"BOTH", "MPC_ONLY"}}
    used, metric_rows, monthly = [], [], {}
    for month, grp in t.groupby("month"):
        stacks = {u: {i: [] for i in INDICES} for u in universes}
        scenes = {u: [] for u in universes}
        for f in grp.itertuples(index=False):
            source = {"BOTH": a.common_source, "GEE_ONLY": "gee", "MPC_ONLY": "mpc"}[f.state]
            ident = str(f.ids_gee if source == "gee" else f.ids_mpc).split("|")[0]
            if source == "gee":
                refl, val, scl = read_gee(ident, crs, transform, width, height, cache)
            else:
                refl, val, scl = read_mpc(ident, crs, transform, width, height, client, cache)
            idx = scene_indices(refl, val, scl, valid_classes, not a.no_3x3)
            member = [u for u, states in universes.items() if f.state in states]
            for u in member:
                scenes[u].append(ident)
                for i in INDICES:
                    stacks[u][i].append(idx[i])
            used.append({"month": month, "key": f.key, "state": f.state, "identity": f.identity,
                         "catalogue_read": source, "id": ident, "universes": "|".join(member),
                         "valid_pixels_aoi": int((inside & np.isfinite(idx["NDVI"])).sum())})
        for u in universes:
            if not scenes[u]:
                continue
            layers, count = [], None
            for i in INDICES:
                m, n = median(stacks[u][i])
                layers.append(m)
                count = n
            monthly[(month, u)] = np.stack(layers)
            write_tif(a.out / "monthly" / f"{month}_{u}.tif", layers + [count.astype(float)],
                      list(INDICES) + ["OBS_COUNT"], crs, transform, scenes[u],
                      {"month": month, "universe": u, "common_source": a.common_source})
        for x, y in (("GEE", "COMMON"), ("MPC", "COMMON"), ("GEE", "MPC")):
            if (month, x) in monthly and (month, y) in monthly:
                for k, i in enumerate(INDICES):
                    metric_rows.append({"month": month, "index": i, "a": x, "b": y,
                                        "scenes_a": len(scenes[x]), "scenes_b": len(scenes[y]),
                                        **metrics(monthly[(month, x)][k], monthly[(month, y)][k], inside)})
        print(f"{month} | COMMON={len(scenes['COMMON'])} GEE={len(scenes['GEE'])} MPC={len(scenes['MPC'])}")

    annual_rows = []
    for year in sorted({m[:4] for m, _ in monthly}):
        composites = {}
        for u in universes:
            months = sorted(m for m, uu in monthly if uu == u and m.startswith(year))
            if len(months) < a.min_months:
                continue
            composites[u] = medoid(months, [monthly[(m, u)] for m in months], a.min_months, a.min_quarters)
        for x, y in (("GEE", "COMMON"), ("MPC", "COMMON"), ("GEE", "MPC")):
            if x in composites and y in composites:
                for k, i in enumerate(INDICES):
                    annual_rows.append({"year": year, "index": i, "a": x, "b": y,
                                        **metrics(composites[x][0][k], composites[y][0][k], inside)})

    pd.DataFrame(used).to_csv(a.out / "scenes_used.csv", index=False)
    met = pd.DataFrame(metric_rows)
    met.to_csv(a.out / "monthly_metrics.csv", index=False)
    pd.DataFrame(annual_rows).to_csv(a.out / "annual_metrics.csv", index=False)
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "grid": {"crs": crs, "resolution_m": a.resolution, "aoi_pixels": int(inside.sum())},
        "filters": {"min_aoi_coverage": a.min_coverage, "max_cloud_cover": a.max_cloud, "months": a.months},
        "contract": {"valid_scl_classes": sorted(valid_classes), "smoothing_3x3": not a.no_3x3,
                     "common_source": a.common_source, "radiometry": "max(DN + BOA_ADD_OFFSET, 0) / 10000",
                     "monthly_reducer": "median per index", "annual_composite": "multivariate medoid",
                     "min_months": a.min_months, "min_quarters": a.min_quarters},
        "months_processed": sorted({m for m, _ in monthly}),
        "years_with_composite": sorted({r["year"] for r in annual_rows}),
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    if not met.empty:
        print("-" * 90)
        view = met[(met["a"] == "GEE") & (met["b"] == "COMMON") & (met["index"] == "NDVI")]
        for f in view.itertuples(index=False):
            print(f"{f.month} NDVI | GEE − COMMON: bias={getattr(f, 'bias_a_minus_b', float('nan')):+.5f} "
                  f"MAE={getattr(f, 'mae', float('nan')):.5f} ({f.scenes_a} vs {f.scenes_b} scenes)")
    print(f"Outputs in: {a.out.resolve()}")


if __name__ == "__main__":
    main()
