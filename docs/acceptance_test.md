# Acceptance tests

Two acceptance tests document the verified behaviour of the code: the pilot farm
(private geometry, values for reference only) and the public demonstration AOI
(anyone can run it).

## 1. Pilot farm

Values obtained by running the three commands over the pilot farm (Cesar, Colombia;
MGRS tiles T18PXS and T18PYS), with catalogue queries of 24 September 2026. The farm
geometry is not distributed.

```bash
gee-mpc-reconcile --aoi farm_aoi.geojson --start 2024-06-01 --end 2025-04-30 \
    --gee-project MY_PROJECT --out accept_reconciliation
gee-mpc-e2 --reconciliation accept_reconciliation/scene_reconciliation.csv \
    --measure-scl --aoi farm_aoi.geojson --gee-project MY_PROJECT --out accept_e2
gee-mpc-impact --reconciliation accept_reconciliation/scene_reconciliation.csv \
    --aoi farm_aoi.geojson --gee-project MY_PROJECT --crs EPSG:9377 \
    --months 2024-12,2025-01 --max-cloud 20 --out accept_impact
```

### Reconciliation (June 2024 to April 2025)

| Measure | Value |
|---|---|
| Images in GEE / items in MPC | 146 / 136 |
| Scene–tile records present in both | 136 |
| GEE only | 10 (6.8%) |
| MPC only | 0 |

Records present only in GEE (all covering the whole farm):

| Date | Satellite | Tiles | Processing baseline |
|---|---|---|---|
| 2024‑09‑14 | S2A | T18PXS, T18PYS | 05.11 |
| 2024‑09‑19 | S2B | T18PXS, T18PYS | 05.11 |
| 2024‑12‑13 | S2C | T18PXS, T18PYS | 99.05 (provisional) |
| 2025‑01‑22 | S2C | T18PXS, T18PYS | 05.11 |
| 2025‑02‑11 | S2C | T18PXS, T18PYS | 05.11 |

### Different generations (E2)

| Measure | Value |
|---|---|
| E2 among common records | 22 / 136 (16.2%) |
| Type | All with the same baseline and another generation |
| Period | 1 June to 21 July 2024 |
| Identical SCL over the farm, with valid pixels | 9 |
| Fully cloudy in both versions | 12 |
| With an SCL difference | 1 (2024‑06‑01, T18PXS; class agreement 0.961 and validity Jaccard 0.899 at 20 m) |

### Effect on monthly medians (GEE − common)

Grid EPSG:9377 at 10 m, 7,348 farm pixels, scene cloud cover ≤ 20%.

| Month | Records common / GEE | NDVI bias | NDVI MAE |
|---|---|---|---|
| 2024‑12 | 4 / 5 | −0.00047 | 0.00594 |
| 2025‑01 | 6 / 8 | −0.00867 | 0.01224 |

These values match those of the monthly composite exported from GEE in the original
study, which confirms that the difference comes only from the scene universe.

## 2. Public demonstration AOI

`data/demo_aoi.geojson` is a 1 km × 1 km square in the T18PXS/T18PYS overlap. It
reproduces the farm's catalogue findings. Catalogues were queried on 8 October 2026;
reference outputs and SHA-256 hashes are in `data/acceptance/demo/` and the expected
values in `data/acceptance/demo/acceptance_demo.json`. The commands are in the README.

| Measure | Value |
|---|---|
| Records in GEE / MPC | 146 / 136 |
| Present in both / GEE only / MPC only | 136 / 10 / 0 |
| E2 among common records | 22 |
| E2 pairs with an SCL difference | 1 (2024‑07‑06, T18PXS; validity Jaccard 0.993) |
| Grid | EPSG:9377, 10 m, 9,970 AOI pixels |

NDVI difference between monthly medians, GEE − common (scene cloud cover ≤ 20%):

| Month | Records common / GEE | Bias | MAE |
|---|---|---|---|
| 2024‑09 | 1 / 3 | +0.0005 | 0.0130 |
| 2024‑12 | 4 / 5 | +0.0042 | 0.0074 |
| 2025‑01 | 6 / 8 | −0.0281 | 0.0284 |
| 2025‑02 | 5 / 6 | −0.0147 | 0.0150 |

Offline, `pytest -m "not ee"` recomputes the reconciliation and the E2 strata from the
published scene lists and checks these values and the hashes. Online, run the commands
in the README and compare the outputs with `gee-mpc-verify-demo`.
