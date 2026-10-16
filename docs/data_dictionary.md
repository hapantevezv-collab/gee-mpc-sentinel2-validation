# Data dictionary

Column definitions for the tables written by `gee-mpc-reconcile`, `gee-mpc-e2` and
`gee-mpc-impact`, and for the derived tables of the data package
(https://doi.org/10.5281/zenodo.23241823, folder `06_derived/`). The same definitions in
machine-readable form are in [`data_dictionary.csv`](data_dictionary.csv); the test
`tests/test_data_dictionary.py` checks that every column of the reference outputs is listed.

- **Unit of observation:** scene–tile record. An acquisition in the overlap of two MGRS
  tiles appears twice (one key per tile).
- **Query date:** catalogues change over time, so every result belongs to the moment of its
  run, stored as `created_utc` in each `summary.json`. Pilot farm reconciliation:
  2026-09-25 03:43 UTC (24 September 2026, Bogotá time). Public demonstration AOI:
  8 October 2026.
- **Empty cells** mean "not applicable" or "not reported by the catalogue". Several values
  in one cell are separated by `|`.
- **Times** are ISO 8601 in UTC. **Cloud cover** is the catalogue value for the whole
  granule (tile), not for the AOI.
- **Rasters** (`monthly/*.tif`, not in the data package): float32 bands NDVI, EVI, NDWI and
  OBS_COUNT (valid observations per pixel), nodata −9999, tags `scenes_sha256` and `n_scenes`.
- **Privacy:** no table contains the farm geometry; the farm is called `FARM`.

The tables in `04_evidence_section_3_2/` of the data package come from one-off tests of
Section 3.2 of the preprint. They are described at file level in the data package README
and in the run logs next to them, not column by column here.


## scene_reconciliation.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `key` | string |  | Acquisition key: datatake identifier without the processing-baseline suffix (_Nxx.xx), a vertical bar, and the MGRS tile without the leading T (e.g. GS2B_20240601T152659_037803\|18PYS). If the datatake is missing: platform_sensing-time\|tile. One row per key (scene-tile record). |
| `sensing_utc` | datetime | UTC | Sensing time. GEE system:time_start when the record is in GEE, otherwise the MPC item datetime; earliest value across generations. |
| `month` | string | YYYY-MM | Month of sensing_utc. |
| `year` | integer |  | Year of sensing_utc. |
| `platform` | string |  | Satellite: S2A, S2B or S2C (from SPACECRAFT_NAME in GEE, platform in MPC). |
| `tile` | string |  | MGRS tile without the leading T (e.g. 18PXS). |
| `state` | string |  | Catalogue presence: BOTH, GEE_ONLY or MPC_ONLY. |
| `identity` | string |  | Only for state = BOTH. E1: at least one product identifier is shared by both catalogues (same L2A generation). E2: same acquisition, no shared product identifier (different L2A generation). Empty otherwise. |
| `multiple_generations` | boolean |  | True if either catalogue holds more than one product (L2A generation) for the key. |
| `aoi_coverage` | float | fraction 0-1 | Share of the AOI inside the scene footprint; maximum of the two catalogues. GEE: geodesic areas with a 10 m error margin. MPC: ratio of areas in geographic degrees (approximate; separates full coverage from edge scenes). |
| `ids_gee` | string |  | GEE asset identifier(s), `COPERNICUS/S2_SR_HARMONIZED/<system:index>`; several are sorted and joined with \|. Empty if absent from GEE. |
| `ids_mpc` | string |  | MPC STAC item identifier(s) in collection sentinel-2-l2a; several joined with \|. Empty if absent from MPC. |
| `products_gee` | string |  | ESA product identifier(s) reported by GEE (PRODUCT_ID, without .SAFE); several joined with \|. |
| `products_mpc` | string |  | ESA product identifier(s) reported by MPC (s2:product_uri, without .SAFE); several joined with \|. |
| `baseline_gee` | float |  | Processing baseline reported by GEE (PROCESSING_BASELINE; 5.1 = N05.10); maximum across generations. |
| `baseline_mpc` | float |  | Processing baseline reported by MPC (s2:processing_baseline); maximum across generations. |
| `generation_gee` | datetime | UTC | L2A generation time reported by GEE (GENERATION_TIME); latest across generations. |
| `generation_mpc` | datetime | UTC | L2A generation time reported by MPC (s2:generation_time); latest across generations. |
| `cloud_cover_gee` | float | percent | Cloud cover of the whole granule (tile), not of the AOI, reported by GEE (CLOUDY_PIXEL_PERCENTAGE); minimum across generations. |
| `cloud_cover_mpc` | float | percent | Cloud cover of the whole granule (tile), not of the AOI, reported by MPC (eo:cloud_cover); minimum across generations. |

## scenes_gee.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `CLOUDY_PIXEL_PERCENTAGE`, `DATATAKE_IDENTIFIER`, `GENERATION_TIME`, `MGRS_TILE`, `PROCESSING_BASELINE`, `PRODUCT_ID`, `SENSING_ORBIT_NUMBER`, `SPACECRAFT_NAME` | mixed |  | Image properties as reported by GEE, unchanged. GENERATION_TIME is in milliseconds since 1970-01-01 UTC. |
| `aoi_coverage` | float | fraction 0-1 | Share of the AOI inside the image footprint (geodesic; 10 m error margin). |
| `asset_id` | string |  | GEE asset identifier: `COPERNICUS/S2_SR_HARMONIZED/<system:index>`. |
| `time_start` | integer | ms since 1970-01-01 UTC | system:time_start of the image. |
| `sensing_utc`, `platform`, `tile`, `datatake`, `product`, `baseline`, `generation`, `cloud_cover` | mixed |  | Normalised fields used for matching: sensing time (UTC), S2A/S2B/S2C, tile without T, datatake without baseline suffix, product without .SAFE, baseline as number, generation time (UTC), cloud cover (%). |

## scenes_mpc.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `item_id` | string |  | MPC STAC item identifier. |
| `sensing_utc`, `platform`, `tile`, `datatake`, `product`, `baseline`, `generation`, `cloud_cover` | mixed |  | Same normalised fields as in scenes_gee.csv, from the STAC properties datetime, platform, s2:mgrs_tile, s2:datatake_id, s2:product_uri, s2:processing_baseline, s2:generation_time and eo:cloud_cover. |
| `relative_orbit` | integer |  | STAC property sat:relative_orbit. |
| `aoi_coverage` | float | fraction 0-1 | Share of the AOI inside the item footprint (areas in geographic degrees; approximate). |

## summary_by_month.csv, summary_by_year.csv, summary_by_platform.csv, summary_by_tile.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `month`, `year`, `platform`, `tile` | string |  | Stratum. |
| `BOTH`, `GEE_ONLY`, `MPC_ONLY` | integer | records | Number of scene-tile records in each state. |
| `total` | integer | records | BOTH + GEE_ONLY + MPC_ONLY. |
| `fraction_single_catalogue` | float | fraction 0-1 | (GEE_ONLY + MPC_ONLY) / total. |
| `E2` | integer | records | Number of records with identity = E2. |

## e2_pairs.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| (all columns of scene_reconciliation.csv) |  |  | Rows of scene_reconciliation.csv with state = BOTH (E1 and E2), plus the four columns below. |
| `is_e2` | boolean |  | True if identity = E2. |
| `baseline_pair` | string |  | Baselines as GEE → MPC, two decimals with zero padding (e.g. 05.10 → 05.10); ? if missing. |
| `difference_type` | string |  | IDENTICAL (E1); SAME_BASELINE_OTHER_GENERATION (E2, same baseline); DIFFERENT_BASELINE (E2, different baseline). |
| `generation_lag_h` | float | hours | generation_mpc − generation_gee. |

## e2_by_month.csv, e2_by_year.csv, e2_by_platform.csv, e2_by_tile.csv, e2_by_baseline_pair.csv, e2_by_difference_type.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `month`, `year`, `platform`, `tile`, `baseline_pair`, `difference_type` | string |  | Stratum. |
| `acquisitions` | integer | records | Records with state = BOTH in the stratum. |
| `e2` | integer | records | Records with identity = E2 in the stratum. |
| `fraction_e2` | float | fraction 0-1 | e2 / acquisitions. |

## e2_scl.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `key`, `sensing_utc`, `tile` | mixed |  | As in scene_reconciliation.csv. |
| `gee_asset` | string |  | GEE asset whose SCL band was read (first of ids_gee). |
| `mpc_item` | string |  | MPC item whose SCL asset was read (first of ids_mpc). |
| `aoi_pixels_20m` | integer | pixels | AOI pixels on the native 20 m SCL grid of the MPC item; GEE SCL is read on the same lattice. |
| `scl_class_agreement` | float | fraction 0-1 | Share of AOI pixels with the same SCL class in both catalogues. |
| `valid_gee`, `valid_mpc` | integer | pixels | AOI pixels with a valid SCL class (default 2, 4, 5, 6, 7) in each catalogue. |
| `valid_only_gee`, `valid_only_mpc` | integer | pixels | Pixels valid in one catalogue and not in the other. |
| `validity_jaccard` | float | fraction 0-1 | Pixels valid in both / pixels valid in either. Empty if no pixel is valid in either catalogue. |
| `frequent_scl_transitions_gee_to_mpc` | string |  | Up to three most frequent class changes, as GEE class->MPC class:pixels, separated by ; (e.g. 4->10:46). Empty if the SCL is identical. |

## scenes_used.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `month` | string | YYYY-MM | Month of the composite. |
| `key`, `state`, `identity` | string |  | As in scene_reconciliation.csv. |
| `catalogue_read` | string |  | Catalogue the pixels were read from: mpc or gee. BOTH records are read from --common-source (default mpc); GEE_ONLY from gee; MPC_ONLY from mpc. |
| `id` | string |  | Asset or item identifier read. |
| `universes` | string |  | Universes the scene belongs to, joined with \|: COMMON (BOTH), GEE (BOTH + GEE_ONLY), MPC (BOTH + MPC_ONLY). |
| `valid_pixels_aoi` | integer | pixels | AOI pixels with a valid NDVI after mask and 3 × 3 smoothing. |

## monthly_metrics.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `month` | string | YYYY-MM | Month of the composites. |
| `index` | string |  | NDVI, EVI or NDWI. |
| `a`, `b` | string |  | Universes compared (difference = a − b). |
| `scenes_a`, `scenes_b` | integer | scenes | Scenes in each monthly composite. |
| `common_pixels` | integer | pixels | AOI pixels valid in both composites. |
| `valid_only_a`, `valid_only_b` | integer | pixels | AOI pixels valid in one composite only. |
| `bias_a_minus_b` | float | index units | Mean of the per-pixel difference a − b over common_pixels. |
| `mae` | float | index units | Mean absolute difference. |
| `p95_abs` | float | index units | 95th percentile of the absolute difference. |
| `max_abs` | float | index units | Maximum absolute difference. |
| `fraction_pixels_changed` | float | fraction 0-1 | Share of common pixels with absolute difference > 1e-6. |

## monthly/YYYY-MM_UNIVERSE.json

| Column | Type | Unit | Description |
|---|---|---|---|
| `scenes` | list of strings |  | Identifiers of the scenes in the composite (sorted). |
| `scenes_sha256` | string |  | SHA-256 of the sorted scene identifiers joined with newlines; also written in the GeoTIFF metadata. |
| `month`, `universe`, `common_source` | string |  | Month, universe (COMMON, GEE, MPC) and the catalogue read for BOTH records. |

## single_catalogue_records.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| (columns of scene_reconciliation.csv) |  |  | Records with state GEE_ONLY or MPC_ONLY; columns sensing_utc, month, platform, tile, state, ids_*, products_*, baseline_*, generation_*, cloud_cover_*, aoi_coverage as defined above. |

## inventory_by_month_satellite.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `catalogue` | string |  | GEE or MPC. |
| `month`, `platform` | string |  | Month (YYYY-MM) and satellite (S2A/S2B/S2C). |
| `records` | integer | records | Listed scenes (rows of scenes_gee.csv or scenes_mpc.csv). |

## monthly_difference_distribution.csv

| Column | Type | Unit | Description |
|---|---|---|---|
| `month`, `index` | string |  | Month (YYYY-MM) and index. |
| `comparison` | string |  | Always GEE - COMMON (difference = GEE universe − COMMON universe). |
| `valid_pixels` | integer | pixels | AOI pixels valid in both composites. |
| `bias` | float | index units | Mean per-pixel difference. |
| `bias_ci95_low`, `bias_ci95_high` | float | index units | 95% confidence interval of bias: percentile bootstrap resampling spatial blocks of 10 × 10 pixels, 2,000 resamples, seed 20261008. |
| `bootstrap_blocks` | integer | blocks | Blocks with at least one valid pixel. |
| `mae` | float | index units | Mean absolute difference. |
| `p5`, `p50`, `p95` | float | index units | 5th, 50th and 95th percentiles of the signed difference. |
| `p99_abs`, `max_abs` | float | index units | 99th percentile and maximum of the absolute difference. |
| `fraction_abs_gt_0_01`, `fraction_abs_gt_0_02` | float | fraction 0-1 | Share of pixels with absolute difference above 0.01 and 0.02. |
